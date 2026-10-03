"""
Pruebas funcionales: recorridos completos desde el punto de vista de la persona
que usa FreshLog. Cada escenario encadena varias acciones reales (registro,
compra, consumo, alertas...) y comprueba el resultado final que vería el usuario.
"""
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from conftest import CLAVE_VALIDA, motor_pruebas
from modelos import alertadb


def test_cf01_registro_completo_y_primer_ingreso(cliente, bandeja):
    """Una persona nueva se registra, confirma su correo, entra y encuentra su alacena lista."""
    # 1. Se registra (con mayúsculas en el correo)
    r = cliente.post("/usuario", json={"name": "Carlos Pérez", "correo": "Carlos@Correo.com",
                                       "username": "Carlos99", "contraseña": CLAVE_VALIDA})
    assert r.status_code == 200
    # 2. Aún no puede entrar
    assert cliente.post("/login", data={"username": "carlos99", "password": CLAVE_VALIDA}).status_code == 403
    # 3. Recibe el PIN en su correo (en minúsculas) y lo confirma
    destinatario, pin = bandeja["pines"][-1]
    assert destinatario == "carlos@correo.com"
    assert cliente.post("/verificar-pin", json={"correo": "carlos@correo.com", "pin": pin}).status_code == 200
    # 4. Ahora sí entra (escribiendo el usuario con otras mayúsculas)
    token = cliente.post("/login", data={"username": "CARLOS99", "password": CLAVE_VALIDA}).json()["access_token"]
    cab = {"Authorization": f"Bearer {token}"}
    # 5. Encuentra sus categorías y unidades listas, y la alacena vacía
    assert len(cliente.get("/categorias", headers=cab).json()) == 11
    assert len(cliente.get("/unidades-medida", headers=cab).json()) == 4
    assert cliente.get("/inventario", headers=cab).json() == []
    assert cliente.get("/alertas", headers=cab).json() == []


def test_cf02_olvide_mi_contraseña(cliente, ana, bandeja):
    """La persona olvida su clave, la restablece por correo y vuelve a entrar."""
    assert cliente.post("/login", data={"username": "ana", "password": "Olvidada1!"}).status_code == 401
    cliente.post("/recuperar-contrasena", json={"correo": "ana@correo.com"})
    token = bandeja["recuperaciones"][-1][1]
    assert cliente.post("/restablecer-contrasena", json={"token": token, "nueva_contraseña": "Brillante9#"}).status_code == 200
    assert cliente.post("/login", data={"username": "ana", "password": "Brillante9#"}).status_code == 200
    # El enlace ya no sirve
    assert cliente.post("/restablecer-contrasena", json={"token": token, "nueva_contraseña": "Otra1234!"}).status_code == 400


def test_cf03_ciclo_de_vida_de_un_producto(ana):
    """Compra → aparece en el inventario → consumo parcial → se agota → alerta de stock mínimo."""
    ids = ana.comprar("Leche", cantidad=3, dias=15, stock_minimo=2)
    # Aparece en el inventario como vigente
    item = ana.get("/inventario").json()[0]
    assert item["producto_nombre"] == "Leche" and item["estado"] == "vigente" and item["cantidad_actual"] == 3
    assert ana.get("/alertas").json() == []                       # stock 3 ≥ mínimo 2: sin alertas
    # Consume 2 → queda 1, por debajo del mínimo
    ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 2})
    alertas = ana.get("/alertas").json()
    assert [a["tipo"] for a in alertas] == ["stock_minimo"]
    assert alertas[0]["cantidad_actual"] == 1 and alertas[0]["stock_minimo"] == 2
    # Consume lo último → sale del inventario
    ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 1})
    assert ana.get("/inventario").json() == []
    # No puede consumir más de lo que no tiene
    assert ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 1}).status_code == 400


def test_cf04_producto_que_vence_se_retira_no_se_consume(ana):
    """Un producto vencido no se consume: el sistema avisa y la persona lo retira."""
    ids = ana.comprar("Yogur", cantidad=2, dias=10, stock_minimo=0)
    ana.put(f"/lotes/{ids['lote']}", json={"fecha_vencimiento": str(date.today() - timedelta(days=2))})
    assert ana.get("/inventario").json()[0]["estado"] == "vencido"
    assert [a["tipo"] for a in ana.get("/alertas").json()] == ["vencido"]
    r = ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 1})
    assert r.status_code == 400 and r.json()["detail"] == "Producto vencido, retírelo de la alacena"
    assert ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 2, "tipo": "retiro"}).status_code == 200
    assert ana.get("/inventario").json() == []


def test_cf05_clasificacion_por_dias_en_el_inventario(ana):
    """El inventario muestra cada lote con su estado según los días que le quedan."""
    ana.comprar("Leche", dias=20)
    ana.comprar("Yogur", dias=4)
    ana.comprar("Queso", dias=5)
    ana.comprar("Mantequilla", categoria="Grasas", dias=6)
    estados = {i["producto_nombre"]: i["estado"] for i in ana.get("/inventario").json()}
    assert estados == {"Leche": "vigente", "Yogur": "proximo_a_vencer",
                       "Queso": "proximo_a_vencer", "Mantequilla": "vigente"}


