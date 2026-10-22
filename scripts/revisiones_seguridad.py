"""
Revisiones de seguridad del backend de FreshLog (Alacena).

Repite las 33 revisiones (SG-01 a SG-33) de la Tabla 106 de la monografía.
Llama a la API como lo haría alguien que intentara abusar de ella: sin sesión,
con tokens falsos, con datos de otro usuario, con cargas de inyección SQL, etc.

Es seguro ejecutarlo:
  - Usa una base de datos SQLite EN MEMORIA: nunca toca tu db.sqlite3 ni Neon.
  - Reemplaza el envío de correos por una bandeja falsa: no manda correos.
  - Aborta si detecta que el motor de base de datos no es el de memoria.

Cómo ejecutarlo (desde la carpeta del backend, la que contiene "src"):

    uv run python scripts/revisiones_seguridad.py

Guarda también el resultado completo en revisiones_seguridad_resultado.txt
"""
import base64
import json
import os
import sys
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

warnings.filterwarnings("ignore")  # avisos de versiones; no afectan el resultado

# --- Entorno de prueba: debe quedar listo ANTES de importar la aplicación ---
os.environ.setdefault("EMAIL_SENDER", "pruebas.freshlog@gmail.com")
os.environ.setdefault("EMAIL_APP_PASSWORD", "clave-de-prueba")
os.environ.setdefault("JWT_SECRET", "clave-solo-para-pruebas-no-usar-en-produccion")
os.environ["DATABASE_URL"] = ""  # nunca usar la base de datos real

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

import db  # noqa: E402

motor = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
db.engine = motor  # el motor de pruebas se instala antes de importar main

import main  # noqa: E402
import usuarios  # noqa: E402
from modelos import categoriadb, compradb, lotedb, productodb, usuariodb  # noqa: E402

if str(db.engine.url) != "sqlite://":
    sys.exit("ABORTADO: el motor no es la base de datos en memoria.")

SECRETO = usuarios.algo2
ALGORITMO = usuarios.algo
CLAVE = "Segura123!"

# --- Correos falsos (se guardan en una bandeja en vez de enviarse) ---
bandeja = {"pines": [], "recuperaciones": []}


async def _pin_falso(destinatario, pin):
    bandeja["pines"].append((destinatario, pin))


async def _recuperacion_falsa(destinatario, token):
    bandeja["recuperaciones"].append((destinatario, token))


usuarios.enviar_pin_verificacion = _pin_falso
usuarios.enviar_correo_recuperacion = _recuperacion_falsa

SQLModel.metadata.drop_all(motor)
SQLModel.metadata.create_all(motor)
cli = TestClient(main.app)

# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
resultados = []  # (codigo, prueba, esperado, obtenido, resultado)


def registrar(codigo, prueba, esperado, obtenido, aprobada, observacion=False):
    if observacion:
        estado = "Aprobada" if aprobada else "Observación"
    else:
        estado = "Aprobada" if aprobada else "FALLÓ"
    resultados.append((codigo, prueba, esperado, str(obtenido), estado))


def cab(token):
    return {"Authorization": f"Bearer {token}"}


def fecha(dias):
    return str(date.today() + timedelta(days=dias))


def registrar_usuario(username, verificar=True):
    correo = f"{username}@correo.com"
    r = cli.post("/usuario", json={"name": username.title(), "correo": correo,
                                   "username": username, "contraseña": CLAVE})
    assert r.status_code == 200, r.text
    pin = bandeja["pines"][-1][1]
    if verificar:
        r = cli.post("/verificar-pin", json={"correo": correo, "pin": pin})
        assert r.status_code == 200, r.text
        r = cli.post("/login", data={"username": username, "password": CLAVE})
        assert r.status_code == 200, r.text
        return {"username": username, "correo": correo, "token": r.json()["access_token"]}
    return {"username": username, "correo": correo, "pin": pin, "token": None}


def cat_id(usuario, nombre):
    for c in cli.get("/categorias", headers=cab(usuario["token"])).json():
        if c["nombre"] == nombre:
            return c["id"]


