"""Pruebas de integración: registro, verificación por PIN, login, sesión,
avatar y recuperación de contraseña (API + base de datos + correo simulado)."""
from datetime import datetime, timedelta

from jose import jwt
from sqlmodel import select

import usuarios
from modelos import usuariodb, categoriadb, unidadmedidadb
from conftest import CLAVE_VALIDA


def cuerpo(**cambios):
    base = {"name": "Ana", "correo": "ana@correo.com", "username": "ana", "contraseña": CLAVE_VALIDA}
    base.update(cambios)
    return base


# ============================ Registro ============================
def test_it01_registro_exitoso_envia_pin_y_no_verifica(cliente, bandeja, sesion_bd):
    r = cliente.post("/usuario", json=cuerpo())
    assert r.status_code == 200
    u = sesion_bd.exec(select(usuariodb)).one()
    assert u.esta_verificado is False
    assert bandeja["pines"] == [("ana@correo.com", u.pin_verificacion)]
    assert len(u.pin_verificacion) == 6


def test_it02_contraseña_se_guarda_cifrada(cliente, sesion_bd):
    cliente.post("/usuario", json=cuerpo())
    u = sesion_bd.exec(select(usuariodb)).one()
    assert u.contraseña != CLAVE_VALIDA
    assert u.contraseña.startswith("$argon2")


def test_it03_registro_siembra_categorias_y_unidades_propias(cliente, sesion_bd):
    cliente.post("/usuario", json=cuerpo())
    u = sesion_bd.exec(select(usuariodb)).one()
    assert len(sesion_bd.exec(select(categoriadb).where(categoriadb.usuario_id == u.id)).all()) == 11
    assert len(sesion_bd.exec(select(unidadmedidadb).where(unidadmedidadb.usuario_id == u.id)).all()) == 4


def test_it04_username_repetido_sin_distinguir_mayusculas(cliente):
    cliente.post("/usuario", json=cuerpo(username="M19MOCHO"))
    r = cliente.post("/usuario", json=cuerpo(username="m19mocho", correo="otro@correo.com"))
    assert r.status_code == 400
    assert r.json()["detail"] == "Ese nombre de usuario ya está en uso"


def test_it05_correo_repetido_sin_distinguir_mayusculas(cliente):
    cliente.post("/usuario", json=cuerpo())
    r = cliente.post("/usuario", json=cuerpo(username="otra", correo="ANA@CORREO.COM"))
    assert r.status_code == 400
    assert r.json()["detail"] == "Ese correo ya está registrado"


def test_it06_correo_se_guarda_en_minusculas(cliente, sesion_bd):
    cliente.post("/usuario", json=cuerpo(correo="Ana@Correo.COM"))
    assert sesion_bd.exec(select(usuariodb)).one().correo == "ana@correo.com"


def test_it07_contraseña_debil_devuelve_422(cliente):
    r = cliente.post("/usuario", json=cuerpo(contraseña="12345678"))
    assert r.status_code == 422


def test_it08_correo_invalido_devuelve_422(cliente):
    assert cliente.post("/usuario", json=cuerpo(correo="ana@")).status_code == 422


def test_it09_faltan_campos_devuelve_422(cliente):
    assert cliente.post("/usuario", json={"name": "Ana"}).status_code == 422


# ============================ PIN ============================
def test_it10_pin_correcto_verifica_la_cuenta(cliente, bandeja, sesion_bd):
    cliente.post("/usuario", json=cuerpo())
    pin = bandeja["pines"][-1][1]
    r = cliente.post("/verificar-pin", json={"correo": "ana@correo.com", "pin": pin})
    assert r.status_code == 200
    u = sesion_bd.exec(select(usuariodb)).one()
    assert u.esta_verificado is True and u.pin_verificacion is None


def test_it11_pin_incorrecto(cliente):
    cliente.post("/usuario", json=cuerpo())
    r = cliente.post("/verificar-pin", json={"correo": "ana@correo.com", "pin": "000000"})
    assert r.status_code == 400 and r.json()["detail"] == "PIN incorrecto"


def test_it12_pin_expirado(cliente, bandeja, sesion_bd):
    cliente.post("/usuario", json=cuerpo())
    u = sesion_bd.exec(select(usuariodb)).one()
    u.pin_expiracion = datetime.utcnow() - timedelta(minutes=1)
    sesion_bd.add(u); sesion_bd.commit()
    r = cliente.post("/verificar-pin", json={"correo": "ana@correo.com", "pin": bandeja["pines"][-1][1]})
    assert r.status_code == 400 and "expirado" in r.json()["detail"]


