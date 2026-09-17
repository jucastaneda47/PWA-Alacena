from datetime import date, datetime, time, timedelta
from collections import defaultdict
from fastapi import APIRouter, HTTPException, status, Depends
from sqlmodel import select
from db import sesiondb
from modelos import (
    lotedb,
    compradb,
    transacciondb,
    categoriadb,
    productodb,
    unidadmedidadb,
    usuariodb,
)
from clasificacion import calcular_estado, UMBRAL_PROXIMO_DIAS
from usuarios import confirmacion

router = APIRouter()

MESES_ES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _clave_periodo(fecha: date, periodo: str):
    if periodo == "mes":
        return (fecha.year, fecha.month)
    iso_year, iso_week, _ = fecha.isocalendar()
    return (iso_year, iso_week)


def _etiqueta_periodo(clave, periodo: str) -> str:
    if periodo == "mes":
        anio, mes = clave
        return f"{MESES_ES[mes]} {anio}"
    _anio, semana = clave
    return f"Sem {semana}"


def _generar_claves(periodo: str, cantidad: int):
    hoy = date.today()
    claves = []
    if periodo == "mes":
        cursor = date(hoy.year, hoy.month, 1)
        for _ in range(cantidad):
            claves.append((cursor.year, cursor.month))
            cursor = (cursor - timedelta(days=1)).replace(day=1)
    else:
        cursor = hoy
        for _ in range(cantidad):
            claves.append(_clave_periodo(cursor, "semana"))
            cursor -= timedelta(weeks=1)
    claves.reverse()
    return claves


def _productos_en_inventario(conexion, usuario_id: int) -> set[int]:
    """IDs de productos que tienen al menos un lote con stock disponible ahora mismo."""
    ids = conexion.exec(
        select(lotedb.producto_id).where(
            lotedb.usuario_id == usuario_id, lotedb.cantidad_actual > 0
        )
    ).all()
    return set(ids)


@router.get("/estadisticas/movimientos", tags=["estadisticas"])
async def compras_vs_consumo(
    conexion: sesiondb,
    periodo: str = "semana",
    cantidad_periodos: int = 6,
    usuario: usuariodb = Depends(confirmacion),
):
    """
    Compara, período a período, cuántas compras se registraron (número de
    lotes creados) contra cuántos consumos se registraron (número de
    transacciones tipo='consumo'). Cuenta EVENTOS, no cantidades sumadas,
    para no mezclar unidades distintas (kg, L, unidades) en un solo número.
    """
    if periodo not in ("semana", "mes"):
        periodo = "semana"

    lotes_con_compra = conexion.exec(
        select(lotedb, compradb)
        .join(compradb, lotedb.compra_id == compradb.id)
        .where(lotedb.usuario_id == usuario.id)
    ).all()

    transacciones = conexion.exec(
        select(transacciondb).where(
            transacciondb.usuario_id == usuario.id,
            transacciondb.tipo == "consumo",
        )
    ).all()

    compras_por_periodo = defaultdict(int)
    for _lote, compra in lotes_con_compra:
        compras_por_periodo[_clave_periodo(compra.fecha_compra, periodo)] += 1

    consumo_por_periodo = defaultdict(int)
    for t in transacciones:
        consumo_por_periodo[_clave_periodo(t.fecha.date(), periodo)] += 1

    claves = _generar_claves(periodo, cantidad_periodos)

    return [
        {
            "periodo": _etiqueta_periodo(clave, periodo),
            "compras": compras_por_periodo.get(clave, 0),
            "consumos": consumo_por_periodo.get(clave, 0),
        }
        for clave in claves
    ]