def uni_id(usuario, nombre):
    for u in cli.get("/unidades-medida", headers=cab(usuario["token"])).json():
        if u["nombre"] == nombre:
            return u["id"]


def sembrar(usuario, nombre):
    """Crea compra + producto + lote para un usuario y devuelve sus ids."""
    h = cab(usuario["token"])
    compra = cli.post("/compras", json={}, headers=h).json()
    prod = cli.post("/productos", headers=h, json={
        "nombre": nombre, "categoria_id": cat_id(usuario, "Lácteos"),
        "unidad_de_medida_id": uni_id(usuario, "Litro")}).json()
    lote = cli.post("/lotes", headers=h, json={
        "producto_id": prod["id"], "compra_id": compra["id"],
        "fecha_vencimiento": fecha(10), "cantidad_inicial": 5}).json()
    return {"compra": compra["id"], "producto": prod["id"], "lote": lote["id"]}


def contar(tabla):
    with Session(motor) as s:
        return len(s.exec(select(tabla)).all())


def b64(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


# ----------------------------------------------------------------------------
# Preparación: tres usuarios (A y B verificados, C sin verificar)
# ----------------------------------------------------------------------------
A = registrar_usuario("ana")
B = registrar_usuario("beto")
C = registrar_usuario("carla", verificar=False)
datos_a = sembrar(A, "Leche de Ana")
datos_b = sembrar(B, "Arroz de Beto")
hA, hB = cab(A["token"]), cab(B["token"])

# ----------------------------------------------------------------------------
# Autenticación y rutas protegidas
# ----------------------------------------------------------------------------
rutas_get = ["/autorizado", "/categorias", "/unidades-medida", "/productos", "/lotes",
             "/compras", "/inventario", "/consumo", "/alertas",
             "/estadisticas/movimientos", "/estadisticas/desperdicio",
             "/estadisticas/historial", "/estadisticas/ranking-productos"]
codigos = [cli.get(r).status_code for r in rutas_get]
registrar("SG-01", f"GET sin token en {len(rutas_get)} rutas protegidas", "401 en todas",
          "401" if set(codigos) == {401} else codigos, set(codigos) == {401})

escrituras = [
    cli.post("/categorias", json={"nombre": "X"}),
    cli.post("/productos", json={"nombre": "X", "categoria_id": 1, "unidad_de_medida_id": 1}),
    cli.post("/compras", json={}),
    cli.post("/consumo", json={"lote_id": 1, "cantidad": 1}),
    cli.put("/categorias/1", json={"nombre": "Y"}),
    cli.delete("/compras/1"),
]
cods = [r.status_code for r in escrituras]
registrar("SG-02", "Escrituras (POST/PUT/DELETE) sin token", "401 en todas",
          ", ".join(map(str, cods)), set(cods) == {401})

exp = datetime.now(timezone.utc) + timedelta(minutes=10)
t_otra_clave = jwt.encode({"sub": "1", "exp": exp}, "otra-clave-distinta", algorithm=ALGORITMO)
r = cli.get("/autorizado", headers=cab(t_otra_clave))
registrar("SG-03", "Token firmado con otra clave", "401", r.status_code, r.status_code == 401)

t_vencido = jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                       SECRETO, algorithm=ALGORITMO)
r = cli.get("/autorizado", headers=cab(t_vencido))
registrar("SG-04", "Token expirado (firma válida)", "401",
          f"{r.status_code} {r.json().get('detail', '')}", r.status_code == 401)

