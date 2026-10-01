from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select, func
from db import sesiondb
from modelos import (
    unidadmedidacreate, unidadmedidadb, unidadmedidaupdate, usuariodb,
    productodb, lotedb,
)
from usuarios import confirmacion

router = APIRouter()


def _unidad_repetida(conexion, usuario_id: int, nombre: str, abreviatura: str, excluir_id: int | None = None):
    """Unidad vigente con el mismo nombre o abreviatura, sin distinguir mayúsculas (se
    compara en Python porque SQLite no pasa a minúscula letras como Á o Ñ)."""
    n = nombre.strip().casefold()
    a = abreviatura.strip().casefold()
    vigentes = conexion.exec(
        select(unidadmedidadb).where(
            unidadmedidadb.usuario_id == usuario_id,
            unidadmedidadb.eliminada == False,  # noqa: E712
        )
    ).all()
    for u in vigentes:
        if u.id == excluir_id:
            continue
        if (n and u.nombre.strip().casefold() == n) or (a and u.abreviatura.strip().casefold() == a):
            return u
    return None


@router.post("/unidades-medida", response_model=unidadmedidadb, tags=["unidades-medida"])
async def crear_unidad(
    conexion: sesiondb,
    datos: unidadmedidacreate,
    usuario: usuariodb = Depends(confirmacion),
):
    """Crea una unidad de medida propia del usuario autenticado."""
    existente = _unidad_repetida(conexion, usuario.id, datos.nombre, datos.abreviatura)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya tienes una unidad de medida con ese nombre o abreviatura",
        )

    nueva = unidadmedidadb(
        nombre=datos.nombre.strip(),
        abreviatura=datos.abreviatura.strip(),
        usuario_id=usuario.id,
    )
    conexion.add(nueva)
    conexion.commit()
    conexion.refresh(nueva)
    return nueva


@router.get("/unidades-medida", response_model=list[unidadmedidadb], tags=["unidades-medida"])
async def listar_unidades(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    """Lista únicamente las unidades de medida del usuario autenticado."""
    return conexion.exec(
        select(unidadmedidadb).where(
            unidadmedidadb.usuario_id == usuario.id,
            unidadmedidadb.eliminada == False,  # noqa: E712
        )
    ).all()


@router.get(
    "/unidades-medida/{unidad_id}", response_model=unidadmedidadb, tags=["unidades-medida"]
)
async def obtener_unidad(
    conexion: sesiondb, unidad_id: int, usuario: usuariodb = Depends(confirmacion)
):
    unidad = conexion.get(unidadmedidadb, unidad_id)
    if unidad is None or unidad.usuario_id != usuario.id or unidad.eliminada:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada"
        )
    return unidad


@router.put(
    "/unidades-medida/{unidad_id}", response_model=unidadmedidadb, tags=["unidades-medida"]
)
async def actualizar_unidad(
    conexion: sesiondb,
    unidad_id: int,
    datos: unidadmedidaupdate,
    usuario: usuariodb = Depends(confirmacion),
):
    unidad = conexion.get(unidadmedidadb, unidad_id)
    if unidad is None or unidad.usuario_id != usuario.id or unidad.eliminada:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada"
        )

    cambios = datos.model_dump(exclude_unset=True)

    # Nombre y abreviatura no se pueden repetir (sin distinguir mayúsculas)
    for campo in ("nombre", "abreviatura"):
        if cambios.get(campo) is not None:
            cambios[campo] = cambios[campo].strip()
    if "nombre" in cambios or "abreviatura" in cambios:
        repetida = _unidad_repetida(
            conexion,
            usuario.id,
            cambios.get("nombre") or "",
            cambios.get("abreviatura") or "",
            excluir_id=unidad.id,
        )
        if repetida:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya tienes una unidad de medida con ese nombre o abreviatura",
            )

    for campo, valor in cambios.items():
        setattr(unidad, campo, valor)

    conexion.add(unidad)
    conexion.commit()
    conexion.refresh(unidad)
    return unidad


@router.delete("/unidades-medida/{unidad_id}", tags=["unidades-medida"])
async def eliminar_unidad(
    conexion: sesiondb, unidad_id: int, usuario: usuariodb = Depends(confirmacion)
):
    unidad = conexion.get(unidadmedidadb, unidad_id)
    if unidad is None or unidad.usuario_id != usuario.id or unidad.eliminada:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada"
        )
    # No se puede eliminar si aún hay productos con stock (vigentes, próximos a
    # vencer o vencidos sin retirar) que usan esta unidad.
    con_stock = conexion.exec(
        select(productodb.nombre)
        .join(lotedb, lotedb.producto_id == productodb.id)
        .where(
            productodb.usuario_id == usuario.id,
            productodb.unidad_de_medida_id == unidad_id,
            lotedb.cantidad_actual > 0,
        )
        .distinct()
    ).all()
    if con_stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No puedes eliminar esta unidad de medida porque aún hay productos en la "
                f"alacena que la usan ({', '.join(con_stock)}). Consúmelos o retíralos primero."
            ),
        )

    # Eliminación lógica: se conserva la fila para no romper el historial
    unidad.eliminada = True
    conexion.add(unidad)
    conexion.commit()
    return {"mensaje": "Unidad de medida eliminada correctamente"}