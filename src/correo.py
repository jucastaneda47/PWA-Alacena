import random
import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

# --- Configuración de conexión (mover a variables de entorno / .env) ---
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


def generar_pin() -> str:
    """Genera un PIN numérico de 6 dígitos."""
    return str(random.randint(100000, 999999))


async def enviar_pin_verificacion(destinatario: str, pin: str) -> None:
    """Envía un correo con el PIN de verificación al usuario registrado."""
    cuerpo = f"""
    <p>Hola,</p>
    <p>Tu código de verificación es: <strong>{pin}</strong></p>
    <p>Este código expira en {PIN_VALIDEZ_MINUTOS} minutos. Si no fuiste vos
    quien intentó registrarse, podés ignorar este mensaje.</p>
    """

    mensaje = MessageSchema(
        subject="Verifica tu cuenta",
        recipients=[destinatario],
        body=cuerpo,
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    await fm.send_message(mensaje)


async def enviar_correo_recuperacion(destinatario: str, token: str) -> None:
    """Envía el correo de 'Olvidé mi contraseña' con el enlace para restablecerla."""
    link = f"{FRONTEND_URL}/restablecer-contrasena?token={token}"
    cuerpo = f"""
    <p>Hola,</p>
    <p>Recibimos una solicitud para restablecer tu contraseña de Alacena.</p>
    <p><a href="{link}">Hacé clic acá para crear una nueva contraseña</a></p>
    <p>Este enlace expira en {TOKEN_RECUPERACION_VALIDEZ_MINUTOS} minutos. Si no
    fuiste vos quien lo solicitó, podés ignorar este mensaje: tu contraseña
    actual sigue funcionando igual.</p>
    """

    mensaje = MessageSchema(
        subject="Restablecer tu contraseña",
        recipients=[destinatario],
        body=cuerpo,
        subtype=MessageType.html,
    )

    fm = FastMail(conf)
    await fm.send_message(mensaje)