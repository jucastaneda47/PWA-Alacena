from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select, func
from db import sesiondb
from modelos import (
    categoriacreate, categoriadb, categoriaupdate, usuariodb,
    productodb, lotedb,
)
from usuarios import confirmacion

router = APIRouter()


def _nombre_repetido(conexion, usuario_id: int, nombre: str, excluir_id: int | None = None):
    """Categoría vigente con ese nombre, sin distinguir mayúsculas (se compara en Python
    porque SQLite no pasa a minúscula letras como Á o Ñ)."""
    clave = nombre.strip().casefold()
    vigentes = conexion.exec(
        select(categoriadb).where(
            categoriadb.usuario_id == usuario_id,
            categoriadb.eliminada == False,  # noqa: E712
        )
    ).all()
    for c in vigentes:
        if c.id != excluir_id and c.nombre.strip().casefold() == clave:
            return c
    return None


@router.post("/categorias", response_model=categoriadb, tags=["categorias"])
async def crear_categoria(
    conexion: sesiondb,
    datos: categoriacreate,
    usuario: usuariodb = Depends(confirmacion),
):
    """Crea una categoría propia del usuario autenticado, con su ícono y color."""
    existente = _nombre_repetido(conexion, usuario.id, datos.nombre)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya tienes una categoría con ese nombre",
        )

    nueva = categoriadb(
        nombre=datos.nombre.strip(),
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
        select(categoriadb).where(
            categoriadb.usuario_id == usuario.id,
            categoriadb.eliminada == False,  # noqa: E712
        )
    ).all()


@router.get("/categorias/{categoria_id}", response_model=categoriadb, tags=["categorias"])
async def obtener_categoria(
    conexion: sesiondb, categoria_id: int, usuario: usuariodb = Depends(confirmacion)
):
    categoria = conexion.get(categoriadb, categoria_id)
    if categoria is None or categoria.usuario_id != usuario.id or categoria.eliminada:
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
    if categoria is None or categoria.usuario_id != usuario.id or categoria.eliminada:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada"
        )

    cambios = datos.model_dump(exclude_unset=True)

    # El nombre no se puede repetir (sin distinguir mayúsculas) entre categorías vigentes
    if cambios.get("nombre") is not None:
        cambios["nombre"] = cambios["nombre"].strip()
        repetida = _nombre_repetido(conexion, usuario.id, cambios["nombre"], excluir_id=categoria.id)
        if repetida:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya tienes una categoría con ese nombre",
            )

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
    if categoria is None or categoria.usuario_id != usuario.id or categoria.eliminada:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada"
        )
    # No se puede eliminar si aún hay productos con stock (vigentes, próximos a
    # vencer o vencidos sin retirar) en esta categoría.
    con_stock = conexion.exec(
        select(productodb.nombre)
        .join(lotedb, lotedb.producto_id == productodb.id)
        .where(
            productodb.usuario_id == usuario.id,
            productodb.categoria_id == categoria_id,
            lotedb.cantidad_actual > 0,
        )
        .distinct()
    ).all()
    if con_stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No puedes eliminar esta categoría porque aún tiene productos en la "
                f"alacena ({', '.join(con_stock)}). Consúmelos o retíralos primero."
            ),
        )

    # Eliminación lógica: se conserva la fila para no romper el historial
    categoria.eliminada = True
    conexion.add(categoria)
    conexion.commit()
    return {"mensaje": "Categoría eliminada correctamente"}