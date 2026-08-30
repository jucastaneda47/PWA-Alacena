from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select
from db import sesiondb
from modelos import (
    productocreate, productodb, productoupdate,
    categoriadb, unidadmedidadb, usuariodb,
)
from usuarios import confirmacion

router = APIRouter()


def _validar_referencias(conexion, usuario_id: int, categoria_id: int, unidad_de_medida_id: int):
    categoria = conexion.get(categoriadb, categoria_id)
    if categoria is None or categoria.usuario_id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La categoría indicada no existe"
        )
    unidad = conexion.get(unidadmedidadb, unidad_de_medida_id)
    if unidad is None or unidad.usuario_id != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La unidad de medida indicada no existe",
        )


@router.post("/productos", response_model=productodb, tags=["productos"])
async def crear_producto(
    conexion: sesiondb, datos: productocreate, usuario: usuariodb = Depends(confirmacion)
):
    _validar_referencias(conexion, usuario.id, datos.categoria_id, datos.unidad_de_medida_id)

    nuevo = productodb(**datos.model_dump(), usuario_id=usuario.id)
    conexion.add(nuevo)
    conexion.commit()
    conexion.refresh(nuevo)
    return nuevo


@router.get("/productos", response_model=list[productodb], tags=["productos"])
async def listar_productos(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    return conexion.exec(
        select(productodb).where(productodb.usuario_id == usuario.id)
    ).all()


@router.get("/productos/{producto_id}", response_model=productodb, tags=["productos"])
async def obtener_producto(
    conexion: sesiondb, producto_id: int, usuario: usuariodb = Depends(confirmacion)
):
    producto = conexion.get(productodb, producto_id)
    if producto is None or producto.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado"
        )
    return producto


@router.put("/productos/{producto_id}", response_model=productodb, tags=["productos"])
async def actualizar_producto(
    conexion: sesiondb,
    producto_id: int,
    datos: productoupdate,
    usuario: usuariodb = Depends(confirmacion),
):
    producto = conexion.get(productodb, producto_id)
    if producto is None or producto.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado"
        )

    cambios = datos.model_dump(exclude_unset=True)

    if "categoria_id" in cambios or "unidad_de_medida_id" in cambios:
        _validar_referencias(
            conexion,
            usuario.id,
            cambios.get("categoria_id", producto.categoria_id),
            cambios.get("unidad_de_medida_id", producto.unidad_de_medida_id),
        )

    for campo, valor in cambios.items():
        setattr(producto, campo, valor)

    conexion.add(producto)
    conexion.commit()
    conexion.refresh(producto)
    return producto


@router.delete("/productos/{producto_id}", tags=["productos"])
async def eliminar_producto(
    conexion: sesiondb, producto_id: int, usuario: usuariodb = Depends(confirmacion)
):
    producto = conexion.get(productodb, producto_id)
    if producto is None or producto.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado"
        )
    conexion.delete(producto)
    conexion.commit()
    return {"mensaje": "Producto eliminado correctamente"}


@router.get("/productos/{producto_id}/stock-minimo-efectivo", tags=["productos"])
async def obtener_stock_minimo_efectivo(
    conexion: sesiondb, producto_id: int, usuario: usuariodb = Depends(confirmacion)
):
    producto = conexion.get(productodb, producto_id)
    if producto is None or producto.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado"
        )

    if producto.stock_minimo is not None:
        return {"stock_minimo": producto.stock_minimo, "origen": "producto"}

    categoria = conexion.get(categoriadb, producto.categoria_id)
    return {"stock_minimo": categoria.stock_minimo, "origen": "categoria"}