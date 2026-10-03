"""Estadísticas de la pantalla Alertas y seguimiento: alertas por período, atendidas vs. pendientes y alertas por categoría.

El funcionamiento de las alertas (generarlas, atenderlas, borrar historial) está en src/alertas.py.
"""
from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlmodel import select
from db import sesiondb
from modelos import categoriadb, productodb, alertadb, usuariodb
from usuarios import confirmacion
from alertas import _sincronizar_alertas
from .comunes import MESES_ES, _clave_periodo, _etiqueta_periodo, _generar_claves

router = APIRouter()


@router.get("/estadisticas/alertas-por-periodo", tags=["estadisticas"])
async def alertas_por_periodo(
    conexion: sesiondb,
    periodo: str = "semana",
    cantidad_periodos: int = 6,
    usuario: usuariodb = Depends(confirmacion),
):
    """
    Módulo Alertas y seguimiento. Cuántas alertas se generaron por
    período (semana o mes), separadas por tipo, para ver la tendencia
    en el tiempo — igual estilo que el gráfico de Movimientos.
    """
    if periodo not in ("semana", "mes"):
        periodo = "semana"

    # Genera las alertas que falten, para que el gráfico no dependa de que el
    # usuario haya abierto antes la lista de alertas.
    _sincronizar_alertas(conexion, usuario.id)

    alertas = conexion.exec(
        select(alertadb).where(
            alertadb.usuario_id == usuario.id, alertadb.oculta == False  # noqa: E712
        )
    ).all()

    conteo = defaultdict(lambda: defaultdict(int))
    for a in alertas:
        clave = _clave_periodo(a.fecha_generada.date(), periodo)
        conteo[clave][a.tipo] += 1

    claves = _generar_claves(periodo, cantidad_periodos)

    return [
        {
            "periodo": _etiqueta_periodo(clave, periodo),
            "proximo_a_vencer": conteo[clave].get("proximo_a_vencer", 0),
            "vencido": conteo[clave].get("vencido", 0),
            "stock_minimo": conteo[clave].get("stock_minimo", 0),
        }
        for clave in claves
    ]


@router.get("/estadisticas/alertas-atencion", tags=["estadisticas"])
async def alertas_atencion_por_tipo(
    conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)
):
    """
    Módulo Alertas y seguimiento. Por cada tipo de alerta, cuántas
    fueron atendidas contra cuántas siguen pendientes — mide qué tan al
    día está el usuario con el seguimiento. Incluye el detalle (producto
    y fecha) de cada alerta que compone cada barra, para mostrarlo al
    pasar el mouse sobre ella.
    """
    _sincronizar_alertas(conexion, usuario.id)

    filas = conexion.exec(
        select(alertadb, productodb)
        .join(productodb, alertadb.producto_id == productodb.id, isouter=True)
        .where(alertadb.usuario_id == usuario.id, alertadb.oculta == False)  # noqa: E712
        .order_by(alertadb.fecha_generada.desc())
    ).all()

    conteo = defaultdict(lambda: {"atendidas": 0, "pendientes": 0})
    detalle = defaultdict(lambda: {"atendidas": [], "pendientes": []})
    for a, producto in filas:
        nombre = producto.nombre if producto else "Producto eliminado"
        etiqueta = f"{nombre} · {a.fecha_generada.day} {MESES_ES[a.fecha_generada.month]}"
        if a.atendida:
            conteo[a.tipo]["atendidas"] += 1
            detalle[a.tipo]["atendidas"].append(etiqueta)
        else:
            conteo[a.tipo]["pendientes"] += 1
            detalle[a.tipo]["pendientes"].append(etiqueta)

    etiquetas_tipo = {
        "vencido": "Vencido",
        "proximo_a_vencer": "Próximo a vencer",
        "stock_minimo": "Stock mínimo",
    }
    orden = ["vencido", "proximo_a_vencer", "stock_minimo"]

    return [
        {
            "tipo": tipo,
            "tipo_nombre": etiquetas_tipo[tipo],
            "atendidas": conteo[tipo]["atendidas"],
            "pendientes": conteo[tipo]["pendientes"],
            "detalle_atendidas": detalle[tipo]["atendidas"],
            "detalle_pendientes": detalle[tipo]["pendientes"],
        }
        for tipo in orden
        if conteo[tipo]["atendidas"] > 0 or conteo[tipo]["pendientes"] > 0
    ]


@router.get("/estadisticas/alertas-por-categoria", tags=["estadisticas"])
async def alertas_por_categoria(
    conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)
):
    """
    Módulo Alertas y seguimiento. Para cada tipo de alerta (vencido,
    próximo a vencer y stock mínimo) cuántas alertas hay por categoría,
    contando las pendientes y las atendidas. Incluye el detalle (producto,
    fecha y si ya fue atendida) para mostrarlo al pasar el mouse.
    """
    _sincronizar_alertas(conexion, usuario.id)

    filas = conexion.exec(
        select(alertadb, productodb, categoriadb)
        .join(productodb, alertadb.producto_id == productodb.id, isouter=True)
        .join(categoriadb, productodb.categoria_id == categoriadb.id, isouter=True)
        .where(alertadb.usuario_id == usuario.id, alertadb.oculta == False)  # noqa: E712
        .order_by(alertadb.fecha_generada.desc())
    ).all()

    # tipo -> clave de categoría -> datos acumulados
    acumulado = {t: {} for t in ("vencido", "proximo_a_vencer", "stock_minimo")}
    for a, producto, categoria in filas:
        if a.tipo not in acumulado:
            continue
        clave = categoria.id if categoria else 0
        grupo = acumulado[a.tipo].setdefault(
            clave,
            {
                "categoria_id": clave,
                "categoria_nombre": categoria.nombre if categoria else "Sin categoría",
                "color": categoria.color if categoria else None,
                "icono": categoria.icono if categoria else None,
                "cantidad": 0,
                "productos": [],
            },
        )
        nombre = producto.nombre if producto else "Producto eliminado"
        linea = f"{nombre} · {a.fecha_generada.day} {MESES_ES[a.fecha_generada.month]}"
        if a.atendida:
            linea += " (atendida)"
        grupo["cantidad"] += 1
        grupo["productos"].append(linea)

    return {
        tipo: sorted(grupos.values(), key=lambda g: g["cantidad"], reverse=True)
        for tipo, grupos in acumulado.items()
    }
