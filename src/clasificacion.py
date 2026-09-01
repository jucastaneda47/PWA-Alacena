from datetime import date

UMBRAL_PROXIMO_DIAS = 5

def calcular_dias_restantes(fecha_vencimiento: date) -> int:
    """Días que faltan para el vencimiento (negativo si ya venció)."""
    return (fecha_vencimiento - date.today()).days


def calcular_estado(fecha_vencimiento: date) -> str:
    """
    Clasifica un lote según los días restantes hasta su vencimiento:
    - vencido: hoy ya pasó (o es) la fecha de vencimiento
    - proximo_a_vencer: quedan 5 días o menos
    - vigente: quedan más de 5 días
    """
    dias_restantes = calcular_dias_restantes(fecha_vencimiento)

    if dias_restantes <= 0:
        return "vencido"
    if dias_restantes <= UMBRAL_PROXIMO_DIAS:
        return "proximo_a_vencer"
    return "vigente"