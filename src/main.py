from fastapi import FastAPI
from db import crear_tablas
import modelos
import usuarios,correo, categoria
from fastapi.middleware.cors import CORSMiddleware

app=FastAPI(lifespan=crear_tablas)
app.include_router(usuarios.router)
app.include_router(categoria.router)
@app.get("/")
async def sapohp():
    return ("holka sapo hp")
app.include_router(correo.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