def test_it13_pin_de_usuario_inexistente(cliente):
    r = cliente.post("/verificar-pin", json={"correo": "nadie@correo.com", "pin": "123456"})
    assert r.status_code == 404


def test_it14_verificar_cuenta_ya_verificada(cliente, ana):
    r = cliente.post("/verificar-pin", json={"correo": "ana@correo.com", "pin": "999999"})
    assert r.status_code == 200 and "ya estaba verificada" in r.json()["mensaje"]


def test_it15_reenviar_pin_genera_uno_nuevo(cliente, bandeja, sesion_bd):
    cliente.post("/usuario", json=cuerpo())
    r = cliente.post("/reenviar-pin", params={"correo": "ANA@correo.com"})
    assert r.status_code == 200
    assert len(bandeja["pines"]) == 2
    assert sesion_bd.exec(select(usuariodb)).one().pin_verificacion == bandeja["pines"][-1][1]


def test_it16_reenviar_pin_inexistente_o_ya_verificada(cliente, ana, bandeja):
    assert cliente.post("/reenviar-pin", params={"correo": "nadie@correo.com"}).status_code == 404
    antes = len(bandeja["pines"])
    r = cliente.post("/reenviar-pin", params={"correo": "ana@correo.com"})
    assert r.status_code == 200 and len(bandeja["pines"]) == antes


# ============================ Login ============================
def test_it20_login_sin_verificar_correo_es_403(cliente):
    cliente.post("/usuario", json=cuerpo())
    r = cliente.post("/login", data={"username": "ana", "password": CLAVE_VALIDA})
    assert r.status_code == 403