@router.get("/estadisticas/distribucion-categorias", tags=["estadisticas"])
async def distribucion_por_categoria(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    """
    Cuenta cuántos productos distintos tiene cada categoría, contando SOLO
    los que tienen stock disponible ahora mismo (al menos un lote con
    cantidad_actual > 0) — así refleja el inventario actual, no el
    catálogo histórico de productos que alguna vez se crearon.
    """
    ids_en_inventario = _productos_en_inventario(conexion, usuario.id)
    if not ids_en_inventario:
        return []

    categorias = conexion.exec(
        select(categoriadb).where(categoriadb.usuario_id == usuario.id)
    ).all()
    productos = conexion.exec(
        select(productodb).where(
            productodb.usuario_id == usuario.id,
            productodb.id.in_(ids_en_inventario),
        )
    ).all()

    conteo = defaultdict(int)
    for p in productos:
        conteo[p.categoria_id] += 1

    respuesta = []
    for c in categorias:
        cantidad = conteo.get(c.id, 0)
        if cantidad == 0:
            continue
        respuesta.append(
            {
                "categoria_id": c.id,
                "categoria_nombre": c.nombre,
                "color": c.color,
                "icono": c.icono,
                "cantidad_productos": cantidad,
            }
        )

    respuesta.sort(key=lambda x: x["cantidad_productos"], reverse=True)
    return respuesta


@router.get(
    "/estadisticas/distribucion-categorias/{categoria_id}/productos", tags=["estadisticas"]
)
async def productos_de_categoria(
    conexion: sesiondb, categoria_id: int, usuario: usuariodb = Depends(confirmacion)
):
    """
    Detalle al hacer clic en una porción: los productos de esa categoría
    que TIENEN STOCK ACTUAL, con cuántas veces se compró cada uno en total
    (histórico, número de lotes registrados alguna vez para ese producto).
    """
    categoria = conexion.get(categoriadb, categoria_id)
    if categoria is None or categoria.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada"
        )

    ids_en_inventario = _productos_en_inventario(conexion, usuario.id)
    if not ids_en_inventario:
        return []

    productos = conexion.exec(
        select(productodb).where(
            productodb.usuario_id == usuario.id,
            productodb.categoria_id == categoria_id,
            productodb.id.in_(ids_en_inventario),
        )
    ).all()

    lotes = conexion.exec(select(lotedb).where(lotedb.usuario_id == usuario.id)).all()
    conteo_lotes = defaultdict(int)
    for l in lotes:
        conteo_lotes[l.producto_id] += 1

    respuesta = [
        {
            "producto_id": p.id,
            "producto_nombre": p.nombre,
            "veces_comprado": conteo_lotes.get(p.id, 0),
        }
        for p in productos
    ]
    respuesta.sort(key=lambda x: x["veces_comprado"], reverse=True)
    return respuesta


def _resumen_desperdicio_por_mes(conexion, usuario_id: int, claves_mes: set[tuple[int, int]]):
    """
    Para los lotes cuyo mes de vencimiento está entre los meses solicitados,
    determina cuántos se "desperdiciaron": aquellos a los que, al llegar su
    fecha de vencimiento, todavía les quedaba cantidad sin consumir. Solo
    cuentan como consumo real las transacciones tipo='consumo' registradas
    hasta (inclusive) la fecha de vencimiento del lote — un 'retiro' nunca
    cuenta como consumo, porque retirar YA es desperdicio.

    Como solo mira transacciones anteriores o iguales a la fecha de
    vencimiento, el resultado de un mes ya cerrado no cambia después,
    sin importar si el usuario retira el lote hoy, en un mes o nunca.
    """
    lotes = conexion.exec(select(lotedb).where(lotedb.usuario_id == usuario_id)).all()
    lotes_relevantes = [
        l for l in lotes if (l.fecha_vencimiento.year, l.fecha_vencimiento.month) in claves_mes
    ]
    if not lotes_relevantes:
        return {}

    ids_lotes = [l.id for l in lotes_relevantes]
    lotes_por_id = {l.id: l for l in lotes_relevantes}

    consumos = conexion.exec(
        select(transacciondb).where(
            transacciondb.lote_id.in_(ids_lotes),
            transacciondb.tipo == "consumo",
        )
    ).all()

    consumido_por_lote = defaultdict(float)
    for t in consumos:
        lote = lotes_por_id.get(t.lote_id)
        if lote and t.fecha.date() <= lote.fecha_vencimiento:
            consumido_por_lote[t.lote_id] += t.cantidad

    resumen = defaultdict(lambda: {"total": 0, "desperdiciados": 0})
    for lote in lotes_relevantes:
        clave = (lote.fecha_vencimiento.year, lote.fecha_vencimiento.month)
        resumen[clave]["total"] += 1
        consumido = consumido_por_lote.get(lote.id, 0)
        if consumido < lote.cantidad_inicial:
            resumen[clave]["desperdiciados"] += 1

    return resumen


