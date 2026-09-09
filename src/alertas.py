from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select
from db import sesiondb
from modelos import alertadb, lotedb, productodb, categoriadb, usuariodb
from usuarios import confirmacion
from clasificacion import calcular_estado

router = APIRouter()


def _sincronizar_alertas(conexion, usuario_id: int):
  
    lotes = conexion.exec(
        select(lotedb).where(lotedb.usuario_id == usuario_id, lotedb.cantidad_actual > 0)
    ).all()

    for lote in lotes:
        estado_actual = calcular_estado(lote.fecha_vencimiento)
        if estado_actual not in ("proximo_a_vencer", "vencido"):
            continue

        ya_existe = conexion.exec(
            select(alertadb).where(
                alertadb.usuario_id == usuario_id,
                alertadb.lote_id == lote.id,
                alertadb.tipo == estado_actual,
            )
        ).first()
        if ya_existe:
            continue

        conexion.add(
            alertadb(
                tipo=estado_actual,
                lote_id=lote.id,
                producto_id=lote.producto_id,
                usuario_id=usuario_id,
            )
        )

    productos = conexion.exec(
        select(productodb).where(productodb.usuario_id == usuario_id)
    ).all()

    for producto in productos:
        total_disponible = sum(l.cantidad_actual for l in lotes if l.producto_id == producto.id)

        if producto.stock_minimo is not None:
            minimo = producto.stock_minimo
        else:
            categoria = conexion.get(categoriadb, producto.categoria_id)
            minimo = categoria.stock_minimo if categoria else 0

        if total_disponible >= minimo:
            continue

        ya_existe = conexion.exec(
            select(alertadb).where(
                alertadb.usuario_id == usuario_id,
                alertadb.producto_id == producto.id,
                alertadb.lote_id == None,  # noqa: E711
                alertadb.tipo == "stock_minimo",
            )
        ).first()
        if ya_existe:
            continue

        conexion.add(alertadb(tipo="stock_minimo", producto_id=producto.id, usuario_id=usuario_id))

    conexion.commit()


@router.get("/alertas", tags=["alertas"])
async def listar_alertas(
    conexion: sesiondb,
    atendida: bool | None = None,
    usuario: usuariodb = Depends(confirmacion),
):

    _sincronizar_alertas(conexion, usuario.id)

    consulta = select(alertadb).where(alertadb.usuario_id == usuario.id)
    if atendida is not None:
        consulta = consulta.where(alertadb.atendida == atendida)
    consulta = consulta.order_by(alertadb.fecha_generada.desc())

    alertas = conexion.exec(consulta).all()

    respuesta = []
    for alerta in alertas:
        producto = conexion.get(productodb, alerta.producto_id) if alerta.producto_id else None
        respuesta.append(
            {
                "id": alerta.id,
                "tipo": alerta.tipo,
                "producto_id": alerta.producto_id,
                "producto_nombre": producto.nombre if producto else None,
                "lote_id": alerta.lote_id,
                "fecha_generada": alerta.fecha_generada,
                "atendida": alerta.atendida,
            }
        )
    return respuesta


@router.put("/alertas/{alerta_id}/atender", tags=["alertas"])
async def atender_alerta(
    conexion: sesiondb, alerta_id: int, usuario: usuariodb = Depends(confirmacion)
):
    """RF-19: Marca una alerta como atendida."""
    alerta = conexion.get(alertadb, alerta_id)
    if alerta is None or alerta.usuario_id != usuario.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada")

    alerta.atendida = True
    conexion.add(alerta)
    conexion.commit()
    conexion.refresh(alerta)
    return alerta