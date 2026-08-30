from fastapi import APIRouter, HTTPException, status
from sqlmodel import select
from db import sesiondb
from modelos import unidadmedidacreate, unidadmedidadb, unidadmedidaupdate

router = APIRouter()


@router.post("/unidades-medida", response_model=unidadmedidadb, tags=["unidades-medida"])
async def crear_unidad(conexion: sesiondb, datos: unidadmedidacreate):
    """Crea una nueva unidad de medida (ej. Kilogramo, abreviatura 'kg')."""
    existente = conexion.exec(
        select(unidadmedidadb).where(
            (unidadmedidadb.nombre == datos.nombre)
            | (unidadmedidadb.abreviatura == datos.abreviatura)
        )
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe una unidad de medida con ese nombre o abreviatura",
        )

    nueva = unidadmedidadb.model_validate(datos)
    conexion.add(nueva)
    conexion.commit()
    conexion.refresh(nueva)
    return nueva


@router.get("/unidades-medida", response_model=list[unidadmedidadb], tags=["unidades-medida"])
async def listar_unidades(conexion: sesiondb):
    """Lista todas las unidades de medida, para poblar el selector del frontend."""
    return conexion.exec(select(unidadmedidadb)).all()


@router.get(
    "/unidades-medida/{unidad_id}", response_model=unidadmedidadb, tags=["unidades-medida"]
)
async def obtener_unidad(conexion: sesiondb, unidad_id: int):
    unidad = conexion.get(unidadmedidadb, unidad_id)
    if unidad is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada"
        )
    return unidad


@router.put(
    "/unidades-medida/{unidad_id}", response_model=unidadmedidadb, tags=["unidades-medida"]
)
async def actualizar_unidad(conexion: sesiondb, unidad_id: int, datos: unidadmedidaupdate):
    unidad = conexion.get(unidadmedidadb, unidad_id)
    if unidad is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada"
        )

    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(unidad, campo, valor)

    conexion.add(unidad)
    conexion.commit()
    conexion.refresh(unidad)
    return unidad


@router.delete("/unidades-medida/{unidad_id}", tags=["unidades-medida"])
async def eliminar_unidad(conexion: sesiondb, unidad_id: int):
    unidad = conexion.get(unidadmedidadb, unidad_id)
    if unidad is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unidad de medida no encontrada"
        )
    conexion.delete(unidad)
    conexion.commit()
    return {"mensaje": "Unidad de medida eliminada correctamente"}