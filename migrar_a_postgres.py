"""
Copia TODOS los datos de db.sqlite3 (SQLite) a una base de datos PostgreSQL.

Uso (desde la carpeta raíz del backend, donde está db.sqlite3):

    uv run python migrar_a_postgres.py "postgresql://usuario:clave@servidor:5432/base"

Opciones:
    --origen RUTA     Archivo SQLite de origen (por defecto: db.sqlite3)
    --solo-revisar    No escribe nada: solo muestra cuántas filas se copiarían
    --reemplazar      Si el destino ya tiene datos, los BORRA antes de copiar

Qué hace:
  1. Crea las tablas en PostgreSQL si no existen.
  2. Copia cada tabla conservando los mismos id (así no se rompen las relaciones).
  3. Ajusta los contadores de id de PostgreSQL para que los registros nuevos no choquen.
  4. Compara el número de filas de origen y destino y avisa si algo no coincide.

El archivo db.sqlite3 se abre en modo SOLO LECTURA: nunca se modifica.
"""
import argparse
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from sqlalchemy import Boolean, Date, DateTime, create_engine, text, select, func
from sqlmodel import SQLModel

import modelos  # noqa: F401  (registra las tablas en SQLModel.metadata)

LOTE = 500


def url_postgres(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if not url.startswith("postgresql+psycopg://"):
        sys.exit("La URL de destino debe ser de PostgreSQL (postgresql://...).")
    return url


def main():
    ap = argparse.ArgumentParser(description="Migra db.sqlite3 a PostgreSQL")
    ap.add_argument("destino", help="URL de PostgreSQL")
    ap.add_argument("--origen", default="db.sqlite3")
    ap.add_argument("--solo-revisar", action="store_true")
    ap.add_argument("--reemplazar", action="store_true")
    args = ap.parse_args()

    origen = Path(args.origen)
    if not origen.exists():
        sys.exit(f"No encuentro {origen}. Ejecuta el script desde la carpeta donde está db.sqlite3.")

    # SQLite en modo solo lectura
    motor_origen = create_engine(
        "sqlite://", creator=lambda: sqlite3.connect(f"file:{origen.resolve().as_posix()}?mode=ro", uri=True)
    )
    motor_destino = create_engine(url_postgres(args.destino), pool_pre_ping=True)

    tablas = list(SQLModel.metadata.sorted_tables)  # respeta el orden de las llaves foráneas

    # Columnas que existen realmente en el SQLite de origen
    with motor_origen.connect() as co:
        existentes = {r[0] for r in co.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}

    plan = []
    with motor_origen.connect() as co:
        for t in tablas:
            if t.name not in existentes:
                plan.append((t, [], 0))
                continue
            cols_origen = {r[1] for r in co.execute(text(f'PRAGMA table_info("{t.name}")'))}
            comunes = [c.name for c in t.columns if c.name in cols_origen]
            faltan = [c.name for c in t.columns if c.name not in cols_origen]
            if faltan:
                print(f"  Aviso: en {t.name} faltan columnas en el origen ({', '.join(faltan)}); se usará su valor por defecto.")
            n = co.execute(text(f'SELECT COUNT(*) FROM "{t.name}"')).scalar()
            plan.append((t, comunes, n))

    print("Filas a copiar:")
    for t, _, n in plan:
        print(f"  {t.name:<18} {n}")
    if args.solo_revisar:
        print("\nModo revisión: no se escribió nada.")
        return

    SQLModel.metadata.create_all(motor_destino)

    with motor_destino.begin() as cd:
        ocupadas = {
            t.name: cd.execute(select(func.count()).select_from(t)).scalar() for t, _, _ in plan
        }
        con_datos = {k: v for k, v in ocupadas.items() if v}
        if con_datos and not args.reemplazar:
            sys.exit(
                "El destino YA tiene datos: "
                + ", ".join(f"{k}={v}" for k, v in con_datos.items())
                + "\nNo se copió nada. Si quieres borrarlos y empezar de nuevo, agrega --reemplazar."
            )
        if con_datos:
            print("\nBorrando los datos que había en el destino...")
            for t, _, _ in reversed(plan):
                cd.execute(t.delete())

        # Todo en una sola transacción: si algo falla, el destino queda como estaba.
        print("\nCopiando...")
        with motor_origen.connect() as co:
            for t, comunes, n in plan:
                if not n:
                    continue
                cols = ", ".join(f'"{c}"' for c in comunes)
                res = co.execute(text(f'SELECT {cols} FROM "{t.name}"'))
                total = 0
                while True:
                    filas = res.fetchmany(LOTE)
                    if not filas:
                        break
                    lote = []
                    for fila in filas:
                        d = dict(zip(comunes, fila))
                        for c in t.columns:  # SQLite guarda booleanos como 0/1 y fechas como texto
                            v = d.get(c.name)
                            if v is None:
                                continue
                            if isinstance(c.type, Boolean):
                                d[c.name] = bool(v)
                            elif isinstance(v, str) and isinstance(c.type, DateTime):
                                d[c.name] = datetime.fromisoformat(v)
                            elif isinstance(v, str) and isinstance(c.type, Date):
                                d[c.name] = date.fromisoformat(v[:10])
                        lote.append(d)
                    cd.execute(t.insert(), lote)
                    total += len(lote)
                print(f"  {t.name:<18} {total}")

        # Ajusta los contadores de id para que los registros nuevos no repitan ids
        for t, _, _ in plan:
            if "id" in t.columns:
                cd.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('\"{t.name}\"', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM \"{t.name}\"), 1), "
                    f"(SELECT MAX(id) FROM \"{t.name}\") IS NOT NULL)"
                ))

    # Verificación final
    print("\nVerificación (origen vs destino):")
    ok = True
    with motor_destino.connect() as cd:
        for t, _, n in plan:
            m = cd.execute(select(func.count()).select_from(t)).scalar()
            marca = "OK" if m == n else "¡NO COINCIDE!"
            ok &= m == n
            print(f"  {t.name:<18} {n:>5} -> {m:>5}  {marca}")
    if not ok:
        sys.exit("\nAlgunas tablas no coinciden. Revisa antes de usar la base.")
    print("\nMigración terminada correctamente.")


if __name__ == "__main__":
    main()
