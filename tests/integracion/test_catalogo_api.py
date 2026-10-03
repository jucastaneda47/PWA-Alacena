"""Pruebas de integración: categorías, unidades de medida y productos
(unicidad sin distinguir mayúsculas, borrado lógico y productos huérfanos)."""


# ============================ Categorías ============================
def test_it60_lista_las_once_categorias_predeterminadas(ana):
    nombres = {c["nombre"] for c in ana.get("/categorias").json()}
    assert len(nombres) == 11 and {"Lácteos", "Granos", "Panadería"} <= nombres


def test_it61_crear_categoria(ana):
    r = ana.post("/categorias", json={"nombre": "  Dulces ", "icono": "candy", "color": "red", "stock_minimo": 2})
    assert r.status_code == 200
    assert r.json()["nombre"] == "Dulces" and r.json()["stock_minimo"] == 2


def test_it62_categoria_repetida_sin_distinguir_mayusculas(ana):
    r = ana.post("/categorias", json={"nombre": "LÁCTEOS"})
    assert r.status_code == 400 and r.json()["detail"] == "Ya tienes una categoría con ese nombre"
    assert ana.post("/categorias", json={"nombre": "lácteos"}).status_code == 400


def test_it63_categoria_repetida_con_ñ_y_tildes(ana):
    ana.post("/categorias", json={"nombre": "Pañales"})
    assert ana.post("/categorias", json={"nombre": "PAÑALES"}).status_code == 400


def test_it64_editar_categoria(ana):
    cid = ana.categoria_id("Granos")
    r = ana.put(f"/categorias/{cid}", json={"nombre": "Cereales", "stock_minimo": 3})
    assert r.status_code == 200 and r.json()["nombre"] == "Cereales"


def test_it65_editar_categoria_a_nombre_existente_falla(ana):
    cid = ana.categoria_id("Granos")
    assert ana.put(f"/categorias/{cid}", json={"nombre": "lácteos"}).status_code == 400


def test_it66_conservar_su_propio_nombre_al_editar_es_valido(ana):
    cid = ana.categoria_id("Granos")
    assert ana.put(f"/categorias/{cid}", json={"nombre": "GRANOS", "color": "red"}).status_code == 200


def test_it67_eliminar_categoria_sin_stock_la_oculta(ana):
    cid = ana.categoria_id("Aseo")
    assert ana.delete(f"/categorias/{cid}").status_code == 200
    assert "Aseo" not in {c["nombre"] for c in ana.get("/categorias").json()}
    assert ana.get(f"/categorias/{cid}").status_code == 404


def test_it68_se_puede_crear_de_nuevo_una_categoria_eliminada(ana):
    ana.delete(f"/categorias/{ana.categoria_id('Aseo')}")
    assert ana.post("/categorias", json={"nombre": "Aseo"}).status_code == 200


def test_it69_no_se_elimina_categoria_con_stock(ana):
    ana.comprar("Leche", categoria="Lácteos")
    r = ana.delete(f"/categorias/{ana.categoria_id('Lácteos')}")
    assert r.status_code == 400 and "Leche" in r.json()["detail"]
    assert "Lácteos" in {c["nombre"] for c in ana.get("/categorias").json()}


def test_it70_categoria_con_stock_vencido_tambien_bloquea(ana):
    ids = ana.comprar("Yogur", categoria="Lácteos")
    ana.put(f"/lotes/{ids['lote']}", json={"fecha_vencimiento": "2020-01-01"})   # lo dejamos vencido
    assert ana.delete(f"/categorias/{ana.categoria_id('Lácteos')}").status_code == 400


def test_it71_categoria_inexistente_o_ajena_es_404(ana, beto):
    assert ana.get("/categorias/99999").status_code == 404
    ajena = beto.categoria_id("Granos")
    assert ana.get(f"/categorias/{ajena}").status_code == 404
    assert ana.put(f"/categorias/{ajena}", json={"nombre": "X"}).status_code == 404
    assert ana.delete(f"/categorias/{ajena}").status_code == 404


# ============================ Unidades de medida ============================
def test_it80_lista_las_cuatro_unidades_predeterminadas(ana):
    assert {u["abreviatura"] for u in ana.get("/unidades-medida").json()} == {"kg", "g", "l", "ml"}


def test_it81_crear_unidad(ana):
    r = ana.post("/unidades-medida", json={"nombre": "Libra", "abreviatura": "lb"})
    assert r.status_code == 200 and r.json()["abreviatura"] == "lb"


def test_it82_unidad_repetida_por_nombre_o_abreviatura(ana):
    msg = "Ya tienes una unidad de medida con ese nombre o abreviatura"
    r = ana.post("/unidades-medida", json={"nombre": "KILOGRAMO", "abreviatura": "kk"})
    assert r.status_code == 400 and r.json()["detail"] == msg
    r = ana.post("/unidades-medida", json={"nombre": "Kilo", "abreviatura": "KG"})
    assert r.status_code == 400 and r.json()["detail"] == msg


def test_it83_editar_unidad_a_valor_repetido_falla(ana):
    gid = ana.unidad_id("Gramo")
    assert ana.put(f"/unidades-medida/{gid}", json={"abreviatura": "KG"}).status_code == 400


def test_it84_eliminar_unidad_sin_stock_la_oculta(ana):
    uid = ana.unidad_id("Mililitro")
    assert ana.delete(f"/unidades-medida/{uid}").status_code == 200
    assert "ml" not in {u["abreviatura"] for u in ana.get("/unidades-medida").json()}


def test_it85_no_se_elimina_unidad_con_stock(ana):
    ana.comprar("Arroz", categoria="Granos", unidad="Kilogramo")
    r = ana.delete(f"/unidades-medida/{ana.unidad_id('Kilogramo')}")
    assert r.status_code == 400 and "Arroz" in r.json()["detail"]


