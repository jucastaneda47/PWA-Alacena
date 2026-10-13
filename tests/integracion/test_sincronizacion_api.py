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


# ---------- Hora real de la compra en el historial ----------
from datetime import datetime, timedelta as _td


def _evento_compra(ana):
    eventos = ana.get("/estadisticas/historial?tipos=compra").json()["eventos"]
    return [e for e in eventos if e["tipo"] == "compra"][0]


def test_it211_la_compra_guarda_la_hora_real_del_registro(ana, sesion_bd):
    antes = datetime.utcnow()
    ana.post("/compras/sincronizar", json=cuerpo(ana))
    compra = sesion_bd.exec(select(compradb)).one()
    assert compra.fecha_registro is not None
    assert antes - _td(seconds=2) <= compra.fecha_registro <= datetime.utcnow() + _td(seconds=2)
    assert _evento_compra(ana)["fecha"].endswith("Z")  # hora UTC: el navegador la pasa a hora local


def test_it212_compra_sin_conexion_conserva_la_hora_en_que_se_registro(ana, sesion_bd):
    hace_dos_horas = datetime.utcnow() - _td(hours=2)
    c = cuerpo(ana)
    c["registrada_en"] = hace_dos_horas.isoformat() + "Z"
    ana.post("/compras/sincronizar", json=c)
    compra = sesion_bd.exec(select(compradb)).one()
    assert abs((compra.fecha_registro - hace_dos_horas).total_seconds()) < 1


def test_it213_hora_en_el_futuro_se_limita_a_la_actual(ana, sesion_bd):
    c = cuerpo(ana)
    c["registrada_en"] = (datetime.utcnow() + _td(days=3)).isoformat() + "Z"
    ana.post("/compras/sincronizar", json=c)
    compra = sesion_bd.exec(select(compradb)).one()
    assert compra.fecha_registro <= datetime.utcnow() + _td(seconds=2)


def test_it214_compra_antigua_sin_hora_sigue_mostrandose_a_las_9(ana, sesion_bd):
    ana.post("/compras/sincronizar", json=cuerpo(ana))
    compra = sesion_bd.exec(select(compradb)).one()
    compra.fecha_registro = None  # como las compras creadas antes de existir este campo
    sesion_bd.add(compra)
    sesion_bd.commit()
    e = _evento_compra(ana)
    assert e["fecha"] == f"{compra.fecha_compra.isoformat()}T09:00:00"


def test_it215_la_compra_clasica_tambien_guarda_la_hora(ana, sesion_bd):
    ana.post("/compras", json={})
    assert sesion_bd.exec(select(compradb)).one().fecha_registro is not None


def test_it216_se_agrega_la_columna_en_bases_ya_creadas():
    """Una base creada antes de existir fecha_registro la recibe sola al arrancar."""
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.pool import StaticPool
    import db

    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with motor.begin() as c:
        c.execute(text("CREATE TABLE compradb (id INTEGER PRIMARY KEY, usuario_id INTEGER, fecha_compra DATE)"))
        c.execute(text("INSERT INTO compradb (usuario_id, fecha_compra) VALUES (1, '2026-10-08')"))
    db.asegurar_columnas(motor)
    db.asegurar_columnas(motor)  # repetirlo no debe fallar
    assert "fecha_registro" in {col["name"] for col in inspect(motor).get_columns("compradb")}
    with motor.begin() as c:
        assert c.execute(text("SELECT fecha_registro FROM compradb")).scalar() is None


def test_it217_el_vencimiento_se_registra_a_las_00_horas(ana):
    """Un lote vence apenas empieza su día de vencimiento: 00:00, no las 9."""
    lineas = [{
        "nombre_nuevo": "Yogur", "categoria_id": ana.categoria_id("Lácteos"),
        "unidad_de_medida_id": ana.unidad_id("Litro"),
        "fecha_vencimiento": str(date.today()), "cantidad_inicial": 2,
    }]
    ana.post("/compras/sincronizar", json=cuerpo(ana, lineas=lineas))
    eventos = ana.get("/estadisticas/historial?tipos=vencimiento").json()["eventos"]
    venc = [e for e in eventos if e["tipo"] == "vencimiento"]
    assert len(venc) == 1
    assert venc[0]["fecha"] == f"{date.today().isoformat()}T00:00:00"
