"""Pruebas unitarias: validaciones de datos (contraseña, correo, usuario, avatar)."""
import pytest
from pydantic import ValidationError

from modelos import (
    usuariocreate,
    validar_reglas_contraseña,
    actualizaravatar,
    restablecercontrasena,
    verificarpin,
    solicitarrecuperacion,
)


def datos_usuario(**cambios):
    base = {"name": "Ana", "correo": "ana@correo.com", "username": "ana", "contraseña": "Segura123!"}
    base.update(cambios)
    return base


# ---------- Contraseña ----------
def test_ut10_contraseña_valida():
    assert validar_reglas_contraseña("Segura123!") == "Segura123!"


@pytest.mark.parametrize(
    "clave, mensaje",
    [
        ("Ab1!", "mínimo 8"),
        ("segura123!", "mayúscula"),
        ("SEGURA123!", "minúscula"),
        ("Segura!!!!", "número"),
        ("Segura1234", "especial"),
    ],
)
def test_ut11_contraseña_incumple_una_regla(clave, mensaje):
    with pytest.raises(ValueError) as error:
        validar_reglas_contraseña(clave)
    assert mensaje in str(error.value)


def test_ut12_registro_rechaza_contraseña_debil():
    with pytest.raises(ValidationError):
        usuariocreate(**datos_usuario(contraseña="debil"))


def test_ut13_restablecer_usa_las_mismas_reglas():
    with pytest.raises(ValidationError):
        restablecercontrasena(token="abc", nueva_contraseña="sinmayuscula1!")
    assert restablecercontrasena(token="abc", nueva_contraseña="Nueva123!").token == "abc"


# ---------- Correo ----------
def test_ut20_correo_se_guarda_en_minusculas():
    u = usuariocreate(**datos_usuario(correo="  ANA@Correo.COM "))
    assert u.correo == "ana@correo.com"


def test_ut21_correo_invalido_se_rechaza():
    with pytest.raises(ValidationError):
        usuariocreate(**datos_usuario(correo="no-es-un-correo"))


def test_ut22_pin_y_recuperacion_normalizan_correo():
    assert verificarpin(correo="ANA@Correo.com", pin="123456").correo == "ana@correo.com"
    assert solicitarrecuperacion(correo="ANA@Correo.com").correo == "ana@correo.com"


# ---------- Nombre de usuario ----------
def test_ut30_username_conserva_mayusculas_y_quita_espacios():
    u = usuariocreate(**datos_usuario(username="  M19MOCHO  "))
    assert u.username == "M19MOCHO"


def test_ut31_username_vacio_se_rechaza():
    with pytest.raises(ValidationError):
        usuariocreate(**datos_usuario(username="   "))


# ---------- Avatar ----------
@pytest.mark.parametrize("avatar", ["a1", "a9", "a10", "a12", None])
def test_ut40_avatar_valido(avatar):
    assert actualizaravatar(avatar=avatar).avatar == avatar


@pytest.mark.parametrize("avatar", ["a0", "a13", "a", "x1", "A1", "a01", "a1 ", "<script>"])
def test_ut41_avatar_invalido(avatar):
    with pytest.raises(ValidationError):
        actualizaravatar(avatar=avatar)
