"""
Estadísticas de FreshLog, divididas por pantalla (cada archivo es un módulo):

    tablero.py      -> Tablero
    compras.py      -> Compras e inventario
    consumo.py      -> Consumo y vencimientos
    seguimiento.py  -> Alertas y seguimiento
    comunes.py      -> funciones auxiliares compartidas (no tiene rutas)

Las direcciones de la API no cambian: todas siguen empezando por /estadisticas.
"""
from fastapi import APIRouter

from . import tablero, compras, consumo, seguimiento

router = APIRouter()
for _modulo in (tablero, compras, consumo, seguimiento):
    router.include_router(_modulo.router)
