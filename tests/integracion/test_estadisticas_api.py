"""Pruebas de integración: estadísticas del tablero (respuesta correcta y aislada por usuario)."""
import pytest

ENDPOINTS = [
    "/estadisticas/movimientos",
    "/estadisticas/distribucion-categorias",
    "/estadisticas/desperdicio",
    "/estadisticas/desperdicio/configuracion",
    "/estadisticas/historial",
    "/estadisticas/ranking-productos",
    "/estadisticas/comprado-vs-consumido-categoria",
    "/estadisticas/riesgo-categoria",
    "/estadisticas/aprovechamiento",
    "/estadisticas/alertas-por-periodo",
    "/estadisticas/alertas-atencion",
    "/estadisticas/alertas-por-categoria",
]


@pytest.mark.parametrize("url", ENDPOINTS)
def test_it200_endpoints_responden_para_usuario_sin_datos(ana, url):
    assert ana.get(url).status_code == 200


@pytest.mark.parametrize("url", ENDPOINTS)
def test_it201_endpoints_responden_con_datos(ana, url):
    ids = ana.comprar("Leche", cantidad=4, dias=3, stock_minimo=10)
    ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 1})
    ana.comprar("Arroz", categoria="Granos", unidad="Kilogramo", cantidad=2, dias=40)
    assert ana.get(url).status_code == 200


@pytest.mark.parametrize("url", ENDPOINTS)
def test_it202_endpoints_exigen_sesion(cliente, url):
    assert cliente.get(url).status_code == 401


def test_it203_distribucion_cuenta_solo_productos_con_stock(ana):
    ana.comprar("Leche", cantidad=1)
    agotado = ana.comprar("Yogur", cantidad=1)
    ana.post("/consumo", json={"lote_id": agotado["lote"], "cantidad": 1})
    datos = ana.get("/estadisticas/distribucion-categorias").json()
    assert datos[0]["categoria_nombre"] == "Lácteos" and datos[0]["cantidad_productos"] == 1


def test_it204_distribucion_no_mezcla_usuarios(ana, beto):
    beto.comprar("Leche")
    assert ana.get("/estadisticas/distribucion-categorias").json() == []


def test_it205_configuracion_de_desperdicio(ana):
    assert ana.get("/estadisticas/desperdicio/configuracion").json() == {"promedio": 10.0, "meta": 2.0}
    r = ana.patch("/estadisticas/desperdicio/configuracion", json={"promedio": 15, "meta": 5})
    assert r.json() == {"promedio": 15, "meta": 5}


@pytest.mark.parametrize("cuerpo", [{"promedio": 101}, {"promedio": -1}, {"meta": 150}, {"meta": -5}])
def test_it206_configuracion_fuera_de_rango_es_400(ana, cuerpo):
    assert ana.patch("/estadisticas/desperdicio/configuracion", json=cuerpo).status_code == 400


def test_it207_historial_registra_compras_y_consumos(ana):
    ids = ana.comprar("Leche", cantidad=3)
    ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 1})
    texto = str(ana.get("/estadisticas/historial").json())
    assert "Leche" in texto


def test_it208_ranking_cuenta_veces_comprado(ana):
    for _ in range(3):
        ana.comprar("Leche")
    ana.comprar("Arroz", categoria="Granos", unidad="Kilogramo")
    ranking = ana.get("/estadisticas/ranking-productos", params={"periodo": "total"}).json()
    assert ranking[0]["producto_nombre"] == "Leche"


def test_it209_productos_de_una_categoria_con_stock(ana, beto):
    ana.comprar("Leche", cantidad=2)
    ana.comprar("Leche", cantidad=1)                       # segunda compra del mismo producto
    cid = ana.categoria_id("Lácteos")
    datos = ana.get(f"/estadisticas/distribucion-categorias/{cid}/productos").json()
    assert "Leche" in str(datos)
    assert ana.get("/estadisticas/distribucion-categorias/99999/productos").status_code == 404
    assert ana.get(f"/estadisticas/distribucion-categorias/{beto.categoria_id('Lácteos')}/productos").status_code == 404