@router.get("/estadisticas/desperdicio", tags=["estadisticas"])
async def evolucion_desperdicio(
    conexion: sesiondb,
    cantidad_meses: int = 6,
    usuario: usuariodb = Depends(confirmacion),
):
    """
    Evolución mensual del % de lotes desperdiciados, agrupados por su mes
    de vencimiento. Solo incluye meses ya cerrados (el mes en curso no
    tiene un % definitivo todavía, porque aún pueden vencerse más lotes
    dentro de él). Si un mes no tuvo ningún lote por vencer, se devuelve
    porcentaje_desperdicio=None para que el frontend lo muestre como un
    hueco real en la gráfica, no como 0%.
    """
    hoy = date.today()
    primer_dia_mes_actual = date(hoy.year, hoy.month, 1)

    claves = []
    cursor = primer_dia_mes_actual
    for _ in range(cantidad_meses):
        cursor = (cursor - timedelta(days=1)).replace(day=1)
        claves.append((cursor.year, cursor.month))
    claves.reverse()

    resumen = _resumen_desperdicio_por_mes(conexion, usuario.id, set(claves))

    resultado = []
    for clave in claves:
        datos = resumen.get(clave, {"total": 0, "desperdiciados": 0})
        porcentaje = (
            round((datos["desperdiciados"] / datos["total"]) * 100, 1)
            if datos["total"] > 0
            else None
        )
        resultado.append(
            {
                "periodo": f"{MESES_ES[clave[1]]} {clave[0]}",
                "total_lotes": datos["total"],
                "lotes_desperdiciados": datos["desperdiciados"],
                "porcentaje_desperdicio": porcentaje,
            }
        )
    return resultado


@router.get("/estadisticas/historial", tags=["estadisticas"])
async def historial_movimientos(
    conexion: sesiondb,
    tipos: str = "compra,consumo,retiro,vencimiento",
    desde: date | None = None,
    hasta: date | None = None,
    usuario: usuariodb = Depends(confirmacion),
):
    """
    Línea de tiempo unificada de 3 tipos de eventos: compras (un lote
    creado), consumos/retiros (transacciones) y vencimientos (un lote que
    llegó a su fecha de vencimiento). Devuelve TODOS los eventos que
    cumplen el filtro, ordenados de más reciente a más antiguo.

    No pagina aquí a propósito: si paginara mezclando los 3 tipos en un
    solo "top N global", un tipo con eventos menos frecuentes (por
    ejemplo, vencimientos) podía quedar completamente fuera de la primera
    página aunque sí existiera. El frontend decide cuánto mostrar —por
    carril cuando no hay filtro de fecha, o todo de una vez cuando el
    usuario sí fija un rango de fechas.
    """
    tipos_activos = {t.strip() for t in tipos.split(",") if t.strip()}

    filas = conexion.exec(
        select(lotedb, productodb, unidadmedidadb)
        .join(productodb, lotedb.producto_id == productodb.id)
        .join(unidadmedidadb, productodb.unidad_de_medida_id == unidadmedidadb.id)
        .where(lotedb.usuario_id == usuario.id)
    ).all()

    eventos = []
    lotes_info = {}
    for lote, producto, unidad in filas:
        lotes_info[lote.id] = (lote, producto, unidad)

    if "compra" in tipos_activos and filas:
        compras = conexion.exec(
            select(compradb).where(compradb.usuario_id == usuario.id)
        ).all()
        compras_por_id = {c.id: c for c in compras}
        for lote, producto, unidad in filas:
            compra = compras_por_id.get(lote.compra_id)
            if compra is None:
                continue
            eventos.append(
                {
                    "id": f"compra-{lote.id}",
                    "tipo": "compra",
                    "fecha": datetime.combine(compra.fecha_compra, time(9, 0)),
                    "titulo": f"Compraste {producto.nombre}",
                    "detalle": f"{lote.cantidad_inicial} {unidad.abreviatura} · vence {lote.fecha_vencimiento.isoformat()}",
                }
            )

    if ("consumo" in tipos_activos or "retiro" in tipos_activos) and filas:
        transacciones = conexion.exec(
            select(transacciondb).where(transacciondb.usuario_id == usuario.id)
        ).all()
        for t in transacciones:
            if t.tipo not in tipos_activos:
                continue
            info = lotes_info.get(t.lote_id)
            if info is None:
                continue
            _lote, producto, unidad = info
            verbo = "Consumiste" if t.tipo == "consumo" else "Retiraste"
            eventos.append(
                {
                    "id": f"{t.tipo}-{t.id}",
                    "tipo": t.tipo,
                    "fecha": t.fecha,
                    "titulo": f"{verbo} {producto.nombre}",
                    "detalle": f"{t.cantidad} {unidad.abreviatura}",
                }
            )

    if "vencimiento" in tipos_activos and filas:
        hoy = date.today()
        for lote, producto, unidad in filas:
            if lote.fecha_vencimiento <= hoy:
                quedaba_sin_consumir = lote.cantidad_actual > 0
                eventos.append(
                    {
                        "id": f"vencimiento-{lote.id}",
                        "tipo": "vencimiento",
                        "fecha": datetime.combine(lote.fecha_vencimiento, time(9, 0)),
                        "titulo": f"Venció {producto.nombre}",
                        "detalle": (
                            f"Quedaban {lote.cantidad_actual} {unidad.abreviatura} sin consumir"
                            if quedaba_sin_consumir
                            else "Se había consumido todo a tiempo"
                        ),
                    }
                )

    if desde is not None:
        eventos = [e for e in eventos if e["fecha"].date() >= desde]
    if hasta is not None:
        eventos = [e for e in eventos if e["fecha"].date() <= hasta]

    eventos.sort(key=lambda e: e["fecha"], reverse=True)

    return {
        "eventos": [{**e, "fecha": e["fecha"].isoformat()} for e in eventos],
        "total": len(eventos),
    }


