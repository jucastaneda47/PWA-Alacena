from sqlmodel import Session, create_engine, SQLModel
from typing import Annotated
from fastapi import FastAPI, Depends

sqlite_name="db.sqlite3"
sqlite_url=f"sqlite:///{sqlite_name}"
engine=create_engine(sqlite_url)
def chat():
    with Session(engine) as sesion:
        yield sesion 

sesiondb=Annotated[Session,Depends(chat)]

from contextlib import asynccontextmanager

@asynccontextmanager
async def crear_tablas(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield