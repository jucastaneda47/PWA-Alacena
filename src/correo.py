import random
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from fastapi import APIRouter

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
router=APIRouter()
 
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
 
PIN_VALIDEZ_MINUTOS = 10
 
 
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
 