from modelos import (
    usuariocreate,
    usuariodb,
    verificarpin,
    solicitarrecuperacion,
    restablecercontrasena,
)
from db import sesiondb
from fastapi import APIRouter,HTTPException, status, Depends
from passlib.hash import argon2
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlmodel import select
from datetime import datetime, timedelta
from jose import jwt, JWTError
import secrets
from correo import (
    generar_pin,
    enviar_pin_verificacion,
    PIN_VALIDEZ_MINUTOS,
    enviar_correo_recuperacion,
    TOKEN_RECUPERACION_VALIDEZ_MINUTOS,
)

router = APIRouter()
t_estatico = 10
algo= "HS256"
algo2= "01268c1ebf7200ad045f6af05ff34ad91f9c4e8aabf5e814c827bc9e824e0d98"
oauth2= OAuth2PasswordBearer(tokenUrl="login")

@router.post("/usuario", response_model=usuariodb, tags=["usuario"])
async def crear(conexion: sesiondb, usuario: usuariocreate):
    nuevo_usuario = usuario.model_dump()

    nuevo_usuario["contraseña"] = argon2.hash(
        nuevo_usuario["contraseña"]
    )

    usadb = usuariodb.model_validate(nuevo_usuario)

    # --- Generamos el PIN de verificación ---
    pin = generar_pin()
    usadb.pin_verificacion = pin
    usadb.pin_expiracion = datetime.utcnow() + timedelta(minutes=PIN_VALIDEZ_MINUTOS)
    usadb.esta_verificado = False

    conexion.add(usadb)
    conexion.commit()
    conexion.refresh(usadb)

    # --- Enviamos el correo con el PIN ---
    await enviar_pin_verificacion(usadb.correo, pin)

    return usadb


@router.post("/verificar-pin", tags=["usuario"])
async def verificar_pin(conexion: sesiondb, datos: verificarpin):
    buscar = select(usuariodb).where(usuariodb.correo == datos.correo)
    user = conexion.exec(buscar).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    if user.esta_verificado:
        return {"mensaje": "La cuenta ya estaba verificada"}

    if user.pin_verificacion != datos.pin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PIN incorrecto"
        )

    if user.pin_expiracion is None or user.pin_expiracion < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El PIN ha expirado, solicita uno nuevo"
        )

    user.esta_verificado = True
    user.pin_verificacion = None
    user.pin_expiracion = None
    conexion.add(user)
    conexion.commit()

    return {"mensaje": "Cuenta verificada correctamente"}


@router.post("/reenviar-pin", tags=["usuario"])
async def reenviar_pin(conexion: sesiondb, correo: str):
    buscar = select(usuariodb).where(usuariodb.correo == correo)
    user = conexion.exec(buscar).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    if user.esta_verificado:
        return {"mensaje": "La cuenta ya está verificada"}

    nuevo_pin = generar_pin()
    user.pin_verificacion = nuevo_pin
    user.pin_expiracion = datetime.utcnow() + timedelta(minutes=PIN_VALIDEZ_MINUTOS)
    conexion.add(user)
    conexion.commit()

    await enviar_pin_verificacion(correo, nuevo_pin)

    return {"mensaje": "Se reenvió un nuevo PIN a tu correo"}


@router.post("/login", tags=["login"])
async def inicio(conexion: sesiondb, formulario: OAuth2PasswordRequestForm = Depends() ):
    buscar= select(usuariodb).where(usuariodb.username==formulario.username)
    user= conexion.exec(buscar).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos"
        )
    
    if not argon2.verify(formulario.password, user.contraseña):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos"
        )

    # --- Bloqueamos el login si el correo no fue verificado ---
    if not user.esta_verificado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes verificar tu correo antes de iniciar sesión"
        )

    tiempo=datetime.utcnow()+timedelta(minutes=t_estatico)
    acces_token={"sub":str(user.id),"exp":tiempo}
    return{
        "access_token":jwt.encode(acces_token,algo2,algorithm=algo), "token_type":"bearer"
    }
async def confirmacion(conexion: sesiondb, token: str=Depends(oauth2)):
    userid= jwt.decode(token,algo2,algorithms=[algo]).get("sub")
    iduser=int(userid)
    if iduser is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No estas verificado, Porfavor intentalo de nuevo"
        )
    
    mostrar=conexion.get(usuariodb,iduser)
    if mostrar is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales invalidas"
            )
    return mostrar

@router.get ("/autorizado", response_model=usuariodb, tags=["login"])
async def vizualizar(usuario:usuariodb=Depends(confirmacion)):
     return usuario


@router.post("/recuperar-contrasena", tags=["usuario"])
async def recuperar_contrasena(conexion: sesiondb, datos: solicitarrecuperacion):
    """
    Primera mitad de "Olvidé mi contraseña": genera un token de un solo uso
    y lo envía por correo con el enlace para restablecer la contraseña.
    """
    buscar = select(usuariodb).where(usuariodb.correo == datos.correo)
    user = conexion.exec(buscar).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    token = secrets.token_urlsafe(32)
    user.token_recuperacion = token
    user.token_recuperacion_expiracion = datetime.utcnow() + timedelta(
        minutes=TOKEN_RECUPERACION_VALIDEZ_MINUTOS
    )
    conexion.add(user)
    conexion.commit()

    await enviar_correo_recuperacion(user.correo, token)

    return {"mensaje": "Te enviamos un correo con el enlace para restablecer tu contraseña"}


@router.post("/restablecer-contrasena", tags=["usuario"])
async def restablecer_contrasena(conexion: sesiondb, datos: restablecercontrasena):
    """
    Segunda mitad de "Olvidé mi contraseña": valida el token que llegó por
    correo (existe, no expiró) y guarda la nueva contraseña, con las mismas
    reglas que se exigen al crear la cuenta.
    """
    buscar = select(usuariodb).where(usuariodb.token_recuperacion == datos.token)
    user = conexion.exec(buscar).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El enlace es inválido o ya fue usado"
        )

    if (
        user.token_recuperacion_expiracion is None
        or user.token_recuperacion_expiracion < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El enlace expiró, solicita uno nuevo"
        )

    user.contraseña = argon2.hash(datos.nueva_contraseña)
    user.token_recuperacion = None
    user.token_recuperacion_expiracion = None
    conexion.add(user)
    conexion.commit()

    return {"mensaje": "Contraseña actualizada correctamente"}