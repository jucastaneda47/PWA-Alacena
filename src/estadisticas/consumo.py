"""Estadísticas de la pantalla Consumo y vencimientos: riesgo por categoría y aprovechamiento.
"""
from datetime import date
from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlmodel import select
from db import sesiondb
from modelos import lotedb, transacciondb, categoriadb, productodb, usuariodb
from usuarios import confirmacion
from clasificacion import calcular_estado, calcular_dias_restantes

router = APIRouter()


@router.get("/estadisticas/riesgo-categoria", tags=["estadisticas"])
async def riesgo_por_categoria(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    """
    Módulo Consumo y vencimientos. Cuenta, por categoría, cuántos lotes
    CON STOCK ACTUAL están en este momento próximos a vencer — los que
    ya vencieron no entran aquí, esos se resuelven aparte con un retiro.
    El estado se recalcula al vuelo (no se confía en el campo `estado`
    guardado, que solo se actualiza cuando se consulta /inventario).
    Incluye, por categoría, el detalle de qué productos están próximos
    a vencer y en cuántos días, para el cuadro al pasar el mouse.
    """
    filas = conexion.exec(
        select(lotedb, productodb, categoriadb)
        .join(productodb, lotedb.producto_id == productodb.id)
        .join(categoriadb, productodb.categoria_id == categoriadb.id)
        .where(lotedb.usuario_id == usuario.id, lotedb.cantidad_actual > 0)
    ).all()

    conteo = defaultdict(int)
    categorias_info = {}
    productos_por_categoria = defaultdict(list)
    for lote, producto, categoria in filas:
        estado = calcular_estado(lote.fecha_vencimiento)
        if estado == "proximo_a_vencer":
            conteo[categoria.id] += 1
            categorias_info[categoria.id] = categoria
            productos_por_categoria[categoria.id].append(
                {
                    "producto_nombre": producto.nombre,
                    "dias_restantes": calcular_dias_restantes(lote.fecha_vencimiento),
                }
            )

    resultado = [
        {
            "categoria_id": cat_id,
            "categoria_nombre": categorias_info[cat_id].nombre,
            "color": categorias_info[cat_id].color,
            "icono": categorias_info[cat_id].icono,
            "cantidad_lotes": cantidad,
            "productos": sorted(
                productos_por_categoria[cat_id], key=lambda p: p["dias_restantes"]
            ),
        }
        for cat_id, cantidad in conteo.items()
    ]
    resultado.sort(key=lambda x: x["cantidad_lotes"], reverse=True)
    return resultado


@router.get("/estadisticas/aprovechamiento", tags=["estadisticas"])
async def aprovechamiento_total(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    """
    Módulo Consumo y vencimientos. Sobre todos los lotes, cuántos se
    consumieron por completo sin necesitar retiro — "consumidos a
    tiempo", esto incluye los que se consumieron mientras el lote
    todavía estaba vigente, no solo los próximos a vencer — contra
    cuántos llegaron efectivamente a su fecha de vencimiento con
    cantidad sin consumir — "vencidos sin consumir". Una vez un lote
    está vencido ya no se puede registrar consumo sobre él — solo
    retiro — así que cualquier lote vencido con cantidad pendiente
    (retirada o no) cuenta como desperdicio. Los lotes vigentes o
    próximos a vencer que todavía tienen cantidad sin resolver se
    excluyen: su resultado aún no está definido. Incluye el detalle de
    productos de cada lado, para el cuadro al pasar el mouse.
    """
    hoy = date.today()
    filas = conexion.exec(
        select(lotedb, productodb)
        .join(productodb, lotedb.producto_id == productodb.id)
        .where(lotedb.usuario_id == usuario.id)
    ).all()

    if not filas:
        return {
            "aprovechados": 0,
            "desperdiciados": 0,
            "productos_aprovechados": [],
            "productos_desperdiciados": [],
        }

    ids_lotes = [lote.id for lote, _producto in filas]
    transacciones = conexion.exec(
        select(transacciondb).where(transacciondb.lote_id.in_(ids_lotes))
    ).all()

    tiene_retiro = {t.lote_id for t in transacciones if t.tipo == "retiro"}

    aprovechados = 0
    desperdiciados = 0
    conteo_aprovechados = defaultdict(int)
    conteo_desperdiciados = defaultdict(int)

    for lote, producto in filas:
        if lote.id in tiene_retiro:
            # Llegó a vencido con cantidad pendiente y hubo que retirarla.
            desperdiciados += 1
            conteo_desperdiciados[producto.nombre] += 1
            continue

        if lote.cantidad_actual <= 0:
            # Se consumió por completo sin necesitar retiro — sin
            # importar si eso pasó mientras estaba vigente o próximo a
            # vencer, en ambos casos se alcanzó a consumir a tiempo.
            aprovechados += 1
            conteo_aprovechados[producto.nombre] += 1
            continue

        # Todavía tiene cantidad sin consumir y sin retirar.
        if lote.fecha_vencimiento <= hoy:
            desperdiciados += 1
            conteo_desperdiciados[producto.nombre] += 1
        # Si está vigente, o próximo a vencer sin resolver todavía, no
        # se cuenta: su resultado aún no está definido.

    return {
        "aprovechados": aprovechados,
        "desperdiciados": desperdiciados,
        "productos_aprovechados": [
            {"producto_nombre": nombre, "cantidad": cantidad}
            for nombre, cantidad in sorted(
                conteo_aprovechados.items(), key=lambda par: par[1], reverse=True
            )
        ],
        "productos_desperdiciados": [
            {"producto_nombre": nombre, "cantidad": cantidad}
            for nombre, cantidad in sorted(
                conteo_desperdiciados.items(), key=lambda par: par[1], reverse=True
            )
        ],
    }
