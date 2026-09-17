from datetime import date, timedelta
from collections import defaultdict
from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select
from db import sesiondb
from modelos import lotedb, compradb, transacciondb, categoriadb, productodb, usuariodb
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


def _productos_en_inventario(conexion, usuario_id: int) -> set[int]:
    """IDs de productos que tienen al menos un lote con stock disponible ahora mismo."""
    ids = conexion.exec(
        select(lotedb.producto_id).where(
            lotedb.usuario_id == usuario_id, lotedb.cantidad_actual > 0
        )
    ).all()
    return set(ids)


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


@router.get("/estadisticas/distribucion-categorias", tags=["estadisticas"])
async def distribucion_por_categoria(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    """
    Cuenta cuántos productos distintos tiene cada categoría, contando SOLO
    los que tienen stock disponible ahora mismo (al menos un lote con
    cantidad_actual > 0) — así refleja el inventario actual, no el
    catálogo histórico de productos que alguna vez se crearon.
    """
    ids_en_inventario = _productos_en_inventario(conexion, usuario.id)
    if not ids_en_inventario:
        return []

    categorias = conexion.exec(
        select(categoriadb).where(categoriadb.usuario_id == usuario.id)
    ).all()
    productos = conexion.exec(
        select(productodb).where(
            productodb.usuario_id == usuario.id,
            productodb.id.in_(ids_en_inventario),
        )
    ).all()

    conteo = defaultdict(int)
    for p in productos:
        conteo[p.categoria_id] += 1

    respuesta = []
    for c in categorias:
        cantidad = conteo.get(c.id, 0)
        if cantidad == 0:
            continue
        respuesta.append(
            {
                "categoria_id": c.id,
                "categoria_nombre": c.nombre,
                "color": c.color,
                "icono": c.icono,
                "cantidad_productos": cantidad,
            }
        )

    respuesta.sort(key=lambda x: x["cantidad_productos"], reverse=True)
    return respuesta


@router.get(
    "/estadisticas/distribucion-categorias/{categoria_id}/productos", tags=["estadisticas"]
)
async def productos_de_categoria(
    conexion: sesiondb, categoria_id: int, usuario: usuariodb = Depends(confirmacion)
):
    """
    Detalle al hacer clic en una porción: los productos de esa categoría
    que TIENEN STOCK ACTUAL, con cuántas veces se compró cada uno en total
    (histórico, número de lotes registrados alguna vez para ese producto).
    """
    categoria = conexion.get(categoriadb, categoria_id)
    if categoria is None or categoria.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada"
        )

    ids_en_inventario = _productos_en_inventario(conexion, usuario.id)
    if not ids_en_inventario:
        return []

    productos = conexion.exec(
        select(productodb).where(
            productodb.usuario_id == usuario.id,
            productodb.categoria_id == categoria_id,
            productodb.id.in_(ids_en_inventario),
        )
    ).all()

    lotes = conexion.exec(select(lotedb).where(lotedb.usuario_id == usuario.id)).all()
    conteo_lotes = defaultdict(int)
    for l in lotes:
        conteo_lotes[l.producto_id] += 1

    respuesta = [
        {
            "producto_id": p.id,
            "producto_nombre": p.nombre,
            "veces_comprado": conteo_lotes.get(p.id, 0),
        }
        for p in productos
    ]
    respuesta.sort(key=lambda x: x["veces_comprado"], reverse=True)
    return respuesta