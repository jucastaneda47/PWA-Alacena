from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from db import sesiondb
from modelos import (
    compracreate, compradb, usuariodb, compraSincronizada, sincronizaciondb,
    lotedb, productodb, productocreate, categoriadb, unidadmedidadb,
)
from usuarios import confirmacion
from clasificacion import calcular_estado
from productos import crear_o_reutilizar_producto

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


def _error_linea(numero: int, detalle: str):
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail=f"Producto {numero} de la compra: {detalle}"
    )


@router.post("/compras/sincronizar", tags=["compras"])
async def sincronizar_compra(
    conexion: sesiondb, datos: compraSincronizada, usuario: usuariodb = Depends(confirmacion)
):
    """
    Recibe una compra completa (compra + lotes, con productos nuevos si hace falta) registrada
    sin conexión. Es "todo o nada" y no se duplica: si el mismo cliente_id llega otra vez
    (reintento tras perder la conexión), devuelve la compra ya creada sin crear nada nuevo.
    """
    def ya_sincronizada():
        return conexion.exec(
            select(sincronizaciondb).where(
                sincronizaciondb.usuario_id == usuario.id,
                sincronizaciondb.cliente_id == datos.cliente_id,
            )
        ).first()

    previa = ya_sincronizada()
    if previa is not None:
        return {"compra_id": previa.compra_id, "repetida": True}

    try:
        compra = compradb(fecha_compra=datos.fecha_compra, usuario_id=usuario.id)
        conexion.add(compra)
        conexion.flush()

        lotes = []
        for numero, linea in enumerate(datos.lineas, start=1):
            if linea.cantidad_inicial <= 0:
                raise _error_linea(numero, "la cantidad debe ser mayor que cero.")
            if linea.fecha_vencimiento < datos.fecha_compra:
                raise _error_linea(numero, "la fecha de vencimiento es anterior a la fecha de la compra.")

            if linea.producto_id is not None:
                producto = conexion.get(productodb, linea.producto_id)
                if producto is None or producto.usuario_id != usuario.id:
                    raise _error_linea(numero, "el producto ya no existe.")
                categoria = conexion.get(categoriadb, producto.categoria_id)
                unidad = conexion.get(unidadmedidadb, producto.unidad_de_medida_id)
                if categoria is None or categoria.eliminada or unidad is None or unidad.eliminada:
                    raise _error_linea(numero, "la categoría o la unidad del producto fue eliminada.")
            else:
                if not (linea.nombre_nuevo and linea.nombre_nuevo.strip()
                        and linea.categoria_id and linea.unidad_de_medida_id):
                    raise _error_linea(numero, "falta el nombre, la categoría o la unidad del producto nuevo.")
                try:
                    producto = crear_o_reutilizar_producto(
                        conexion,
                        usuario.id,
                        productocreate(
                            nombre=linea.nombre_nuevo,
                            categoria_id=linea.categoria_id,
                            unidad_de_medida_id=linea.unidad_de_medida_id,
                            stock_minimo=None,
                        ),
                        confirmar=False,
                    )
                except HTTPException as e:
                    raise _error_linea(numero, e.detail)

            lote = lotedb(
                producto_id=producto.id,
                compra_id=compra.id,
                fecha_vencimiento=linea.fecha_vencimiento,
                cantidad_inicial=linea.cantidad_inicial,
                cantidad_actual=linea.cantidad_inicial,
                usuario_id=usuario.id,
                estado=calcular_estado(linea.fecha_vencimiento),
            )
            conexion.add(lote)
            lotes.append(lote)

        conexion.flush()
        conexion.add(
            sincronizaciondb(usuario_id=usuario.id, cliente_id=datos.cliente_id, compra_id=compra.id)
        )
        conexion.commit()
    except IntegrityError:
        # Dos envíos simultáneos de la misma compra: gana uno, el otro devuelve el resultado del primero.
        conexion.rollback()
        previa = ya_sincronizada()
        if previa is None:
            raise
        return {"compra_id": previa.compra_id, "repetida": True}
    except HTTPException:
        conexion.rollback()
        raise

    return {"compra_id": compra.id, "lotes": [l.id for l in lotes], "repetida": False}


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