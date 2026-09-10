from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select
from db import sesiondb
from modelos import categoriacreate, categoriadb, categoriaupdate, usuariodb
from usuarios import confirmacion

router = APIRouter()


@router.post("/categorias", response_model=categoriadb, tags=["categorias"])
async def crear_categoria(
    conexion: sesiondb,
    datos: categoriacreate,
    usuario: usuariodb = Depends(confirmacion),
):
    """Crea una categoría propia del usuario autenticado, con su ícono y color."""
    existente = conexion.exec(
        select(categoriadb).where(
            categoriadb.usuario_id == usuario.id,
            categoriadb.nombre == datos.nombre,
        )
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya tienes una categoría con ese nombre",
        )

    nueva = categoriadb(
        nombre=datos.nombre,
        stock_minimo=datos.stock_minimo,
        icono=datos.icono,
        color=datos.color,
        usuario_id=usuario.id,
    )
    conexion.add(nueva)
    conexion.commit()
    conexion.refresh(nueva)
    return nueva


@router.get("/categorias", response_model=list[categoriadb], tags=["categorias"])
async def listar_categorias(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    """Lista únicamente las categorías del usuario autenticado."""
    return conexion.exec(
        select(categoriadb).where(categoriadb.usuario_id == usuario.id)
    ).all()


@router.get("/categorias/{categoria_id}", response_model=categoriadb, tags=["categorias"])
async def obtener_categoria(
    conexion: sesiondb, categoria_id: int, usuario: usuariodb = Depends(confirmacion)
):
    categoria = conexion.get(categoriadb, categoria_id)
    if categoria is None or categoria.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada"
        )
    return categoria


@router.put("/categorias/{categoria_id}", response_model=categoriadb, tags=["categorias"])
async def actualizar_categoria(
    conexion: sesiondb,
    categoria_id: int,
    datos: categoriaupdate,
    usuario: usuariodb = Depends(confirmacion),
):
    """Permite editar nombre, stock mínimo, ícono y/o color de la categoría."""
    categoria = conexion.get(categoriadb, categoria_id)
    if categoria is None or categoria.usuario_id != usuario.id:
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
async def eliminar_categoria(
    conexion: sesiondb, categoria_id: int, usuario: usuariodb = Depends(confirmacion)
):
    categoria = conexion.get(categoriadb, categoria_id)
    if categoria is None or categoria.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada"
        )
    conexion.delete(categoria)
    conexion.commit()
    return {"mensaje": "Categoría eliminada correctamente"}