from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select
from db import sesiondb
from modelos import lotecreate, lotedb, loteupdate, compradb, productodb, usuariodb
from usuarios import confirmacion
from clasificacion import calcular_estado

router = APIRouter()


def _validar_referencias(conexion, usuario_id: int, compra_id: int, producto_id: int):
    compra = conexion.get(compradb, compra_id)
    if compra is None or compra.usuario_id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La compra indicada no existe"
        )
    producto = conexion.get(productodb, producto_id)
    if producto is None or producto.usuario_id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="El producto indicado no existe"
        )


@router.post("/lotes", response_model=lotedb, tags=["lotes"])
async def crear_lote(
    conexion: sesiondb, datos: lotecreate, usuario: usuariodb = Depends(confirmacion)
):
    _validar_referencias(conexion, usuario.id, datos.compra_id, datos.producto_id)

    nuevo = lotedb(
        producto_id=datos.producto_id,
        compra_id=datos.compra_id,
        fecha_vencimiento=datos.fecha_vencimiento,
        cantidad_inicial=datos.cantidad_inicial,
        cantidad_actual=datos.cantidad_inicial,
        usuario_id=usuario.id,
        estado=calcular_estado(datos.fecha_vencimiento),
    )
    conexion.add(nuevo)
    conexion.commit()
    conexion.refresh(nuevo)
    return nuevo


@router.get("/lotes", response_model=list[lotedb], tags=["lotes"])
async def listar_lotes(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    return conexion.exec(select(lotedb).where(lotedb.usuario_id == usuario.id)).all()


@router.get("/lotes/{lote_id}", response_model=lotedb, tags=["lotes"])
async def obtener_lote(
    conexion: sesiondb, lote_id: int, usuario: usuariodb = Depends(confirmacion)
):
    lote = conexion.get(lotedb, lote_id)
    if lote is None or lote.usuario_id != usuario.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote no encontrado")
    return lote


@router.put("/lotes/{lote_id}", response_model=lotedb, tags=["lotes"])
async def actualizar_lote(
    conexion: sesiondb, lote_id: int, datos: loteupdate, usuario: usuariodb = Depends(confirmacion)
):
    """
    RF-10: Actualiza la cantidad disponible de un lote (por ejemplo, para
    corregir un error de captura) y/o su fecha de vencimiento. Si cambia la
    fecha de vencimiento, el estado se recalcula automáticamente.
    """
    lote = conexion.get(lotedb, lote_id)
    if lote is None or lote.usuario_id != usuario.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote no encontrado")

    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(lote, campo, valor)

    if "fecha_vencimiento" in cambios:
        lote.estado = calcular_estado(lote.fecha_vencimiento)

    conexion.add(lote)
    conexion.commit()
    conexion.refresh(lote)
    return lote


@router.delete("/lotes/{lote_id}", tags=["lotes"])
async def eliminar_lote(
    conexion: sesiondb, lote_id: int, usuario: usuariodb = Depends(confirmacion)
):
    lote = conexion.get(lotedb, lote_id)
    if lote is None or lote.usuario_id != usuario.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote no encontrado")
    conexion.delete(lote)
    conexion.commit()
    return {"mensaje": "Lote eliminado correctamente"}