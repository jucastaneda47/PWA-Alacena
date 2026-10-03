"""Funciones auxiliares compartidas por las estadísticas de todas las pantallas."""
from datetime import date, timedelta
from sqlmodel import select
from modelos import lotedb

MESES_ES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _clave_periodo(fecha: date, periodo: str):
    if periodo == "mes":
        return (fecha.year, fecha.month)
    iso_year, iso_week, _ = fecha.isocalendar()
    return (iso_year, iso_week)


def _etiqueta_periodo(clave, periodo: str) -> str:
    if periodo == "mes":
        anio, mes = clave
        return f"{MESES_ES[mes]} {anio}"
    _anio, semana = clave
    return f"Sem {semana}"


def _generar_claves(periodo: str, cantidad: int):
    hoy = date.today()
    claves = []
    if periodo == "mes":
        cursor = date(hoy.year, hoy.month, 1)
        for _ in range(cantidad):
            claves.append((cursor.year, cursor.month))
            cursor = (cursor - timedelta(days=1)).replace(day=1)
    else:
        cursor = hoy
        for _ in range(cantidad):
            claves.append(_clave_periodo(cursor, "semana"))
            cursor -= timedelta(weeks=1)
    claves.reverse()
    return claves


def _productos_en_inventario(conexion, usuario_id: int) -> set[int]:
    """IDs de productos que tienen al menos un lote con stock disponible ahora mismo."""
    ids = conexion.exec(
        select(lotedb.producto_id).where(
            lotedb.usuario_id == usuario_id, lotedb.cantidad_actual > 0
        )
    ).all()
    return set(ids)
