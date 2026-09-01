from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select
from db import sesiondb
from modelos import compracreate, compradb, usuariodb
from usuarios import confirmacion

router = APIRouter()


@router.post("/compras", response_model=compradb, tags=["compras"])
async def registrar_compra(
    conexion: sesiondb, datos: compracreate, usuario: usuariodb = Depends(confirmacion)
):
    nueva = compradb(fecha_compra=datos.fecha_compra, usuario_id=usuario.id)
    conexion.add(nueva)
    conexion.commit()
    conexion.refresh(nueva)
    return nueva


@router.get("/compras", response_model=list[compradb], tags=["compras"])
async def listar_compras(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    return conexion.exec(
        select(compradb)
        .where(compradb.usuario_id == usuario.id)
        .order_by(compradb.fecha_compra.desc())
    ).all()


@router.get("/compras/{compra_id}", response_model=compradb, tags=["compras"])
async def obtener_compra(
    conexion: sesiondb, compra_id: int, usuario: usuariodb = Depends(confirmacion)
):
    compra = conexion.get(compradb, compra_id)
    if compra is None or compra.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada"
        )
    return compra


@router.delete("/compras/{compra_id}", tags=["compras"])
async def eliminar_compra(
    conexion: sesiondb, compra_id: int, usuario: usuariodb = Depends(confirmacion)
):
    compra = conexion.get(compradb, compra_id)
    if compra is None or compra.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Compra no encontrada"
        )
    conexion.delete(compra)
    conexion.commit()
    return {"mensaje": "Compra eliminada correctamente"}