t_none = (b64({"alg": "none", "typ": "JWT"}) + "." +
          b64({"sub": "1", "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())}) + ".")
r = cli.get("/autorizado", headers=cab(t_none))
registrar("SG-05", "Token con algoritmo 'none'", "401", r.status_code, r.status_code == 401)

cabecera, _carga, firma = A["token"].split(".")
carga_falsa = b64({"sub": "2", "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())})
r = cli.get("/autorizado", headers=cab(f"{cabecera}.{carga_falsa}.{firma}"))
registrar("SG-06", "Token con el 'sub' cambiado a mano (firma original)", "401",
          r.status_code, r.status_code == 401)

# ----------------------------------------------------------------------------
# Contraseñas y datos sensibles
# ----------------------------------------------------------------------------
with Session(motor) as s:
    hashes = [u.contraseña for u in s.exec(select(usuariodb)).all()]
todos_argon = all(h.startswith("$argon2") for h in hashes)
registrar("SG-07", "Contraseñas guardadas en la base de datos", "Hash argon2, nunca texto plano",
          f"{len(hashes)} registros, todos inician con $argon2: {todos_argon}", todos_argon)

campos = sorted(cli.get("/autorizado", headers=hA).json().keys())
prohibidos = {"contraseña", "pin_verificacion", "pin_expiracion",
              "token_recuperacion", "token_recuperacion_expiracion", "access_token"}
registrar("SG-08", "Respuesta de /autorizado", "Sin contraseña, PIN ni token de recuperación",
          f"{len(campos)} campos, ninguno sensible", not (prohibidos & set(campos)))

# ----------------------------------------------------------------------------
# Inicio de sesión
# ----------------------------------------------------------------------------
r1 = cli.post("/login", data={"username": "no_existe_xyz", "password": CLAVE})
r2 = cli.post("/login", data={"username": "ana", "password": "ClaveMala123!"})
ok = (r1.status_code == r2.status_code == 401) and (r1.json()["detail"] == r2.json()["detail"])
registrar("SG-09", "Login con usuario inexistente vs. clave errónea", "Mismo código y mismo mensaje",
          f"{r1.status_code}/{r2.status_code}: '{r1.json()['detail']}'", ok)

r = cli.post("/login", data={"username": "carla", "password": CLAVE})
registrar("SG-10", "Login de cuenta sin verificar", "403", r.status_code, r.status_code == 403)

usuarios_antes = contar(usuariodb)
cargas = ["' OR '1'='1", "admin'--", "' OR 1=1 --", "'; DROP TABLE usuariodb; --"]
cods = [cli.post("/login", data={"username": c, "password": "x"}).status_code for c in cargas]
ok = set(cods) == {401} and contar(usuariodb) == usuarios_antes
registrar("SG-11", f"Inyección SQL en el formulario de login ({len(cargas)} cargas)",
          "401 sin acceso y tabla intacta", f"códigos {cods}; usuarios en tabla: {contar(usuariodb)}", ok)

lotes_antes = contar(lotedb)
cargas = ["x'); DROP TABLE lotedb; --", "' OR '1'='1", "Robert'); DELETE FROM categoriadb; --"]
cods = [cli.post("/categorias", headers=hA, json={"nombre": c}).status_code for c in cargas]
cli.get("/inventario", headers=hA, params={"estado": "' OR '1'='1"})
cli.get("/inventario", headers=hA, params={"categoria_id": "1 OR 1=1"})
ok = contar(lotedb) == lotes_antes and contar(categoriadb) >= 1 and set(cods) == {200}
registrar("SG-12", "Inyección SQL en nombre de categoría y filtro de inventario",
          "Se trata como texto; tablas intactas",
          f"POST categorías {cods}; lotes={contar(lotedb)}; categorías={contar(categoriadb)}", ok)

# ----------------------------------------------------------------------------
# Aislamiento entre usuarios (B intenta tocar datos de A)
# ----------------------------------------------------------------------------
def b_contra_a(codigo, prueba, respuesta):
    registrar(codigo, prueba, "404", respuesta.status_code, respuesta.status_code == 404)

b_contra_a("SG-13", "Usuario B pide un lote de A (GET /lotes/{id})",
           cli.get(f"/lotes/{datos_a['lote']}", headers=hB))
b_contra_a("SG-14", "Usuario B pide una compra de A",
           cli.get(f"/compras/{datos_a['compra']}", headers=hB))
b_contra_a("SG-15", "Usuario B pide un producto de A",
           cli.get(f"/productos/{datos_a['producto']}", headers=hB))
cat_a = cat_id(A, "Lácteos")
b_contra_a("SG-16", "Usuario B pide una categoría de A",
           cli.get(f"/categorias/{cat_a}", headers=hB))
b_contra_a("SG-17", "Usuario B consume un lote de A",
           cli.post("/consumo", headers=hB, json={"lote_id": datos_a["lote"], "cantidad": 1}))
b_contra_a("SG-18", "Usuario B elimina una compra de A",
           cli.delete(f"/compras/{datos_a['compra']}", headers=hB))
b_contra_a("SG-19", "Usuario B edita una categoría de A",
           cli.put(f"/categorias/{cat_a}", headers=hB, json={"nombre": "Hackeada"}))

lotes_b_antes = len([x for x in cli.get("/lotes", headers=hB).json()])
r = cli.post("/compras/sincronizar", headers=hB, json={
    "cliente_id": "cliente-robo-0001", "fecha_compra": str(date.today()),
    "lineas": [{"producto_id": datos_a["producto"], "fecha_vencimiento": fecha(10),
                "cantidad_inicial": 1}]})
lotes_b_despues = len(cli.get("/lotes", headers=hB).json())
registrar("SG-20", "Usuario B sincroniza una compra con un producto de A",
          "400, sin crear lotes", f"{r.status_code} {r.json().get('detail', '')}",
          r.status_code == 400 and lotes_b_despues == lotes_b_antes)

lotes_b = cli.get("/lotes", headers=hB).json()
prods_b = cli.get("/productos", headers=hB).json()
compras_b = cli.get("/compras", headers=hB).json()
limpio = (datos_a["lote"] not in [x["id"] for x in lotes_b]
          and datos_a["producto"] not in [x["id"] for x in prods_b]
          and datos_a["compra"] not in [x["id"] for x in compras_b])
registrar("SG-21", "Listados de B no contienen datos de A", "Solo registros propios de B",
          f"B ve lotes={len(lotes_b)}, productos={len(prods_b)}, compras={len(compras_b)}", limpio)

inv_b = cli.get("/inventario", headers=hB).json()
ids_inv_b = [x["lote_id"] for x in inv_b]
registrar("SG-22", "Inventario de B", "Solo lotes de B",
          f"{len(inv_b)} lotes", datos_a["lote"] not in ids_inv_b and datos_b["lote"] in ids_inv_b)

# ----------------------------------------------------------------------------
# Registro, PIN y recuperación
# ----------------------------------------------------------------------------
malas = ["Corta1!", "sinmayuscula1!", "SINMINUSCULA1!", "SinNumeros!!", "SinEspecial123"]
cods = [cli.post("/usuario", json={"name": "X", "correo": f"x{i}@correo.com",
                                    "username": f"x{i}", "contraseña": m}).status_code
        for i, m in enumerate(malas)]
registrar("SG-23", f"Registro con {len(malas)} contraseñas que incumplen las reglas",
          "422 en todas", ", ".join(map(str, cods)), set(cods) == {422})

r = cli.post("/usuario", json={"name": "Otra", "correo": "ana@correo.com",
                                "username": "otra_ana", "contraseña": CLAVE})
registrar("SG-24", "Registro con correo ya existente", "400",
          f"{r.status_code} {r.json().get('detail', '')}", r.status_code == 400)

r = cli.post("/usuario", json={"name": "Otra", "correo": "otra@correo.com",
                                "username": "ANA", "contraseña": CLAVE})
registrar("SG-25", "Registro con usuario existente en otras mayúsculas", "400",
          r.status_code, r.status_code == 400)

pin_malo = "000000" if C["pin"] != "000000" else "111111"
r = cli.post("/verificar-pin", json={"correo": C["correo"], "pin": pin_malo})
registrar("SG-26", "PIN incorrecto", "400", f"{r.status_code} {r.json().get('detail', '')}",
          r.status_code == 400)

r = cli.post("/restablecer-contrasena", json={"token": "token-inventado-123",
                                               "nueva_contraseña": "Nueva123!"})
registrar("SG-27", "Restablecer con token inventado", "400", r.status_code, r.status_code == 400)

r = cli.put("/avatar", headers=hA, json={"avatar": "<script>alert(1)</script>"})
registrar("SG-28", "Avatar con valor fuera del catálogo (XSS)", "422", r.status_code,
          r.status_code == 422)

# ----------------------------------------------------------------------------
# CORS y renovación de sesión
# ----------------------------------------------------------------------------
origen_ok = main.ORIGENES_PERMITIDOS[0]
r = cli.options("/login", headers={"Origin": "http://sitio-malicioso.example",
                                   "Access-Control-Request-Method": "POST"})
permiso = r.headers.get("access-control-allow-origin")
registrar("SG-29", "CORS: petición desde origen no autorizado",
          "Sin cabecera Access-Control-Allow-Origin", f"{r.status_code}; allow-origin={permiso}",
          permiso is None)

r = cli.options("/login", headers={"Origin": origen_ok, "Access-Control-Request-Method": "POST"})
permiso = r.headers.get("access-control-allow-origin")
registrar("SG-30", "CORS: petición desde origen autorizado",
          "Cabecera con el origen permitido", f"allow-origin={permiso}", permiso == origen_ok)

r = cli.post("/renovar-sesion", headers=hA)
registrar("SG-31", "Renovación de sesión con token vigente", "200 con token nuevo",
          r.status_code, r.status_code == 200 and "access_token" in r.json())

# ----------------------------------------------------------------------------
# Observaciones (pueden quedar como debilidades pendientes)
# ----------------------------------------------------------------------------
cods = [cli.post("/login", data={"username": "ana", "password": "ClaveMala123!"}).status_code
        for _ in range(15)]
hubo_bloqueo = any(c in (423, 429) for c in cods) or cods[-1] != 401
registrar("SG-32", "15 intentos seguidos de login con clave errónea",
          "(Observación) ¿se bloquea la cuenta?",
          (f"{sorted(set(cods))}: " + ("hay bloqueo" if hubo_bloqueo else "no hay bloqueo por intentos")),
          hubo_bloqueo, observacion=True)

r_ok = cli.post("/recuperar-contrasena", json={"correo": "ana@correo.com"})
r_no = cli.post("/recuperar-contrasena", json={"correo": "nadie@correo.com"})
mismo = r_ok.status_code == r_no.status_code and r_ok.json() == r_no.json()
registrar("SG-33", "Recuperación con correo no registrado",
          "(Observación) ¿mismo mensaje que con correo válido?",
          (f"{r_no.status_code} {r_no.json().get('detail', '')}: " +
           ("responde igual" if mismo else "revela que el correo no existe")),
          mismo, observacion=True)

# ----------------------------------------------------------------------------
# Informe
# ----------------------------------------------------------------------------
resultados.sort(key=lambda x: x[0])
aprobadas = sum(1 for r in resultados if r[4] == "Aprobada")
observ = sum(1 for r in resultados if r[4] == "Observación")
fallos = sum(1 for r in resultados if r[4] == "FALLÓ")


def corto(t, n):
    t = " ".join(t.split())
    return t if len(t) <= n else t[: n - 1] + "…"


lineas = []
lineas.append("REVISIONES DE SEGURIDAD - FreshLog (backend)")
lineas.append(f"Fecha: {datetime.now():%Y-%m-%d %H:%M:%S}   Python {sys.version.split()[0]}   "
              f"Base de datos: SQLite en memoria")
lineas.append("-" * 122)
lineas.append(f"{'Código':<6} {'Resultado':<11} {'Prueba':<50} {'Obtenido':<52}")
lineas.append("-" * 122)
for cod, prueba, esperado, obtenido, estado in resultados:
    lineas.append(f"{cod:<6} {estado:<11} {corto(prueba, 50):<50} {corto(obtenido, 52):<52}")
lineas.append("-" * 122)
lineas.append(f"Total: {len(resultados)} revisiones | Aprobadas: {aprobadas} | "
              f"Observaciones: {observ} | Fallidas: {fallos}")

texto = "\n".join(lineas)
print(texto)
try:
    (RAIZ / "revisiones_seguridad_resultado.txt").write_text(texto + "\n", encoding="utf-8")
    print("\nResultado guardado en revisiones_seguridad_resultado.txt")
except OSError:
    pass

SQLModel.metadata.drop_all(motor)
sys.exit(1 if fallos else 0)
