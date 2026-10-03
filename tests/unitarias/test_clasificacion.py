"""Pruebas unitarias: clasificación de lotes según su fecha de vencimiento."""
from datetime import date, timedelta

import pytest

from clasificacion import calcular_dias_restantes, calcular_estado, UMBRAL_PROXIMO_DIAS


def en(dias):
    return date.today() + timedelta(days=dias)


def test_ut01_dias_restantes_futuro():
    assert calcular_dias_restantes(en(7)) == 7


def test_ut02_dias_restantes_hoy_es_cero():
    assert calcular_dias_restantes(en(0)) == 0


def test_ut03_dias_restantes_pasado_es_negativo():
    assert calcular_dias_restantes(en(-3)) == -3


@pytest.mark.parametrize(
    "dias, esperado",
    [
        (-30, "vencido"),
        (-1, "vencido"),
        (0, "vencido"),            # el día de vencimiento ya cuenta como vencido
        (1, "proximo_a_vencer"),
        (UMBRAL_PROXIMO_DIAS, "proximo_a_vencer"),   # 5 días: último día "próximo"
        (UMBRAL_PROXIMO_DIAS + 1, "vigente"),        # 6 días: ya es vigente
        (60, "vigente"),
    ],
)
def test_ut04_estado_segun_dias(dias, esperado):
    assert calcular_estado(en(dias)) == esperado


def test_ut05_umbral_es_cinco_dias():
    assert UMBRAL_PROXIMO_DIAS == 5
