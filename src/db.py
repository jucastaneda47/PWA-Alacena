import os
from sqlmodel import Session, create_engine, SQLModel
from typing import Annotated
from fastapi import FastAPI, Depends


def _url_de_base_de_datos() -> str:
    """
    Elige la base de datos según la variable de entorno DATABASE_URL.
    - Sin DATABASE_URL (desarrollo local): SQLite, archivo db.sqlite3 (como siempre).
    - Con DATABASE_URL (producción): PostgreSQL. Los proveedores entregan la URL como
      "postgres://..." o "postgresql://...", y aquí se ajusta al driver psycopg.
    """
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return "sqlite:///db.sqlite3"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


database_url = _url_de_base_de_datos()
es_sqlite = database_url.startswith("sqlite")

if es_sqlite:
    engine = create_engine(database_url)
else:
    # pool_pre_ping: revisa que la conexión siga viva antes de usarla
    # (los servicios gratuitos cierran las conexiones inactivas).
    engine = create_engine(database_url, pool_pre_ping=True)


def chat():
    with Session(engine) as sesion:
        yield sesion

sesiondb=Annotated[Session,Depends(chat)]

from contextlib import asynccontextmanager

@asynccontextmanager
async def crear_tablas(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield
