from fastapi import APIRouter, HTTPException, status
from sqlmodel import select
from db import sesiondb
from modelos import categoriacreate, categoriadb, categoriaupdate

router = APIRouter()


@router.post("/categorias", response_model=categoriadb, tags=["categorias"])
async def crear_categoria(conexion: sesiondb, datos: categoriacreate):
    """Crea una nueva categoría de alimentos con su stock mínimo por defecto."""
    existente = conexion.exec(
        select(categoriadb).where(categoriadb.nombre == datos.nombre)
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe una categoría con ese nombre",
        )

    nueva = categoriadb.model_validate(datos)
    conexion.add(nueva)
    conexion.commit()
    conexion.refresh(nueva)
    return nueva


@router.get("/categorias", response_model=list[categoriadb], tags=["categorias"])
async def listar_categorias(conexion: sesiondb):
    """Lista todas las categorías disponibles, para poblar el selector del frontend."""
    return conexion.exec(select(categoriadb)).all()


@router.get("/categorias/{categoria_id}", response_model=categoriadb, tags=["categorias"])
async def obtener_categoria(conexion: sesiondb, categoria_id: int):
    categoria = conexion.get(categoriadb, categoria_id)
    if categoria is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada"
        )
    return categoria


@router.put("/categorias/{categoria_id}", response_model=categoriadb, tags=["categorias"])
async def actualizar_categoria(conexion: sesiondb, categoria_id: int, datos: categoriaupdate):
    """Permite editar el nombre y/o el stock mínimo de la categoría."""
    categoria = conexion.get(categoriadb, categoria_id)
    if categoria is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada"
        )

    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(categoria, campo, valor)

    conexion.add(categoria)
    conexion.commit()
    conexion.refresh(categoria)
    return categoria


@router.delete("/categorias/{categoria_id}", tags=["categorias"])
async def eliminar_categoria(conexion: sesiondb, categoria_id: int):
    categoria = conexion.get(categoriadb, categoria_id)
    if categoria is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada"
        )
    conexion.delete(categoria)
    conexion.commit()
    return {"mensaje": "Categoría eliminada correctamente"}