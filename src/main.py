import os
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from db import crear_tablas
import usuarios, categoria,productos,unidades_medidas,compras,lotes,inventario,consumo,alertas,estadisticas
from fastapi.middleware.cors import CORSMiddleware

app=FastAPI(lifespan=crear_tablas)
app.include_router(usuarios.router)
app.include_router(categoria.router)
app.include_router(productos.router)
app.include_router(unidades_medidas.router)
app.include_router(compras.router)
app.include_router(lotes.router)
app.include_router(inventario.router)
app.include_router(consumo.router)
app.include_router(alertas.router)
app.include_router(estadisticas.router)

# Orígenes permitidos (frontend). En producción se define CORS_ORIGINS en el entorno,
# separando varias URL con comas. Ej.: https://alacena.vercel.app
ORIGENES_PERMITIDOS = [
    o.strip().rstrip("/")
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES_PERMITIDOS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
