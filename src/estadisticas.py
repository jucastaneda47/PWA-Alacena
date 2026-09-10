from datetime import date, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlmodel import select
from db import sesiondb
from modelos import lotedb, compradb, transacciondb, usuariodb
from usuarios import confirmacion

router = APIRouter()

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


@router.get("/estadisticas/movimientos", tags=["estadisticas"])
async def compras_vs_consumo(
    conexion: sesiondb,
    periodo: str = "semana",
    cantidad_periodos: int = 6,
    usuario: usuariodb = Depends(confirmacion),
):
    """
    Compara, período a período, cuántas compras se registraron (número de
    lotes creados) contra cuántos consumos se registraron (número de
    transacciones tipo='consumo'). Cuenta EVENTOS, no cantidades sumadas,
    para no mezclar unidades distintas (kg, L, unidades) en un solo número.
    """
    if periodo not in ("semana", "mes"):
        periodo = "semana"

    lotes_con_compra = conexion.exec(
        select(lotedb, compradb)
        .join(compradb, lotedb.compra_id == compradb.id)
        .where(lotedb.usuario_id == usuario.id)
    ).all()

    transacciones = conexion.exec(
        select(transacciondb).where(
            transacciondb.usuario_id == usuario.id,
            transacciondb.tipo == "consumo",
        )
    ).all()

    compras_por_periodo = defaultdict(int)
    for _lote, compra in lotes_con_compra:
        compras_por_periodo[_clave_periodo(compra.fecha_compra, periodo)] += 1

    consumo_por_periodo = defaultdict(int)
    for t in transacciones:
        consumo_por_periodo[_clave_periodo(t.fecha.date(), periodo)] += 1

    claves = _generar_claves(periodo, cantidad_periodos)

    return [
        {
            "periodo": _etiqueta_periodo(clave, periodo),
            "compras": compras_por_periodo.get(clave, 0),
            "consumos": consumo_por_periodo.get(clave, 0),
        }
        for clave in claves
    ]