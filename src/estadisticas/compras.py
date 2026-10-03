"""Estadísticas de la pantalla Compras e inventario: distribución del stock por categoría y comprado vs. consumido.

La distribución por categorías también la usa el Tablero (misma ruta /estadisticas/distribucion-categorias).
"""
from collections import defaultdict
from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select
from db import sesiondb
from modelos import lotedb, transacciondb, categoriadb, productodb, usuariodb
from usuarios import confirmacion
from .comunes import _productos_en_inventario

router = APIRouter()


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


@router.get("/estadisticas/comprado-vs-consumido-categoria", tags=["estadisticas"])
async def comprado_vs_consumido_por_categoria(
    conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)
):
    """
    Módulo Compras e inventario. Por cada categoría con actividad, cuántas
    veces se compró (lotes registrados) contra cuántas veces se consumió
    (transacciones tipo='consumo', igual criterio que el gráfico de
    Movimientos — 'retiro' no cuenta como consumo). Histórico total, sin
    filtro de fecha.
    """
    filas = conexion.exec(
        select(lotedb, productodb, categoriadb)
        .join(productodb, lotedb.producto_id == productodb.id)
        .join(categoriadb, productodb.categoria_id == categoriadb.id)
        .where(lotedb.usuario_id == usuario.id)
    ).all()

    if not filas:
        return []

    lote_a_categoria = {lote.id: categoria for lote, _producto, categoria in filas}
    categorias_info = {categoria.id: categoria for _lote, _producto, categoria in filas}

    comprados = defaultdict(int)
    for lote, _producto, categoria in filas:
        comprados[categoria.id] += 1

    transacciones = conexion.exec(
        select(transacciondb).where(
            transacciondb.usuario_id == usuario.id,
            transacciondb.tipo == "consumo",
        )
    ).all()
    consumidos = defaultdict(int)
    for t in transacciones:
        categoria = lote_a_categoria.get(t.lote_id)
        if categoria:
            consumidos[categoria.id] += 1

    categorias_con_datos = set(comprados) | set(consumidos)
    resultado = [
        {
            "categoria_id": cat_id,
            "categoria_nombre": categorias_info[cat_id].nombre,
            "color": categorias_info[cat_id].color,
            "icono": categorias_info[cat_id].icono,
            "comprados": comprados.get(cat_id, 0),
            "consumidos": consumidos.get(cat_id, 0),
        }
        for cat_id in categorias_con_datos
    ]
    resultado.sort(key=lambda x: x["comprados"] + x["consumidos"], reverse=True)
    return resultado
