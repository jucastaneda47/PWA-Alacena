from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select
from db import sesiondb
from modelos import transaccioncreate, transacciondb, lotedb, usuariodb
from usuarios import confirmacion

router = APIRouter()


@router.post("/consumo", response_model=transacciondb, tags=["consumo"])
async def registrar_consumo(
    conexion: sesiondb, datos: transaccioncreate, usuario: usuariodb = Depends(confirmacion)
):
    """
    RF-12: Descuenta cantidad_actual de un lote y deja registro de la
    transacción. tipo="consumo" para uso normal, tipo="retiro" para dar
    de baja un producto vencido (ambos casos usan el mismo mecanismo).
    """
    lote = conexion.get(lotedb, datos.lote_id)
    if lote is None or lote.usuario_id != usuario.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote no encontrado")

    if datos.cantidad <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La cantidad debe ser mayor a 0"
        )

    if datos.cantidad > lote.cantidad_actual:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No hay suficiente cantidad disponible (quedan {lote.cantidad_actual})",
        )

    lote.cantidad_actual -= datos.cantidad
    conexion.add(lote)

    nueva_transaccion = transacciondb(
        lote_id=lote.id,
        tipo=datos.tipo,
        cantidad=datos.cantidad,
        usuario_id=usuario.id,
    )
    conexion.add(nueva_transaccion)

    conexion.commit()
    conexion.refresh(nueva_transaccion)
    return nueva_transaccion


@router.get("/consumo", response_model=list[transacciondb], tags=["consumo"])
async def listar_consumo(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    """Historial de consumos/retiros del usuario, más reciente primero."""
    return conexion.exec(
        select(transacciondb)
        .where(transacciondb.usuario_id == usuario.id)
        .order_by(transacciondb.fecha.desc())
    ).all()