def _fecha_hace_meses(fecha: date, meses: int) -> date:
    mes = fecha.month - meses
    anio = fecha.year
    while mes <= 0:
        mes += 12
        anio -= 1
    dia = min(fecha.day, 28)  # evita desbordes en meses cortos (ej. 31 de enero - 2 meses)
    return date(anio, mes, dia)


@router.get("/estadisticas/ranking-productos", tags=["estadisticas"])
async def ranking_productos(
    conexion: sesiondb,
    periodo: str = "reciente",
    usuario: usuariodb = Depends(confirmacion),
):
    """
    Top 5 productos por número de veces comprados (cuenta lotes/compras
    registradas, no cantidades sumadas, igual que el resto de estadísticas).

    periodo="reciente" (por defecto): solo compras de los últimos 2 meses.
    periodo="historico": desde siempre.
    """
    if periodo not in ("reciente", "historico"):
        periodo = "reciente"

    filas = conexion.exec(
        select(lotedb, compradb, productodb)
        .join(compradb, lotedb.compra_id == compradb.id)
        .join(productodb, lotedb.producto_id == productodb.id)
        .where(lotedb.usuario_id == usuario.id)
    ).all()

    if periodo == "reciente":
        limite = _fecha_hace_meses(date.today(), 2)
        filas = [fila for fila in filas if fila[1].fecha_compra >= limite]

    conteo = defaultdict(int)
    nombres = {}
    for _lote, _compra, producto in filas:
        conteo[producto.id] += 1
        nombres[producto.id] = producto.nombre

    ranking = sorted(conteo.items(), key=lambda item: item[1], reverse=True)[:5]

    return [
        {"producto_id": producto_id, "producto_nombre": nombres[producto_id], "veces_comprado": veces}
        for producto_id, veces in ranking
    ]

@router.get("/estadisticas/comprado-vs-consumido-categoria", tags=["estadisticas"])
async def comprado_vs_consumido_por_categoria(
    conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)
):
    """
    Módulo Compras e inventario. Por cada categoría con actividad, cuántas
    veces se compró (lotes registrados) contra cuántas veces se consumió
    (transacciones tipo='consumo', igual criterio que el gráfico de
    Movimientos — 'retiro' no cuenta como consumo). Histórico total, sin
    filtro de fecha.
    """
    filas = conexion.exec(
        select(lotedb, productodb, categoriadb)
        .join(productodb, lotedb.producto_id == productodb.id)
        .join(categoriadb, productodb.categoria_id == categoriadb.id)
        .where(lotedb.usuario_id == usuario.id)
    ).all()

    if not filas:
        return []

    lote_a_categoria = {lote.id: categoria for lote, _producto, categoria in filas}
    categorias_info = {categoria.id: categoria for _lote, _producto, categoria in filas}

    comprados = defaultdict(int)
    for lote, _producto, categoria in filas:
        comprados[categoria.id] += 1

    transacciones = conexion.exec(
        select(transacciondb).where(
            transacciondb.usuario_id == usuario.id,
            transacciondb.tipo == "consumo",
        )
    ).all()
    consumidos = defaultdict(int)
    for t in transacciones:
        categoria = lote_a_categoria.get(t.lote_id)
        if categoria:
            consumidos[categoria.id] += 1

    categorias_con_datos = set(comprados) | set(consumidos)
    resultado = [
        {
            "categoria_id": cat_id,
            "categoria_nombre": categorias_info[cat_id].nombre,
            "color": categorias_info[cat_id].color,
            "icono": categorias_info[cat_id].icono,
            "comprados": comprados.get(cat_id, 0),
            "consumidos": consumidos.get(cat_id, 0),
        }
        for cat_id in categorias_con_datos
    ]
    resultado.sort(key=lambda x: x["comprados"] + x["consumidos"], reverse=True)
    return resultado