def test_it86_unidad_ajena_es_404(ana, beto):
    assert ana.delete(f"/unidades-medida/{beto.unidad_id('Gramo')}").status_code == 404


# ============================ Productos ============================
def producto(ana, nombre="Leche", categoria="Lácteos", unidad="Litro", **extra):
    return ana.post("/productos", json={
        "nombre": nombre,
        "categoria_id": ana.categoria_id(categoria),
        "unidad_de_medida_id": ana.unidad_id(unidad),
        **extra,
    })


def test_it90_crear_producto(ana):
    r = producto(ana, "  Leche entera ")
    assert r.status_code == 200 and r.json()["nombre"] == "Leche entera"


def test_it91_mismo_producto_se_reutiliza_sin_duplicar(ana):
    a = producto(ana, "Leche").json()
    b = producto(ana, "LECHE").json()
    assert a["id"] == b["id"]
    assert len(ana.get("/productos").json()) == 1


def test_it92_mismo_nombre_con_otra_categoria_se_rechaza(ana):
    producto(ana, "Leche")
    r = producto(ana, "leche", categoria="Bebidas")
    assert r.status_code == 400 and "Ya existe el producto" in r.json()["detail"]


def test_it93_mismo_nombre_con_otra_unidad_se_rechaza(ana):
    producto(ana, "Leche", unidad="Litro")
    assert producto(ana, "Leche", unidad="Mililitro").status_code == 400


def test_it94_producto_con_categoria_inexistente_o_ajena(ana, beto):
    r = ana.post("/productos", json={"nombre": "X", "categoria_id": 99999, "unidad_de_medida_id": ana.unidad_id("Litro")})
    assert r.status_code == 400 and r.json()["detail"] == "La categoría indicada no existe"
    r = ana.post("/productos", json={"nombre": "X", "categoria_id": beto.categoria_id("Granos"),
                                     "unidad_de_medida_id": ana.unidad_id("Litro")})
    assert r.status_code == 400


def test_it95_producto_con_unidad_eliminada_se_rechaza(ana):
    uid = ana.unidad_id("Mililitro")
    ana.delete(f"/unidades-medida/{uid}")
    r = ana.post("/productos", json={"nombre": "X", "categoria_id": ana.categoria_id("Lácteos"), "unidad_de_medida_id": uid})
    assert r.status_code == 400 and "unidad de medida" in r.json()["detail"]


def test_it96_producto_huerfano_se_oculta_y_se_reactiva_al_recrearlo(ana):
    original = producto(ana, "Carne", "Proteína", "Kilogramo").json()
    ana.delete(f"/categorias/{ana.categoria_id('Proteína')}")
    assert ana.get("/productos").json() == []                      # oculto mientras su categoría no exista
    ana.post("/categorias", json={"nombre": "Proteína"})
    nuevo = producto(ana, "carne", "Proteína", "Kilogramo").json()
    assert nuevo["id"] == original["id"]                           # se reactiva el mismo producto
    assert len(ana.get("/productos").json()) == 1


def test_it97_actualizar_producto(ana):
    pid = producto(ana, "Leche").json()["id"]
    r = ana.put(f"/productos/{pid}", json={"nombre": "Leche light", "stock_minimo": 2})
    assert r.status_code == 200 and r.json()["nombre"] == "Leche light" and r.json()["stock_minimo"] == 2


def test_it98_actualizar_a_nombre_de_otro_producto_falla(ana):
    producto(ana, "Leche")
    pid = producto(ana, "Yogur").json()["id"]
    r = ana.put(f"/productos/{pid}", json={"nombre": "LECHE"})
    assert r.status_code == 400 and r.json()["detail"] == "Ya existe otro producto con ese nombre"


def test_it99_stock_minimo_efectivo_producto_o_categoria(ana):
    cid = ana.categoria_id("Lácteos")
    ana.put(f"/categorias/{cid}", json={"stock_minimo": 5})
    sin_propio = producto(ana, "Leche").json()["id"]
    con_propio = producto(ana, "Yogur", stock_minimo=2).json()["id"]
    assert ana.get(f"/productos/{sin_propio}/stock-minimo-efectivo").json() == {"stock_minimo": 5, "origen": "categoria"}
    assert ana.get(f"/productos/{con_propio}/stock-minimo-efectivo").json() == {"stock_minimo": 2, "origen": "producto"}


def test_it100_eliminar_producto_y_404_en_ajeno(ana, beto):
    pid = producto(ana, "Leche").json()["id"]
    assert beto.get(f"/productos/{pid}").status_code == 404
    assert beto.delete(f"/productos/{pid}").status_code == 404
    assert ana.delete(f"/productos/{pid}").status_code == 200
    assert ana.get(f"/productos/{pid}").status_code == 404


def test_it101_obtener_y_editar_unidad(ana):
    uid = ana.unidad_id("Gramo")
    assert ana.get(f"/unidades-medida/{uid}").json()["abreviatura"] == "g"
    r = ana.put(f"/unidades-medida/{uid}", json={"nombre": "Gramos", "abreviatura": "gr"})
    assert r.status_code == 200 and r.json()["nombre"] == "Gramos"
    assert ana.get("/unidades-medida/99999").status_code == 404
    assert ana.put("/unidades-medida/99999", json={"nombre": "X"}).status_code == 404


def test_it102_unidad_eliminada_no_se_puede_consultar(ana):
    uid = ana.unidad_id("Gramo")
    ana.delete(f"/unidades-medida/{uid}")
    assert ana.get(f"/unidades-medida/{uid}").status_code == 404
