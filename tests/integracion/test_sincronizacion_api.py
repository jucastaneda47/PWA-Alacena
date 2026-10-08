"""Pruebas de integración: compras registradas sin conexión y enviadas después (sincronización)."""
from datetime import date, timedelta

from sqlmodel import select

from modelos import compradb, lotedb, productodb


def fecha(dias):
    return str(date.today() + timedelta(days=dias))


def cuerpo(ana, cliente_id="cliente-0001", lineas=None, fecha_compra=None):
    if lineas is None:
        lineas = [{
            "nombre_nuevo": "Leche", "categoria_id": ana.categoria_id("Lácteos"),
            "unidad_de_medida_id": ana.unidad_id("Litro"),
            "fecha_vencimiento": fecha(10), "cantidad_inicial": 3,
        }]
    return {"cliente_id": cliente_id, "fecha_compra": fecha_compra or str(date.today()), "lineas": lineas}


def test_it200_sincroniza_compra_con_producto_nuevo(ana, sesion_bd):
    r = ana.post("/compras/sincronizar", json=cuerpo(ana))
    assert r.status_code == 200
    d = r.json()
    assert d["repetida"] is False and len(d["lotes"]) == 1
    assert len(sesion_bd.exec(select(compradb)).all()) == 1
    lote = sesion_bd.exec(select(lotedb)).one()
    assert lote.cantidad_actual == 3 and lote.compra_id == d["compra_id"]
    assert [p.nombre for p in sesion_bd.exec(select(productodb)).all()] == ["Leche"]
    assert ana.get("/inventario").status_code == 200


def test_it201_reenviar_la_misma_compra_no_duplica(ana, sesion_bd):
    primero = ana.post("/compras/sincronizar", json=cuerpo(ana)).json()
    segundo = ana.post("/compras/sincronizar", json=cuerpo(ana)).json()
    assert segundo["repetida"] is True and segundo["compra_id"] == primero["compra_id"]
    assert len(sesion_bd.exec(select(compradb)).all()) == 1
    assert len(sesion_bd.exec(select(lotedb)).all()) == 1
    assert len(sesion_bd.exec(select(productodb)).all()) == 1


def test_it202_compras_distintas_se_crean_por_separado(ana, sesion_bd):
    ana.post("/compras/sincronizar", json=cuerpo(ana, "cliente-0001"))
    ana.post("/compras/sincronizar", json=cuerpo(ana, "cliente-0002"))
    assert len(sesion_bd.exec(select(compradb)).all()) == 2
    assert len(sesion_bd.exec(select(productodb)).all()) == 1      # "Leche" se reutiliza
    assert len(sesion_bd.exec(select(lotedb)).all()) == 2


def test_it203_con_producto_existente(ana, sesion_bd):
    pid = ana.comprar("Arroz", categoria="Granos", unidad="Kilogramo")["producto"]
    r = ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=[
        {"producto_id": pid, "fecha_vencimiento": fecha(30), "cantidad_inicial": 2}]))
    assert r.status_code == 200
    assert len(sesion_bd.exec(select(productodb)).all()) == 1
    assert len(sesion_bd.exec(select(lotedb)).all()) == 2


def test_it204_si_una_linea_falla_no_se_guarda_nada(ana, sesion_bd):
    buena = {"nombre_nuevo": "Yogur", "categoria_id": ana.categoria_id("Lácteos"),
             "unidad_de_medida_id": ana.unidad_id("Litro"), "fecha_vencimiento": fecha(5), "cantidad_inicial": 1}
    mala = {"producto_id": 99999, "fecha_vencimiento": fecha(5), "cantidad_inicial": 1}
    r = ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=[buena, mala]))
    assert r.status_code == 400 and "Producto 2" in r.json()["detail"]
    assert sesion_bd.exec(select(compradb)).all() == []
    assert sesion_bd.exec(select(lotedb)).all() == []
    assert sesion_bd.exec(select(productodb)).all() == []          # ni el producto nuevo de la línea 1
    # y se puede reintentar con el mismo cliente_id una vez corregido
    assert ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=[buena])).status_code == 200


def test_it205_validaciones_de_las_lineas(ana):
    base = {"nombre_nuevo": "X", "categoria_id": ana.categoria_id("Lácteos"),
            "unidad_de_medida_id": ana.unidad_id("Litro"), "fecha_vencimiento": fecha(5), "cantidad_inicial": 1}
    assert ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=[{**base, "cantidad_inicial": 0}])).status_code == 400
    assert ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=[{**base, "cantidad_inicial": -2}])).status_code == 400
    assert ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=[{**base, "nombre_nuevo": "  "}])).status_code == 400
    assert ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=[{**base, "categoria_id": 99999}])).status_code == 400
    assert ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=[])).status_code == 422
    assert ana.post("/compras/sincronizar", json=cuerpo(ana, cliente_id="corto")).status_code == 422


def test_it206_la_fecha_de_vencimiento_se_compara_con_la_fecha_de_la_compra(ana):
    # Compra hecha sin conexión hace 2 días, vence ayer: ya llegó vencida pero es válida
    linea = {"nombre_nuevo": "Pan", "categoria_id": ana.categoria_id("Lácteos"),
             "unidad_de_medida_id": ana.unidad_id("Litro"), "fecha_vencimiento": fecha(-1), "cantidad_inicial": 1}
    r = ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=[linea], fecha_compra=fecha(-2)))
    assert r.status_code == 200
    # Pero no puede vencer antes de la fecha de la compra
    linea2 = {**linea, "fecha_vencimiento": fecha(-3)}
    r = ana.post("/compras/sincronizar", json=cuerpo(ana, "cliente-0002", lineas=[linea2], fecha_compra=fecha(-2)))
    assert r.status_code == 400


def test_it207_nombre_repetido_con_otra_unidad_se_rechaza_completo(ana, sesion_bd):
    ana.comprar("Leche")                                            # Lácteos / Litro
    linea = {"nombre_nuevo": "LECHE", "categoria_id": ana.categoria_id("Lácteos"),
             "unidad_de_medida_id": ana.unidad_id("Gramo"), "fecha_vencimiento": fecha(5), "cantidad_inicial": 1}
    r = ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=[linea]))
    assert r.status_code == 400 and "Ya existe" in r.json()["detail"]
    assert len(sesion_bd.exec(select(compradb)).all()) == 1         # solo la compra de ana.comprar


def test_it208_cada_usuario_tiene_su_propio_cliente_id(ana, beto, sesion_bd):
    ana.post("/compras/sincronizar", json=cuerpo(ana, "cliente-0001"))
    r = beto.post("/compras/sincronizar", json=cuerpo(beto, "cliente-0001"))
    assert r.status_code == 200 and r.json()["repetida"] is False
    assert len(sesion_bd.exec(select(compradb)).all()) == 2


def test_it209_no_se_puede_usar_producto_ajeno(ana, beto):
    pid = beto.comprar("Arroz", categoria="Granos", unidad="Kilogramo")["producto"]
    r = ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=[
        {"producto_id": pid, "fecha_vencimiento": fecha(5), "cantidad_inicial": 1}]))
    assert r.status_code == 400


def test_it210_requiere_sesion(cliente, ana):
    assert cliente.post("/compras/sincronizar", json=cuerpo(ana)).status_code == 401