@router.get("/estadisticas/riesgo-categoria", tags=["estadisticas"])
async def riesgo_por_categoria(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    """
    Módulo Consumo y vencimientos. Cuenta, por categoría, cuántos lotes
    CON STOCK ACTUAL están en este momento próximos a vencer o ya
    vencidos — solo lo que está en riesgo ahora mismo, no todo el
    inventario. El estado se recalcula al vuelo (no se confía en el
    campo `estado` guardado, que solo se actualiza cuando se consulta
    /inventario).
    """
    filas = conexion.exec(
        select(lotedb, productodb, categoriadb)
        .join(productodb, lotedb.producto_id == productodb.id)
        .join(categoriadb, productodb.categoria_id == categoriadb.id)
        .where(lotedb.usuario_id == usuario.id, lotedb.cantidad_actual > 0)
    ).all()

    conteo = defaultdict(int)
    categorias_info = {}
    for lote, _producto, categoria in filas:
        estado = calcular_estado(lote.fecha_vencimiento)
        if estado in ("proximo_a_vencer", "vencido"):
            conteo[categoria.id] += 1
            categorias_info[categoria.id] = categoria

    resultado = [
        {
            "categoria_id": cat_id,
            "categoria_nombre": categorias_info[cat_id].nombre,
            "color": categorias_info[cat_id].color,
            "icono": categorias_info[cat_id].icono,
            "cantidad_lotes": cantidad,
        }
        for cat_id, cantidad in conteo.items()
    ]
    resultado.sort(key=lambda x: x["cantidad_lotes"], reverse=True)
    return resultado


@router.get("/estadisticas/aprovechamiento", tags=["estadisticas"])
async def aprovechamiento_total(conexion: sesiondb, usuario: usuariodb = Depends(confirmacion)):
    """
    Módulo Consumo y vencimientos. Sobre los lotes que llegaron a estar
    en riesgo (vencidos, o próximos a vencer y ya resueltos), cuántos se
    consumieron por completo a tiempo (consumidos mientras aún se podía,
    dentro de la ventana de 'próximo a vencer' o antes) contra cuántos
    llegaron a vencerse con cantidad sin consumir. Una vez un lote está
    vencido ya no se puede registrar consumo sobre él — solo retiro —
    así que cualquier lote vencido con cantidad pendiente (retirada o
    no) cuenta como desperdicio, tenga o no también consumo parcial
    previo. Los lotes vigentes, y los próximos a vencer que todavía
    tienen cantidad sin resolver, se excluyen a propósito: su resultado
    aún no está definido.
    """
    hoy = date.today()
    lotes = conexion.exec(
        select(lotedb).where(lotedb.usuario_id == usuario.id)
    ).all()

    if not lotes:
        return {"aprovechados": 0, "desperdiciados": 0}

    ids_lotes = [l.id for l in lotes]
    transacciones = conexion.exec(
        select(transacciondb).where(transacciondb.lote_id.in_(ids_lotes))
    ).all()

    tiene_retiro = set()
    fecha_ultimo_consumo = {}
    for t in transacciones:
        if t.tipo == "retiro":
            tiene_retiro.add(t.lote_id)
        elif t.tipo == "consumo":
            fecha = t.fecha.date()
            anterior = fecha_ultimo_consumo.get(t.lote_id)
            if anterior is None or fecha > anterior:
                fecha_ultimo_consumo[t.lote_id] = fecha

    aprovechados = 0
    desperdiciados = 0
    for lote in lotes:
        if lote.id in tiene_retiro:
            # Llegó a vencido con cantidad pendiente y hubo que retirarla.
            desperdiciados += 1
            continue

        if lote.cantidad_actual <= 0:
            # Se consumió por completo sin necesitar retiro. Solo cuenta
            # como "a tiempo" si ese último consumo ocurrió dentro de la
            # ventana de riesgo (próximo a vencer) o antes de vencer.
            ultimo = fecha_ultimo_consumo.get(lote.id)
            if ultimo is not None and (lote.fecha_vencimiento - ultimo).days <= UMBRAL_PROXIMO_DIAS:
                aprovechados += 1
            continue

        # Todavía tiene cantidad sin consumir y sin retirar.
        if lote.fecha_vencimiento <= hoy:
            desperdiciados += 1
        # Si está vigente, o próximo a vencer sin resolver todavía, no
        # se cuenta: su resultado aún no está definido.

    return {"aprovechados": aprovechados, "desperdiciados": desperdiciados}