def test_it21_login_con_contraseña_incorrecta_es_401(cliente, ana):
    r = cliente.post("/login", data={"username": "ana", "password": "Incorrecta1!"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Usuario o contraseña incorrectos"


def test_it22_login_usuario_inexistente_mismo_mensaje(cliente):
    r = cliente.post("/login", data={"username": "nadie", "password": CLAVE_VALIDA})
    assert r.status_code == 401
    assert r.json()["detail"] == "Usuario o contraseña incorrectos"


def test_it23_login_no_distingue_mayusculas_en_usuario(cliente, ana):
    r = cliente.post("/login", data={"username": "  ANA ", "password": CLAVE_VALIDA})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"


def test_it24_contraseña_si_distingue_mayusculas(cliente, ana):
    r = cliente.post("/login", data={"username": "ana", "password": CLAVE_VALIDA.lower()})
    assert r.status_code == 401


# ============================ Sesión / token ============================
def test_it30_autorizado_devuelve_el_usuario(ana):
    r = ana.get("/autorizado")
    assert r.status_code == 200 and r.json()["username"] == "ana"


def test_it31_sin_token_es_401(cliente):
    assert cliente.get("/autorizado").status_code == 401
    assert cliente.get("/categorias").status_code == 401


def test_it32_token_basura_es_401_no_500(cliente):
    r = cliente.get("/autorizado", headers={"Authorization": "Bearer esto-no-es-un-jwt"})
    assert r.status_code == 401


def test_it33_token_vencido_es_401(cliente, ana, sesion_bd):
    uid = sesion_bd.exec(select(usuariodb)).one().id
    vencido = jwt.encode(
        {"sub": str(uid), "exp": datetime.utcnow() - timedelta(minutes=1)},
        usuarios.algo2, algorithm=usuarios.algo,
    )
    r = cliente.get("/autorizado", headers={"Authorization": f"Bearer {vencido}"})
    assert r.status_code == 401 and "Sesión expirada" in r.json()["detail"]


def test_it34_token_firmado_con_otra_clave_es_401(cliente, ana, sesion_bd):
    uid = sesion_bd.exec(select(usuariodb)).one().id
    falso = jwt.encode({"sub": str(uid), "exp": datetime.utcnow() + timedelta(minutes=5)},
                       "otra-clave", algorithm="HS256")
    assert cliente.get("/autorizado", headers={"Authorization": f"Bearer {falso}"}).status_code == 401


def test_it35_token_de_usuario_que_ya_no_existe_es_401(cliente):
    token = jwt.encode({"sub": "9999", "exp": datetime.utcnow() + timedelta(minutes=5)},
                       usuarios.algo2, algorithm=usuarios.algo)
    assert cliente.get("/autorizado", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_it36_token_dura_diez_minutos(ana):
    datos = jwt.decode(ana.token, usuarios.algo2, algorithms=[usuarios.algo])
    restante = datetime.utcfromtimestamp(datos["exp"]) - datetime.utcnow()
    assert timedelta(minutes=9) < restante <= timedelta(minutes=10)


def test_it37_renovar_sesion_entrega_token_valido(cliente, ana):
    r = ana.post("/renovar-sesion")
    assert r.status_code == 200
    nuevo = r.json()["access_token"]
    assert cliente.get("/autorizado", headers={"Authorization": f"Bearer {nuevo}"}).status_code == 200


def test_it38_renovar_sesion_exige_token_valido(cliente):
    assert cliente.post("/renovar-sesion").status_code == 401


# ============================ Avatar ============================
def test_it40_guardar_avatar_y_verlo_al_volver_a_entrar(cliente, ana):
    assert ana.put("/avatar", json={"avatar": "a7"}).json() == {"avatar": "a7"}
    r = cliente.post("/login", data={"username": "ana", "password": CLAVE_VALIDA})
    token = r.json()["access_token"]
    datos = cliente.get("/autorizado", headers={"Authorization": f"Bearer {token}"}).json()
    assert datos["avatar"] == "a7"


def test_it41_quitar_avatar(ana):
    ana.put("/avatar", json={"avatar": "a3"})
    assert ana.put("/avatar", json={"avatar": None}).json() == {"avatar": None}


def test_it42_avatar_invalido_es_422(ana):
    assert ana.put("/avatar", json={"avatar": "a99"}).status_code == 422


def test_it43_avatar_es_independiente_por_usuario(ana, beto):
    ana.put("/avatar", json={"avatar": "a2"})
    assert beto.get("/autorizado").json()["avatar"] is None


# ============================ Recuperar contraseña ============================
def test_it50_recuperar_envia_enlace_con_token(cliente, ana, bandeja):
    r = cliente.post("/recuperar-contrasena", json={"correo": "ana@correo.com"})
    assert r.status_code == 200
    destinatario, token = bandeja["recuperaciones"][-1]
    assert destinatario == "ana@correo.com" and len(token) >= 40


def test_it51_recuperar_correo_inexistente_es_404(cliente):
    assert cliente.post("/recuperar-contrasena", json={"correo": "x@correo.com"}).status_code == 404


def test_it52_restablecer_cambia_la_contraseña(cliente, ana, bandeja):
    cliente.post("/recuperar-contrasena", json={"correo": "ana@correo.com"})
    token = bandeja["recuperaciones"][-1][1]
    r = cliente.post("/restablecer-contrasena", json={"token": token, "nueva_contraseña": "Nueva456?"})
    assert r.status_code == 200
    assert cliente.post("/login", data={"username": "ana", "password": "Nueva456?"}).status_code == 200
    assert cliente.post("/login", data={"username": "ana", "password": CLAVE_VALIDA}).status_code == 401


def test_it53_el_enlace_solo_sirve_una_vez(cliente, ana, bandeja):
    cliente.post("/recuperar-contrasena", json={"correo": "ana@correo.com"})
    token = bandeja["recuperaciones"][-1][1]
    cliente.post("/restablecer-contrasena", json={"token": token, "nueva_contraseña": "Nueva456?"})
    r = cliente.post("/restablecer-contrasena", json={"token": token, "nueva_contraseña": "Otra789?x"})
    assert r.status_code == 400 and "inválido o ya fue usado" in r.json()["detail"]


def test_it54_token_inexistente_es_400(cliente):
    r = cliente.post("/restablecer-contrasena", json={"token": "inventado", "nueva_contraseña": "Nueva456?"})
    assert r.status_code == 400


def test_it55_token_expirado_es_400(cliente, ana, bandeja, sesion_bd):
    cliente.post("/recuperar-contrasena", json={"correo": "ana@correo.com"})
    u = sesion_bd.exec(select(usuariodb)).one()
    u.token_recuperacion_expiracion = datetime.utcnow() - timedelta(minutes=1)
    sesion_bd.add(u); sesion_bd.commit()
    r = cliente.post("/restablecer-contrasena",
                     json={"token": bandeja["recuperaciones"][-1][1], "nueva_contraseña": "Nueva456?"})
    assert r.status_code == 400 and "expiró" in r.json()["detail"]


def test_it56_nueva_contraseña_debil_es_422(cliente, ana, bandeja):
    cliente.post("/recuperar-contrasena", json={"correo": "ana@correo.com"})
    r = cliente.post("/restablecer-contrasena",
                     json={"token": bandeja["recuperaciones"][-1][1], "nueva_contraseña": "corta"})
    assert r.status_code == 422
