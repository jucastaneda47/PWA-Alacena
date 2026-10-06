"""
Configuración común de las pruebas de FreshLog (Alacena).

- Usa una base de datos SQLite EN MEMORIA: nunca toca tu db.sqlite3 real.
- Reemplaza el envío de correos por una bandeja falsa, para poder leer los PIN
  y los enlaces de recuperación sin mandar correos de verdad.
- Cada prueba empieza con la base de datos vacía.
"""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Variables que correo.py necesita para construir la configuración de correo.
os.environ.setdefault("EMAIL_SENDER", "pruebas.freshlog@gmail.com")
os.environ.setdefault("EMAIL_APP_PASSWORD", "clave-de-prueba")
os.environ.setdefault("JWT_SECRET", "clave-solo-para-pruebas-no-usar-en-produccion")
# Las pruebas nunca deben usar la base de datos real, aunque el .env tenga DATABASE_URL.
os.environ["DATABASE_URL"] = ""

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# IMPORTANTE: el motor de pruebas se instala ANTES de importar el resto de los
# módulos, porque minimos.py guarda una referencia a db.engine al importarse.
import db

# Por defecto: SQLite en memoria. Para comprobar que todo funciona también en PostgreSQL,
# define PRUEBAS_DATABASE_URL con una base de datos VACÍA de pruebas (¡se borran sus tablas!).
_url_pg = os.environ.get("PRUEBAS_DATABASE_URL", "").strip()
if _url_pg:
    if _url_pg.startswith("postgresql://"):
        _url_pg = "postgresql+psycopg://" + _url_pg[len("postgresql://"):]
    motor_pruebas = create_engine(_url_pg)
else:
    motor_pruebas = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
db.engine = motor_pruebas

import main  # noqa: E402
import usuarios  # noqa: E402

CLAVE_VALIDA = "Segura123!"


@pytest.fixture(autouse=True)
def base_de_datos_limpia():
    """Crea las tablas vacías antes de cada prueba y las borra al terminar."""
    SQLModel.metadata.drop_all(motor_pruebas)
    SQLModel.metadata.create_all(motor_pruebas)
    yield
    SQLModel.metadata.drop_all(motor_pruebas)


@pytest.fixture
def sesion_bd():
    """Sesión directa a la base de datos de pruebas (para preparar o revisar datos)."""
    with Session(motor_pruebas) as s:
        yield s


@pytest.fixture(autouse=True)
def bandeja(monkeypatch):
    """Correos falsos: guarda lo que se 'enviaría' en vez de enviarlo."""
    caja = {"pines": [], "recuperaciones": []}

    async def pin_falso(destinatario, pin):
        caja["pines"].append((destinatario, pin))

    async def recuperacion_falsa(destinatario, token):
        caja["recuperaciones"].append((destinatario, token))

    monkeypatch.setattr(usuarios, "enviar_pin_verificacion", pin_falso)
    monkeypatch.setattr(usuarios, "enviar_correo_recuperacion", recuperacion_falsa)
    return caja


@pytest.fixture
def cliente():
    return TestClient(main.app)


class Sesion:
    """Un usuario ya registrado e iniciado, con atajos para llamar a la API."""

    def __init__(self, cliente, token, username):
        self.c = cliente
        self.token = token
        self.username = username

    @property
    def cabeceras(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, url, **kw):
        return self.c.get(url, headers=self.cabeceras, **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers=self.cabeceras, **kw)

    def put(self, url, **kw):
        return self.c.put(url, headers=self.cabeceras, **kw)

    def patch(self, url, **kw):
        return self.c.patch(url, headers=self.cabeceras, **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self.cabeceras, **kw)

    # ---- atajos de datos ----
    def categoria_id(self, nombre):
        for c in self.get("/categorias").json():
            if c["nombre"] == nombre:
                return c["id"]
        raise AssertionError(f"No existe la categoría {nombre}")

    def unidad_id(self, nombre):
        for u in self.get("/unidades-medida").json():
            if u["nombre"] == nombre:
                return u["id"]
        raise AssertionError(f"No existe la unidad {nombre}")

    def comprar(self, nombre, categoria="Lácteos", unidad="Litro", cantidad=2.0, dias=10, stock_minimo=None):
        """Registra compra + producto + lote. Devuelve los ids creados."""
        compra = self.post("/compras", json={}).json()
        cuerpo = {
            "nombre": nombre,
            "categoria_id": self.categoria_id(categoria),
            "unidad_de_medida_id": self.unidad_id(unidad),
        }
        if stock_minimo is not None:
            cuerpo["stock_minimo"] = stock_minimo
        producto = self.post("/productos", json=cuerpo).json()
        lote = self.post(
            "/lotes",
            json={
                "producto_id": producto["id"],
                "compra_id": compra["id"],
                "fecha_vencimiento": str(date.today() + timedelta(days=dias)),
                "cantidad_inicial": cantidad,
            },
        )
        assert lote.status_code == 200, lote.text
        return {"compra": compra["id"], "producto": producto["id"], "lote": lote.json()["id"]}


def registrar_y_entrar(cliente, bandeja, username, correo=None, clave=CLAVE_VALIDA):
    correo = correo or f"{username}@correo.com"
    r = cliente.post(
        "/usuario",
        json={"name": username.title(), "correo": correo, "username": username, "contraseña": clave},
    )
    assert r.status_code == 200, r.text
    pin = bandeja["pines"][-1][1]
    r = cliente.post("/verificar-pin", json={"correo": correo, "pin": pin})
    assert r.status_code == 200, r.text
    r = cliente.post("/login", data={"username": username, "password": clave})
    assert r.status_code == 200, r.text
    return Sesion(cliente, r.json()["access_token"], username)


@pytest.fixture
def ana(cliente, bandeja):
    return registrar_y_entrar(cliente, bandeja, "ana")


@pytest.fixture
def beto(cliente, bandeja):
    return registrar_y_entrar(cliente, bandeja, "beto")


@pytest.fixture
def fabrica_usuarios(cliente, bandeja):
    """Para crear usuarios con nombres propios dentro de una prueba."""
    return lambda username, **kw: registrar_y_entrar(cliente, bandeja, username, **kw)
