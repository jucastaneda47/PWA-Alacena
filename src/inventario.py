from fastapi import APIRouter, Depends
from sqlmodel import select
from db import sesiondb
from modelos import lotedb, productodb, categoriadb, unidadmedidadb, usuariodb
from usuarios import confirmacion
from clasificacion import calcular_estado, calcular_dias_restantes

router = APIRouter()


@router.get("/inventario", tags=["inventario"])
async def consultar_inventario(
    conexion: sesiondb,
    categoria_id: int | None = None,
    estado: str | None = None,
    usuario: usuariodb = Depends(confirmacion),
):

    consulta = (
        select(lotedb, productodb, categoriadb, unidadmedidadb)
        .join(productodb, lotedb.producto_id == productodb.id)
        .join(categoriadb, productodb.categoria_id == categoriadb.id)
        .join(unidadmedidadb, productodb.unidad_de_medida_id == unidadmedidadb.id)
        .where(lotedb.usuario_id == usuario.id, lotedb.cantidad_actual > 0)
        .order_by(lotedb.fecha_vencimiento.asc())
    )

    if categoria_id is not None:
        consulta = consulta.where(productodb.categoria_id == categoria_id)

    resultados = conexion.exec(consulta).all()

    respuesta = []
    for lote, producto, categoria, unidad in resultados:
        nuevo_estado = calcular_estado(lote.fecha_vencimiento)
        if nuevo_estado != lote.estado:
            lote.estado = nuevo_estado
            conexion.add(lote)

        if estado is not None and lote.estado != estado:
            continue

        respuesta.append(
            {
                "lote_id": lote.id,
                "producto_id": producto.id,
                "producto_nombre": producto.nombre,
                "categoria_id": producto.categoria_id,
                "categoria_nombre": categoria.nombre,
                "unidad_abreviatura": unidad.abreviatura,
                "cantidad_inicial": lote.cantidad_inicial,
                "cantidad_actual": lote.cantidad_actual,
                "fecha_vencimiento": lote.fecha_vencimiento,
                "dias_restantes": calcular_dias_restantes(lote.fecha_vencimiento),
                "estado": lote.estado,
            }
        )

    conexion.commit()
    return respuesta