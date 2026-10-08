"""Pruebas unitarias: contenido de los correos (sin enviarlos de verdad)."""
import asyncio

import correo


def capturar(monkeypatch):
    enviados = []
    # Aunque el .env local tenga BREVO_API_KEY, estas pruebas deben usar el camino SMTP simulado.
    monkeypatch.delenv("BREVO_API_KEY", raising=False)

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


# ============ Envío por Brevo (producción) ============
class _RespuestaFalsa:
    def __init__(self, codigo=201, texto="{}"):
        self.status_code, self.text = codigo, texto


def _cliente_falso(registro, codigo=201):
    class Cliente:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            registro.update(url=url, json=json, headers=headers)
            return _RespuestaFalsa(codigo, "error de prueba")

    return Cliente


def test_ut93_con_api_key_se_envia_por_brevo_y_no_por_smtp(monkeypatch):
    registro = {}
    monkeypatch.setenv("BREVO_API_KEY", "clave-brevo-falsa")
    monkeypatch.setenv("BREVO_SENDER", "remitente@correo.com")
    monkeypatch.setattr(correo.httpx, "AsyncClient", _cliente_falso(registro))

    async def smtp_prohibido(self, mensaje):
        raise AssertionError("No debe usar SMTP cuando hay BREVO_API_KEY")

    monkeypatch.setattr(correo.FastMail, "send_message", smtp_prohibido)
    asyncio.run(correo.enviar_pin_verificacion("ana@correo.com", "123456"))

    assert registro["url"] == correo.BREVO_URL
    assert registro["headers"]["api-key"] == "clave-brevo-falsa"
    assert registro["json"]["to"] == [{"email": "ana@correo.com"}]
    assert registro["json"]["sender"]["email"] == "remitente@correo.com"
    assert "123456" in registro["json"]["htmlContent"]


def test_ut94_si_brevo_rechaza_el_correo_se_avisa(monkeypatch):
    import pytest
    monkeypatch.setenv("BREVO_API_KEY", "clave-brevo-falsa")
    monkeypatch.setenv("BREVO_SENDER", "remitente@correo.com")
    monkeypatch.setattr(correo.httpx, "AsyncClient", _cliente_falso({}, codigo=401))
    with pytest.raises(RuntimeError, match="401"):
        asyncio.run(correo.enviar_correo_recuperacion("ana@correo.com", "TOKEN"))


def test_ut95_sin_api_key_sigue_usando_smtp(monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    enviados = []

    async def falso(self, mensaje):
        enviados.append(mensaje)

    monkeypatch.setattr(correo.FastMail, "send_message", falso)
    asyncio.run(correo.enviar_pin_verificacion("ana@correo.com", "654321"))
    assert len(enviados) == 1

