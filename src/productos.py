from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select, func
from db import sesiondb
from modelos import (
    productocreate, productodb, productoupdate,
    categoriadb, unidadmedidadb, usuariodb,
)
from usuarios import confirmacion

router = APIRouter()


def _validar_referencias(conexion, usuario_id: int, categoria_id: int, unidad_de_medida_id: int):
    categoria = conexion.get(categoriadb, categoria_id)
    if categoria is None or categoria.usuario_id != usuario_id or categoria.eliminada:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La categoría indicada no existe"
        )
    unidad = conexion.get(unidadmedidadb, unidad_de_medida_id)
    if unidad is None or unidad.usuario_id != usuario_id or unidad.eliminada:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La unidad de medida indicada no existe",
        )


def _buscar_activo_por_nombre(conexion, usuario_id: int, nombre: str, excluir_id: int | None = None):
    """Producto vigente (categoría y unidad no eliminadas) con ese nombre, sin distinguir mayúsculas."""
    # Se compara en Python: SQLite no pasa a minúscula letras como Ñ o Á
    clave = nombre.strip().casefold()
    consulta = (
        select(productodb)
        .join(categoriadb, productodb.categoria_id == categoriadb.id)
        .join(unidadmedidadb, productodb.unidad_de_medida_id == unidadmedidadb.id)
        .where(
            productodb.usuario_id == usuario_id,
            categoriadb.eliminada == False,  # noqa: E712
            unidadmedidadb.eliminada == False,  # noqa: E712
        )
    )
    for p in conexion.exec(consulta).all():
        if p.id != excluir_id and p.nombre.strip().casefold() == clave:
            return p
    return None


@router.post("/productos", response_model=productodb, tags=["productos"])
async def crear_producto(
    conexion: sesiondb, datos: productocreate, usuario: usuariodb = Depends(confirmacion)
):
    _validar_referencias(conexion, usuario.id, datos.categoria_id, datos.unidad_de_medida_id)

    clave = datos.nombre.strip().casefold()
    candidatos = conexion.exec(
        select(productodb)
        .join(categoriadb, productodb.categoria_id == categoriadb.id)
        .join(unidadmedidadb, productodb.unidad_de_medida_id == unidadmedidadb.id)
        .where(
            productodb.usuario_id == usuario.id,
            (categoriadb.eliminada == True) | (unidadmedidadb.eliminada == True),  # noqa: E712
        )
    ).all()
    huerfano = next((p for p in candidatos if p.nombre.strip().casefold() == clave), None)
    if huerfano is not None:
        huerfano.categoria_id = datos.categoria_id
        huerfano.unidad_de_medida_id = datos.unidad_de_medida_id
        if datos.stock_minimo is not None:
            huerfano.stock_minimo = datos.stock_minimo
        conexion.add(huerfano)
        conexion.commit()
        conexion.refresh(huerfano)
        return huerfano

    existente = _buscar_activo_por_nombre(conexion, usuario.id, datos.nombre)
    if existente is not None:
        if (
            existente.categoria_id == datos.categoria_id
            and existente.unidad_de_medida_id == datos.unidad_de_medida_id
        ):
            return existente
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Ya existe el producto \"{existente.nombre}\" con otra categoría o unidad. "
                "Elígelo en \"Producto existente\" o usa otro nombre."
            ),
        )

    datos.nombre = datos.nombre.strip()
    nuevo = productodb(**datos.model_dump(), usuario_id=usuario.id)
    conexion.add(nuevo)
    conexion.commit()
    conexion.refresh(nuevo)
    return nuevo


@router.get("/productos", response_model=list[productodb], tags=["productos"])
async def listar_productos(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    # Solo productos cuya categoría y unidad de medida siguen vigentes
    return conexion.exec(
        select(productodb)
        .join(categoriadb, productodb.categoria_id == categoriadb.id)
        .join(unidadmedidadb, productodb.unidad_de_medida_id == unidadmedidadb.id)
        .where(
            productodb.usuario_id == usuario.id,
            categoriadb.eliminada == False,  # noqa: E712
            unidadmedidadb.eliminada == False,  # noqa: E712
        )
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

    if "nombre" in cambios and cambios["nombre"] is not None:
        cambios["nombre"] = cambios["nombre"].strip()
        if _buscar_activo_por_nombre(conexion, usuario.id, cambios["nombre"], excluir_id=producto.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe otro producto con ese nombre",
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