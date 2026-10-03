"""Pruebas de integración: alertas, historial de seguimiento y estadísticas de alertas."""
from datetime import datetime, timedelta

from sqlmodel import select

from modelos import alertadb


def tipos(alertas):
    return sorted(a["tipo"] for a in alertas)


# ============================ Generación de alertas ============================
def test_it150_lote_proximo_a_vencer_genera_alerta(ana):
    ana.comprar("Leche", dias=3, stock_minimo=0)
    alertas = ana.get("/alertas").json()
    assert tipos(alertas) == ["proximo_a_vencer"]
    assert alertas[0]["producto_nombre"] == "Leche" and alertas[0]["atendida"] is False


def test_it151_lote_vencido_genera_alerta_de_vencido(ana):
    ids = ana.comprar("Leche", dias=10, stock_minimo=0)
    ana.put(f"/lotes/{ids['lote']}", json={"fecha_vencimiento": "2020-01-01"})
    assert tipos(ana.get("/alertas").json()) == ["vencido"]


def test_it152_lote_vigente_no_genera_alerta(ana):
    ana.comprar("Leche", dias=30, stock_minimo=0)
    assert ana.get("/alertas").json() == []


def test_it153_stock_bajo_el_minimo_genera_alerta_con_detalle(ana):
    ana.comprar("Leche", cantidad=1, dias=30, stock_minimo=5)
    alerta = ana.get("/alertas").json()[0]
    assert alerta["tipo"] == "stock_minimo"
    assert alerta["cantidad_actual"] == 1 and alerta["stock_minimo"] == 5
    assert alerta["unidad_abreviatura"] == "l"


def test_it154_stock_minimo_heredado_de_la_categoria(ana):
    ana.put(f"/categorias/{ana.categoria_id('Lácteos')}", json={"stock_minimo": 4})
    ana.comprar("Leche", cantidad=1, dias=30)
    assert tipos(ana.get("/alertas").json()) == ["stock_minimo"]


def test_it155_no_duplica_alertas_al_consultar_varias_veces(ana):
    ana.comprar("Leche", cantidad=1, dias=3, stock_minimo=5)
    for _ in range(3):
        ana.get("/alertas")
    assert tipos(ana.get("/alertas").json()) == ["proximo_a_vencer", "stock_minimo"]


def test_it156_filtro_por_atendida(ana):
    ana.comprar("Leche", dias=3, stock_minimo=0)
    aid = ana.get("/alertas").json()[0]["id"]
    ana.put(f"/alertas/{aid}/atender")
    assert ana.get("/alertas", params={"atendida": False}).json() == []
    assert len(ana.get("/alertas", params={"atendida": True}).json()) == 1


# ============================ Atender ============================
def test_it160_atender_alerta(ana):
    ana.comprar("Leche", dias=3, stock_minimo=0)
    aid = ana.get("/alertas").json()[0]["id"]
    r = ana.put(f"/alertas/{aid}/atender")
    assert r.status_code == 200 and r.json()["atendida"] is True


def test_it161_atender_alerta_inexistente_o_ajena_es_404(ana, beto):
    beto.comprar("Leche", dias=3, stock_minimo=0)
    ajena = beto.get("/alertas").json()[0]["id"]
    assert ana.put(f"/alertas/{ajena}/atender").status_code == 404
    assert ana.put("/alertas/9999/atender").status_code == 404


def test_it162_alerta_atendida_no_se_vuelve_a_generar(ana):
    ana.comprar("Leche", dias=3, stock_minimo=0)
    aid = ana.get("/alertas").json()[0]["id"]
    ana.put(f"/alertas/{aid}/atender")
    ana.get("/alertas")
    assert ana.get("/alertas", params={"atendida": False}).json() == []


# ============================ Eliminar historial ============================
def sembrar_historial(sesion_bd, ana, dias_lista):
    """Crea alertas atendidas generadas hace N días para el usuario."""
    ids = ana.comprar("Leche", dias=30, stock_minimo=0)
    for dias in dias_lista:
        sesion_bd.add(alertadb(
            tipo="proximo_a_vencer", producto_id=ids["producto"], lote_id=ids["lote"],
            usuario_id=ana.get("/autorizado").json()["id"], atendida=True,
            fecha_generada=datetime.utcnow() - timedelta(days=dias),
        ))
    sesion_bd.commit()


def test_it170_eliminar_historial_borra_solo_lo_mas_antiguo_que_el_periodo(ana, sesion_bd):
    sembrar_historial(sesion_bd, ana, [5, 40, 100, 200, 400])
    r = ana.delete("/alertas/historial", params={"meses": 3})
    assert r.status_code == 200 and r.json() == {"eliminadas": 3}      # 100, 200 y 400 días
    assert len(ana.get("/alertas", params={"atendida": True}).json()) == 2   # quedan 5 y 40


def test_it171_cada_periodo_elimina_lo_correspondiente(ana, sesion_bd):
    sembrar_historial(sesion_bd, ana, [5, 40, 100, 200, 400])
    assert ana.delete("/alertas/historial", params={"meses": 12}).json() == {"eliminadas": 1}
    assert ana.delete("/alertas/historial", params={"meses": 6}).json() == {"eliminadas": 1}
    assert ana.delete("/alertas/historial", params={"meses": 1}).json() == {"eliminadas": 2}
    assert len(ana.get("/alertas", params={"atendida": True}).json()) == 1


