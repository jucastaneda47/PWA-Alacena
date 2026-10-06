import random
import os
import httpx
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

# --- Envío por SMTP (Gmail). Se usa en tu computador, o donde el servidor permita SMTP ---
conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("EMAIL_SENDER"),
    MAIL_PASSWORD=os.getenv("EMAIL_APP_PASSWORD"),
    MAIL_FROM=os.getenv("EMAIL_SENDER"),
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)

# --- URL del frontend, para armar los links que van dentro de los correos ---
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

PIN_VALIDEZ_MINUTOS = 10
TOKEN_RECUPERACION_VALIDEZ_MINUTOS = 30


BREVO_URL = "https://api.brevo.com/v3/smtp/email"


async def _enviar(destinatario: str, asunto: str, cuerpo_html: str) -> None:
    """
    Envía un correo HTML.
    - Si existe BREVO_API_KEY en el entorno, lo envía por la API de Brevo (HTTPS). Es lo que
      se usa en producción, porque los servidores gratuitos suelen bloquear el SMTP.
    - Si no existe, lo envía por SMTP con Gmail, como siempre.
    """
    api_key = os.getenv("BREVO_API_KEY")
    if api_key:
        remitente = os.getenv("BREVO_SENDER") or os.getenv("EMAIL_SENDER")
        if not remitente:
            raise RuntimeError("Falta BREVO_SENDER (o EMAIL_SENDER) para enviar correos por Brevo.")
        datos = {
            "sender": {"name": "FreshLog", "email": remitente},
            "to": [{"email": destinatario}],
            "subject": asunto,
            "htmlContent": cuerpo_html,
        }
        async with httpx.AsyncClient(timeout=20) as cliente:
            resp = await cliente.post(
                BREVO_URL,
                json=datos,
                headers={"api-key": api_key, "accept": "application/json"},
            )
        if resp.status_code >= 300:
            raise RuntimeError(f"Brevo rechazó el correo ({resp.status_code}): {resp.text[:200]}")
        return

    mensaje = MessageSchema(
        subject=asunto,
        recipients=[destinatario],
        body=cuerpo_html,
        subtype=MessageType.html,
    )
    await FastMail(conf).send_message(mensaje)


def generar_pin() -> str:
    """Genera un PIN numérico de 6 dígitos."""
    return str(random.randint(100000, 999999))


async def enviar_pin_verificacion(destinatario: str, pin: str) -> None:
    """Envía un correo con el PIN de verificación al usuario registrado."""
    cuerpo = f"""
    <p>Hola,</p>
    <p>Tu código de verificación es: <strong>{pin}</strong></p>
    <p>Este código expira en {PIN_VALIDEZ_MINUTOS} minutos. Si no fuiste tu
    quien intentó registrarse, puedes ignorar este mensaje.</p>
    """

    await _enviar(destinatario, "Verifica tu cuenta", cuerpo)
async def enviar_correo_recuperacion(destinatario: str, token: str) -> None:
    """Envía el correo de 'Olvidé mi contraseña' con el enlace para restablecerla."""
    link = f"{FRONTEND_URL}/restablecer-contrasena?token={token}"
    cuerpo = f"""
    <p>Hola,</p>
    <p>Recibimos una solicitud para restablecer tu contraseña de FreshLog.</p>
    <p><a href="{link}">Haz clic aquí para crear una nueva contraseña</a></p>
    <p>Este enlace expira en {TOKEN_RECUPERACION_VALIDEZ_MINUTOS} minutos. Si no
    fuiste tu quien lo solicitó, puedes ignorar este mensaje: tu contraseña
    actual sigue funcionando igual.</p>
    """

    await _enviar(destinatario, "Restablecer tu contraseña", cuerpo)