def test_cf06_no_se_pueden_duplicar_nombres(ana):
    """Categorías, unidades, productos y usuarios no se repiten por mayúsculas."""
    assert ana.post("/categorias", json={"nombre": "LÁCTEOS"}).status_code == 400
    assert ana.post("/unidades-medida", json={"nombre": "litro", "abreviatura": "xx"}).status_code == 400
    ana.comprar("Leche")
    r = ana.post("/productos", json={"nombre": "LECHE", "categoria_id": ana.categoria_id("Lácteos"),
                                     "unidad_de_medida_id": ana.unidad_id("Litro")})
    assert r.status_code == 200 and len(ana.get("/productos").json()) == 1      # reutiliza, no duplica


def test_cf07_eliminar_categoria_y_unidad_con_su_regla(ana):
    """Con productos en la alacena no se elimina; al consumirlos sí, y el producto queda oculto hasta recrearla."""
    ids = ana.comprar("Carne", categoria="Proteína", unidad="Kilogramo", cantidad=1)
    # Bloqueada mientras hay stock
    assert ana.delete(f"/categorias/{ana.categoria_id('Proteína')}").status_code == 400
    assert ana.delete(f"/unidades-medida/{ana.unidad_id('Kilogramo')}").status_code == 400
    # Se consume todo y ya se puede eliminar
    cat_eliminada = ana.categoria_id("Proteína")
    ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 1})
    assert ana.delete(f"/categorias/{ana.categoria_id('Proteína')}").status_code == 200
    assert ana.delete(f"/unidades-medida/{ana.unidad_id('Kilogramo')}").status_code == 200
    # Su producto ya no se ofrece para comprar
    assert ana.get("/productos").json() == []
    # La categoría eliminada no se puede usar para productos nuevos
    r = ana.post("/productos", json={"nombre": "Pollo", "categoria_id": cat_eliminada,
                                     "unidad_de_medida_id": ana.unidad_id("Gramo")})
    assert r.status_code == 400 and r.json()["detail"] == "La categoría indicada no existe"


def test_cf08_producto_huerfano_vuelve_al_recrear_su_categoria(ana):
    ids = ana.comprar("Carne", categoria="Proteína", unidad="Kilogramo", cantidad=1)
    ana.post("/consumo", json={"lote_id": ids["lote"], "cantidad": 1})
    ana.delete(f"/categorias/{ana.categoria_id('Proteína')}")
    ana.post("/categorias", json={"nombre": "Proteína"})
    nuevo = ana.comprar("Carne", categoria="Proteína", unidad="Kilogramo", cantidad=2)
    assert nuevo["producto"] == ids["producto"]                    # es el mismo producto de antes
    assert ana.get("/inventario").json()[0]["cantidad_actual"] == 2


def test_cf09_seguimiento_de_alertas_y_limpieza_del_historial(ana):
    """Aparece la alerta, se atiende, pasa al historial y luego se limpia el historial viejo."""
    ana.comprar("Leche", cantidad=1, dias=2, stock_minimo=0)
    activas = ana.get("/alertas", params={"atendida": False}).json()
    assert len(activas) == 1
    ana.put(f"/alertas/{activas[0]['id']}/atender")
    assert ana.get("/alertas", params={"atendida": False}).json() == []
    assert len(ana.get("/alertas", params={"atendida": True}).json()) == 1
    # El historial es reciente: eliminar lo de hace más de 1 mes no borra nada
    assert ana.delete("/alertas/historial", params={"meses": 1}).json() == {"eliminadas": 0}
    # Pasan 3 meses...
    with Session(motor_pruebas) as s:
        a = s.exec(select(alertadb)).one()
        a.fecha_generada = datetime.utcnow() - timedelta(days=95)
        s.add(a); s.commit()
    assert ana.delete("/alertas/historial", params={"meses": 3}).json() == {"eliminadas": 1}
    assert ana.get("/alertas", params={"atendida": True}).json() == []
    # La alerta borrada no vuelve como pendiente aunque el lote siga próximo a vencer
    assert ana.get("/alertas", params={"atendida": False}).json() == []


def test_cf10_cada_persona_ve_solo_sus_datos(ana, beto):
    """Dos usuarios usando la app a la vez no se mezclan."""
    ana.comprar("Leche", cantidad=1, dias=2, stock_minimo=0)
    beto.comprar("Arroz", categoria="Granos", unidad="Kilogramo", cantidad=1, dias=2, stock_minimo=0)
    assert [i["producto_nombre"] for i in ana.get("/inventario").json()] == ["Leche"]
    assert [i["producto_nombre"] for i in beto.get("/inventario").json()] == ["Arroz"]
    assert [a["producto_nombre"] for a in ana.get("/alertas").json()] == ["Leche"]
    assert len(ana.get("/productos").json()) == 1 and len(beto.get("/productos").json()) == 1
    # Los dos pueden tener una categoría con el mismo nombre
    assert ana.post("/categorias", json={"nombre": "Snacks"}).status_code == 200
    assert beto.post("/categorias", json={"nombre": "Snacks"}).status_code == 200


def test_cf11_perfil_con_avatar_se_conserva_entre_sesiones(cliente, ana):
    ana.put("/avatar", json={"avatar": "a5"})
    token = cliente.post("/login", data={"username": "ana", "password": CLAVE_VALIDA}).json()["access_token"]
    perfil = cliente.get("/autorizado", headers={"Authorization": f"Bearer {token}"}).json()
    assert perfil["avatar"] == "a5" and perfil["username"] == "ana" and perfil["correo"] == "ana@correo.com"


def test_cf12_sesion_se_renueva_mientras_hay_actividad(cliente, ana):
    nuevo = ana.post("/renovar-sesion").json()["access_token"]
    assert cliente.get("/autorizado", headers={"Authorization": f"Bearer {nuevo}"}).status_code == 200
