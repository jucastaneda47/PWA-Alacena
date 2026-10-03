"""Pruebas unitarias: contenido de los correos (sin enviarlos de verdad)."""
import asyncio

import correo


def capturar(monkeypatch):
    enviados = []

    async def falso(self, mensaje):
        enviados.append(mensaje)

    monkeypatch.setattr(correo.FastMail, "send_message", falso)
    return enviados


def test_ut90_correo_del_pin(monkeypatch):
    enviados = capturar(monkeypatch)
    asyncio.run(correo.enviar_pin_verificacion("ana@correo.com", "123456"))
    m = enviados[0]
    assert len(m.recipients) == 1 and "ana@correo.com" in str(m.recipients[0])
    assert m.subject == "Verifica tu cuenta"
    assert "123456" in m.body and "10 minutos" in m.body


def test_ut91_correo_de_recuperacion_trae_el_enlace(monkeypatch):
    enviados = capturar(monkeypatch)
    asyncio.run(correo.enviar_correo_recuperacion("ana@correo.com", "TOKEN-XYZ"))
    m = enviados[0]
    assert f"{correo.FRONTEND_URL}/restablecer-contrasena?token=TOKEN-XYZ" in m.body
    assert "FreshLog" in m.body and "30 minutos" in m.body
    assert "Haz clic aquí" in m.body


def test_ut92_los_correos_no_usan_voseo():
    import inspect
    texto = inspect.getsource(correo)
    for palabra in ("vos ", "podés", "Hacé", "tenés", "Ingresá"):
        assert palabra not in texto
