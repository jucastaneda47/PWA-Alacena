"""Pruebas de integración: compras, lotes, inventario y consumo."""
from datetime import date, timedelta


def fecha(dias):
    return str(date.today() + timedelta(days=dias))


# ============================ Compras ============================
def test_it110_registrar_y_listar_compras(ana):
    r = ana.post("/compras", json={"fecha_compra": "2026-09-01"})
    assert r.status_code == 200 and r.json()["fecha_compra"] == "2026-09-01"
    ana.post("/compras", json={"fecha_compra": "2026-09-15"})
    fechas = [c["fecha_compra"] for c in ana.get("/compras").json()]
    assert fechas == ["2026-09-15", "2026-09-01"]          # la más reciente primero


def test_it111_compra_sin_fecha_usa_hoy(ana):
    assert ana.post("/compras", json={}).json()["fecha_compra"] == str(date.today())


def test_it112_obtener_y_eliminar_compra(ana):
    cid = ana.post("/compras", json={}).json()["id"]
    assert ana.get(f"/compras/{cid}").status_code == 200
    assert ana.delete(f"/compras/{cid}").status_code == 200
    assert ana.get(f"/compras/{cid}").status_code == 404


def test_it113_compra_ajena_es_404(ana, beto):
    cid = beto.post("/compras", json={}).json()["id"]
    assert ana.get(f"/compras/{cid}").status_code == 404
    assert ana.delete(f"/compras/{cid}").status_code == 404


# ============================ Lotes ============================
def preparar(ana, nombre="Leche"):
    return ana.comprar(nombre)


def test_it120_crear_lote_calcula_estado_y_cantidad_actual(ana):
    ids = ana.comprar("Leche", cantidad=3, dias=10)
    lote = ana.get(f"/lotes/{ids['lote']}").json()
    assert lote["cantidad_actual"] == 3 and lote["estado"] == "vigente"


def test_it121_lote_proximo_a_vencer(ana):
    ids = ana.comprar("Pan", categoria="Panadería", unidad="Kilogramo", dias=3)
    assert ana.get(f"/lotes/{ids['lote']}").json()["estado"] == "proximo_a_vencer"


def test_it122_no_se_permite_fecha_anterior_a_hoy(ana):
    compra = ana.post("/compras", json={}).json()["id"]
    pid = ana.post("/productos", json={"nombre": "Leche", "categoria_id": ana.categoria_id("Lácteos"),
                                        "unidad_de_medida_id": ana.unidad_id("Litro")}).json()["id"]
    r = ana.post("/lotes", json={"producto_id": pid, "compra_id": compra,
                                 "fecha_vencimiento": fecha(-1), "cantidad_inicial": 1})
    assert r.status_code == 400
    assert r.json()["detail"] == "La fecha de vencimiento no puede ser anterior a hoy"


def test_it123_fecha_de_hoy_si_se_permite(ana):
    compra = ana.post("/compras", json={}).json()["id"]
    pid = ana.post("/productos", json={"nombre": "Leche", "categoria_id": ana.categoria_id("Lácteos"),
                                        "unidad_de_medida_id": ana.unidad_id("Litro")}).json()["id"]
    r = ana.post("/lotes", json={"producto_id": pid, "compra_id": compra,
                                 "fecha_vencimiento": fecha(0), "cantidad_inicial": 1})
    assert r.status_code == 200 and r.json()["estado"] == "vencido"


def test_it124_lote_con_compra_o_producto_inexistente(ana):
    r = ana.post("/lotes", json={"producto_id": 999, "compra_id": 999,
                                 "fecha_vencimiento": fecha(5), "cantidad_inicial": 1})
    assert r.status_code == 400 and r.json()["detail"] == "La compra indicada no existe"


def test_it125_no_se_compra_producto_con_categoria_eliminada(ana):
    ids = ana.comprar("Carne", categoria="Proteína", unidad="Kilogramo")
    ana.put(f"/lotes/{ids['lote']}", json={"cantidad_actual": 0})      # sin stock para poder eliminar
    ana.delete(f"/categorias/{ana.categoria_id('Proteína')}")
    r = ana.post("/lotes", json={"producto_id": ids["producto"], "compra_id": ids["compra"],
                                 "fecha_vencimiento": fecha(5), "cantidad_inicial": 1})
    assert r.status_code == 400 and "fue eliminada" in r.json()["detail"]


def test_it126_actualizar_fecha_recalcula_estado(ana):
    ids = ana.comprar("Leche", dias=30)
    r = ana.put(f"/lotes/{ids['lote']}", json={"fecha_vencimiento": fecha(2)})
    assert r.json()["estado"] == "proximo_a_vencer"


def test_it127_actualizar_cantidad_y_eliminar_lote(ana):
    ids = ana.comprar("Leche", cantidad=5)
    assert ana.put(f"/lotes/{ids['lote']}", json={"cantidad_actual": 4}).json()["cantidad_actual"] == 4
    assert ana.delete(f"/lotes/{ids['lote']}").status_code == 200
    assert ana.get(f"/lotes/{ids['lote']}").status_code == 404


