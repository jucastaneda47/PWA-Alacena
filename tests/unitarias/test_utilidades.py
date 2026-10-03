"""Pruebas unitarias: funciones auxiliares (PIN, fechas, stock, datos predeterminados)."""
from datetime import datetime, date, timedelta

import pytest
from sqlmodel import select

from alertas import _restar_meses, _calcular_stock_producto
from correo import generar_pin, PIN_VALIDEZ_MINUTOS, TOKEN_RECUPERACION_VALIDEZ_MINUTOS
from minimos import (
    sembrar_datos_para_usuario,
    CATEGORIAS_PREDETERMINADAS,
    UNIDADES_PREDETERMINADAS,
)
from modelos import (
    usuariodb, categoriadb, unidadmedidadb, productodb, lotedb, compradb,
)


# ---------- PIN ----------
def test_ut50_pin_tiene_seis_digitos():
    for _ in range(200):
        pin = generar_pin()
        assert len(pin) == 6 and pin.isdigit()


def test_ut51_tiempos_de_validez():
    assert PIN_VALIDEZ_MINUTOS == 10
    assert TOKEN_RECUPERACION_VALIDEZ_MINUTOS == 30


# ---------- Resta de meses (filtro del historial) ----------
@pytest.mark.parametrize(
    "origen, meses, esperado",
    [
        (datetime(2026, 10, 15, 8, 30), 1, datetime(2026, 9, 15, 8, 30)),
        (datetime(2026, 10, 15), 3, datetime(2026, 7, 15)),
        (datetime(2026, 10, 15), 12, datetime(2025, 10, 15)),
        (datetime(2026, 2, 10), 3, datetime(2025, 11, 10)),     # cruza de año
        (datetime(2026, 3, 31), 1, datetime(2026, 2, 28)),      # febrero más corto
        (datetime(2024, 3, 31), 1, datetime(2024, 2, 29)),      # año bisiesto
        (datetime(2026, 8, 31), 6, datetime(2026, 2, 28)),
    ],
)
def test_ut60_restar_meses(origen, meses, esperado):
    assert _restar_meses(origen, meses) == esperado


# ---------- Datos predeterminados por usuario ----------
def crear_usuario_directo(s, username):
    u = usuariodb(name=username, correo=f"{username}@x.co", username=username, contraseña="x")
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


def test_ut70_sembrar_crea_once_categorias_y_cuatro_unidades(sesion_bd):
    u = crear_usuario_directo(sesion_bd, "ana")
    sembrar_datos_para_usuario(u.id)

    cats = sesion_bd.exec(select(categoriadb).where(categoriadb.usuario_id == u.id)).all()
    unis = sesion_bd.exec(select(unidadmedidadb).where(unidadmedidadb.usuario_id == u.id)).all()
    assert len(cats) == len(CATEGORIAS_PREDETERMINADAS) == 11
    assert len(unis) == len(UNIDADES_PREDETERMINADAS) == 4
    assert all(not c.eliminada for c in cats)


def test_ut71_cada_usuario_tiene_su_propia_copia(sesion_bd):
    a = crear_usuario_directo(sesion_bd, "ana")
    b = crear_usuario_directo(sesion_bd, "beto")
    sembrar_datos_para_usuario(a.id)
    sembrar_datos_para_usuario(b.id)

    ids_a = {c.id for c in sesion_bd.exec(select(categoriadb).where(categoriadb.usuario_id == a.id)).all()}
    ids_b = {c.id for c in sesion_bd.exec(select(categoriadb).where(categoriadb.usuario_id == b.id)).all()}
    assert ids_a and ids_b and ids_a.isdisjoint(ids_b)


# ---------- Cálculo de stock ----------
def preparar_producto(s, stock_producto=None, stock_categoria=0.0):
    u = crear_usuario_directo(s, "ana")
    cat = categoriadb(nombre="Lácteos", stock_minimo=stock_categoria, usuario_id=u.id)
    uni = unidadmedidadb(nombre="Litro", abreviatura="l", usuario_id=u.id)
    s.add(cat); s.add(uni); s.commit(); s.refresh(cat); s.refresh(uni)
    prod = productodb(nombre="Leche", categoria_id=cat.id, unidad_de_medida_id=uni.id,
                      stock_minimo=stock_producto, usuario_id=u.id)
    compra = compradb(usuario_id=u.id)
    s.add(prod); s.add(compra); s.commit(); s.refresh(prod); s.refresh(compra)
    return u, prod, compra


def agregar_lote(s, u, prod, compra, cantidad):
    s.add(lotedb(producto_id=prod.id, compra_id=compra.id, usuario_id=u.id,
                 fecha_vencimiento=date.today() + timedelta(days=30),
                 cantidad_inicial=cantidad, cantidad_actual=cantidad))
    s.commit()


def test_ut80_stock_suma_los_lotes_con_existencias(sesion_bd):
    u, prod, compra = preparar_producto(sesion_bd, stock_producto=1)
    agregar_lote(sesion_bd, u, prod, compra, 2)
    agregar_lote(sesion_bd, u, prod, compra, 3)
    agregar_lote(sesion_bd, u, prod, compra, 0)    # lote agotado: no suma
    total, minimo = _calcular_stock_producto(sesion_bd, prod)
    assert total == 5 and minimo == 1


def test_ut81_minimo_propio_tiene_prioridad_sobre_el_de_la_categoria(sesion_bd):
    u, prod, compra = preparar_producto(sesion_bd, stock_producto=4, stock_categoria=9)
    assert _calcular_stock_producto(sesion_bd, prod)[1] == 4


def test_ut82_sin_minimo_propio_hereda_el_de_la_categoria(sesion_bd):
    u, prod, compra = preparar_producto(sesion_bd, stock_producto=None, stock_categoria=9)
    assert _calcular_stock_producto(sesion_bd, prod)[1] == 9