def test_it172_periodo_invalido_es_400(ana):
    for meses in (0, 2, 5, 13):
        assert ana.delete("/alertas/historial", params={"meses": meses}).status_code == 400


def test_it173_no_elimina_alertas_pendientes(ana, sesion_bd):
    ids = ana.comprar("Leche", dias=30, stock_minimo=0)
    sesion_bd.add(alertadb(tipo="vencido", producto_id=ids["producto"], lote_id=ids["lote"],
                           usuario_id=ana.get("/autorizado").json()["id"], atendida=False,
                           fecha_generada=datetime.utcnow() - timedelta(days=500)))
    sesion_bd.commit()
    assert ana.delete("/alertas/historial", params={"meses": 1}).json() == {"eliminadas": 0}
    assert len(ana.get("/alertas", params={"atendida": False}).json()) == 1


def test_it174_eliminar_no_afecta_a_otros_usuarios(ana, beto, sesion_bd):
    sembrar_historial(sesion_bd, ana, [400])
    sembrar_historial(sesion_bd, beto, [400])
    ana.delete("/alertas/historial", params={"meses": 1})
    assert beto.get("/alertas", params={"atendida": True}).json() != []


def test_it175_la_alerta_eliminada_no_reaparece_como_pendiente(ana):
    """Si el lote sigue próximo a vencer, borrar su historial no debe recrear la alerta."""
    ana.comprar("Leche", dias=3, stock_minimo=0)
    aid = ana.get("/alertas").json()[0]["id"]
    ana.put(f"/alertas/{aid}/atender")
    # Simulamos que fue generada hace más de un mes
    from conftest import motor_pruebas
    from sqlmodel import Session
    with Session(motor_pruebas) as s:
        a = s.exec(select(alertadb)).one()
        a.fecha_generada = datetime.utcnow() - timedelta(days=60)
        s.add(a); s.commit()
    assert ana.delete("/alertas/historial", params={"meses": 1}).json() == {"eliminadas": 1}
    assert ana.get("/alertas").json() == []          # sigue sin aparecer


# ============================ Estadísticas de alertas ============================
def test_it180_alertas_por_categoria_agrupa_por_tipo_y_categoria(ana):
    ana.comprar("Leche", cantidad=1, dias=3, stock_minimo=5)                       # próximo + stock mínimo
    ana.comprar("Arroz", categoria="Granos", unidad="Kilogramo", cantidad=1, dias=2, stock_minimo=0)
    datos = ana.get("/estadisticas/alertas-por-categoria").json()
    assert set(datos) == {"vencido", "proximo_a_vencer", "stock_minimo"}
    prox = {g["categoria_nombre"]: g["cantidad"] for g in datos["proximo_a_vencer"]}
    assert prox == {"Lácteos": 1, "Granos": 1}
    assert [g["categoria_nombre"] for g in datos["stock_minimo"]] == ["Lácteos"]
    assert datos["vencido"] == []


def test_it181_alertas_por_categoria_incluye_detalle_y_marca_atendidas(ana):
    ana.comprar("Leche", cantidad=1, dias=3, stock_minimo=0)
    aid = ana.get("/alertas").json()[0]["id"]
    ana.put(f"/alertas/{aid}/atender")
    grupo = ana.get("/estadisticas/alertas-por-categoria").json()["proximo_a_vencer"][0]
    assert grupo["cantidad"] == 1
    assert grupo["productos"][0].startswith("Leche · ") and grupo["productos"][0].endswith("(atendida)")


def test_it182_alertas_por_categoria_vacio_para_usuario_nuevo(ana):
    assert ana.get("/estadisticas/alertas-por-categoria").json() == {
        "vencido": [], "proximo_a_vencer": [], "stock_minimo": []}


def test_it183_alertas_por_categoria_solo_del_usuario(ana, beto):
    beto.comprar("Leche", cantidad=1, dias=3, stock_minimo=0)
    beto.get("/alertas")
    assert ana.get("/estadisticas/alertas-por-categoria").json()["proximo_a_vencer"] == []


def test_it184_alertas_atencion_cuenta_atendidas_y_pendientes(ana):
    ana.comprar("Leche", cantidad=1, dias=3, stock_minimo=5)
    alertas = ana.get("/alertas").json()
    ana.put(f"/alertas/{alertas[0]['id']}/atender")
    filas = {f["tipo"]: f for f in ana.get("/estadisticas/alertas-atencion").json()}
    assert sum(f["atendidas"] for f in filas.values()) == 1
    assert sum(f["pendientes"] for f in filas.values()) == 1


def test_it185_alertas_por_periodo_devuelve_seis_periodos(ana):
    ana.comprar("Leche", dias=3, stock_minimo=0)
    ana.get("/alertas")
    for periodo in ("semana", "mes"):
        datos = ana.get("/estadisticas/alertas-por-periodo", params={"periodo": periodo}).json()
        assert len(datos) == 6
        assert sum(d["proximo_a_vencer"] for d in datos) == 1


def test_it186_historial_eliminado_sale_de_las_estadisticas(ana, sesion_bd):
    sembrar_historial(sesion_bd, ana, [400])
    assert len(ana.get("/estadisticas/alertas-atencion").json()) == 1
    ana.delete("/alertas/historial", params={"meses": 1})
    assert ana.get("/estadisticas/alertas-atencion").json() == []
    assert all(v == [] for v in ana.get("/estadisticas/alertas-por-categoria").json().values())