def test_it128_lote_ajeno_es_404(ana, beto):
    ids = beto.comprar("Leche")
    assert ana.get(f"/lotes/{ids['lote']}").status_code == 404
    assert ana.put(f"/lotes/{ids['lote']}", json={"cantidad_actual": 0}).status_code == 404
    assert ana.delete(f"/lotes/{ids['lote']}").status_code == 404


# ============================ Inventario ============================
def test_it130_inventario_lista_lotes_con_existencias_ordenados_por_vencimiento(ana):
    ana.comprar("Leche", dias=20)
    ana.comprar("Yogur", dias=3)
    ana.comprar("Arroz", categoria="Granos", unidad="Kilogramo", dias=90)
    items = ana.get("/inventario").json()
    assert [i["producto_nombre"] for i in items] == ["Yogur", "Leche", "Arroz"]
    assert items[0]["estado"] == "proximo_a_vencer" and items[0]["dias_restantes"] == 3
    assert items[0]["unidad_abreviatura"] == "l" and items[0]["categoria_nombre"] == "Lácteos"


def test_it131_inventario_oculta_lotes_agotados(ana):
    ids = ana.comprar("Leche", cantidad=1)
    ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 1})
    assert ana.get("/inventario").json() == []


def test_it132_filtro_por_categoria(ana):
    ana.comprar("Leche")
    ana.comprar("Arroz", categoria="Granos", unidad="Kilogramo")
    cid = ana.categoria_id("Granos")
    items = ana.get("/inventario", params={"categoria_id": cid}).json()
    assert [i["producto_nombre"] for i in items] == ["Arroz"]


def test_it133_filtro_por_estado(ana):
    ana.comprar("Leche", dias=30)
    ana.comprar("Yogur", dias=2)
    assert [i["producto_nombre"] for i in ana.get("/inventario", params={"estado": "proximo_a_vencer"}).json()] == ["Yogur"]
    assert [i["producto_nombre"] for i in ana.get("/inventario", params={"estado": "vigente"}).json()] == ["Leche"]


def test_it134_inventario_marca_vencido_cuando_pasa_la_fecha(ana):
    ids = ana.comprar("Leche", dias=10)
    ana.put(f"/lotes/{ids['lote']}", json={"fecha_vencimiento": "2020-01-01"})
    item = ana.get("/inventario").json()[0]
    assert item["estado"] == "vencido" and item["dias_restantes"] < 0


# ============================ Consumo ============================
def test_it140_consumo_descuenta_del_lote(ana):
    ids = ana.comprar("Leche", cantidad=5)
    r = ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 2})
    assert r.status_code == 200 and r.json()["tipo"] == "consumo" and r.json()["cantidad"] == 2
    assert ana.get(f"/lotes/{ids['lote']}").json()["cantidad_actual"] == 3


def test_it141_no_se_consume_mas_de_lo_disponible(ana):
    ids = ana.comprar("Leche", cantidad=2)
    r = ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 3})
    assert r.status_code == 400 and "quedan 2" in r.json()["detail"]
    assert ana.get(f"/lotes/{ids['lote']}").json()["cantidad_actual"] == 2


def test_it142_cantidad_cero_o_negativa_se_rechaza(ana):
    ids = ana.comprar("Leche", cantidad=2)
    for cantidad in (0, -1):
        r = ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": cantidad})
        assert r.status_code == 400 and r.json()["detail"] == "La cantidad debe ser mayor a 0"


def test_it143_producto_vencido_no_se_puede_consumir(ana):
    ids = ana.comprar("Leche", cantidad=2)
    ana.put(f"/lotes/{ids['lote']}", json={"fecha_vencimiento": "2020-01-01"})
    r = ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 1})
    assert r.status_code == 400 and r.json()["detail"] == "Producto vencido, retírelo de la alacena"
    assert ana.get(f"/lotes/{ids['lote']}").json()["cantidad_actual"] == 2


def test_it144_producto_vencido_si_se_puede_retirar(ana):
    ids = ana.comprar("Leche", cantidad=2)
    ana.put(f"/lotes/{ids['lote']}", json={"fecha_vencimiento": "2020-01-01"})
    r = ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 2, "tipo": "retiro"})
    assert r.status_code == 200 and r.json()["tipo"] == "retiro"
    assert ana.get("/inventario").json() == []


def test_it145_lote_inexistente_o_ajeno_es_404(ana, beto):
    assert ana.post("/consumo", json={"lote_id": 999, "cantidad": 1}).status_code == 404
    ajeno = beto.comprar("Leche")["lote"]
    assert ana.post("/consumo", json={"lote_id": ajeno, "cantidad": 1}).status_code == 404


def test_it146_historial_de_consumo_mas_reciente_primero(ana):
    ids = ana.comprar("Leche", cantidad=10)
    ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 1})
    ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 2})
    historial = ana.get("/consumo").json()
    assert [h["cantidad"] for h in historial] == [2, 1]
