from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select
from db import sesiondb
from modelos import alertadb, lotedb, productodb, categoriadb, unidadmedidadb, usuariodb
from usuarios import confirmacion
from clasificacion import calcular_estado

router = APIRouter()


def _calcular_stock_producto(conexion, producto):
    """Devuelve (cantidad_total_disponible, stock_minimo_efectivo) de un producto."""
    lotes = conexion.exec(
        select(lotedb).where(
            lotedb.usuario_id == producto.usuario_id,
            lotedb.producto_id == producto.id,
            lotedb.cantidad_actual > 0,
        )
    ).all()
    total = sum(l.cantidad_actual for l in lotes)

    if producto.stock_minimo is not None:
        minimo = producto.stock_minimo
    else:
        categoria = conexion.get(categoriadb, producto.categoria_id)
        minimo = categoria.stock_minimo if categoria else 0

    return total, minimo


def _sincronizar_alertas(conexion, usuario_id: int):
    """
    Revisa el inventario del usuario y crea las alertas que falten:
    - 'proximo_a_vencer' / 'vencido' por cada lote con stock disponible
    - 'stock_minimo' por cada producto cuyo stock total esté por debajo
      de su mínimo (propio, o heredado de su categoría si no tiene uno)

    No duplica: si ya existe una alerta de ese tipo para ese lote/producto
    (atendida o no), no genera otra.
    """
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
        total_disponible, minimo = _calcular_stock_producto(conexion, producto)

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
    """
    RF-16/17/18: sincroniza las alertas del usuario contra su inventario
    actual y las devuelve. Para las de tipo 'stock_minimo' agrega
    cantidad_actual, stock_minimo y unidad_abreviatura, para poder
    mostrarlas con detalle en el frontend sin otra consulta.
    """
    _sincronizar_alertas(conexion, usuario.id)

    consulta = select(alertadb).where(alertadb.usuario_id == usuario.id)
    if atendida is not None:
        consulta = consulta.where(alertadb.atendida == atendida)
    consulta = consulta.order_by(alertadb.fecha_generada.desc())

    alertas = conexion.exec(consulta).all()

    respuesta = []
    for alerta in alertas:
        producto = conexion.get(productodb, alerta.producto_id) if alerta.producto_id else None

        item = {
            "id": alerta.id,
            "tipo": alerta.tipo,
            "producto_id": alerta.producto_id,
            "producto_nombre": producto.nombre if producto else None,
            "lote_id": alerta.lote_id,
            "fecha_generada": alerta.fecha_generada,
            "atendida": alerta.atendida,
            "cantidad_actual": None,
            "stock_minimo": None,
            "unidad_abreviatura": None,
        }

        if alerta.tipo == "stock_minimo" and producto is not None:
            total, minimo = _calcular_stock_producto(conexion, producto)
            unidad = conexion.get(unidadmedidadb, producto.unidad_de_medida_id)
            item["cantidad_actual"] = total
            item["stock_minimo"] = minimo
            item["unidad_abreviatura"] = unidad.abreviatura if unidad else None

        respuesta.append(item)

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