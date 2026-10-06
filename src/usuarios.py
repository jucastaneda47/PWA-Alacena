from modelos import (
    usuariocreate,
    usuariodb,
    usuariopublico,
    verificarpin,
    solicitarrecuperacion,
    restablecercontrasena,
    actualizaravatar,
)
from db import sesiondb
from minimos import sembrar_datos_para_usuario
from fastapi import APIRouter,HTTPException, status, Depends
from passlib.hash import argon2
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlmodel import select, func
from datetime import datetime, timedelta
from jose import jwt, JWTError
import secrets
import os
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
# Clave para firmar los tokens: viene del archivo .env (variable JWT_SECRET), nunca va escrita en el código.
algo2 = os.getenv("JWT_SECRET")
if not algo2:
    raise RuntimeError(
        "Falta JWT_SECRET en el archivo .env. Genera una con: "
        "python -c \"import secrets; print(secrets.token_hex(32))\""
    )
oauth2= OAuth2PasswordBearer(tokenUrl="login")

@router.post("/usuario", response_model=usuariopublico, tags=["usuario"])
async def crear(conexion: sesiondb, usuario: usuariocreate):
    # El nombre de usuario no distingue mayúsculas (M19MOCHO == m19mocho)
    ya_usuario = conexion.exec(
        select(usuariodb).where(func.lower(usuariodb.username) == usuario.username.lower())
    ).first()
    if ya_usuario is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ese nombre de usuario ya está en uso",
        )
    ya_correo = conexion.exec(
        select(usuariodb).where(func.lower(usuariodb.correo) == usuario.correo.lower())
    ).first()
    if ya_correo is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ese correo ya está registrado",
        )

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

    # --- Categorías y unidades de medida predeterminadas (copia propia del usuario) ---
    sembrar_datos_para_usuario(usadb.id)

    # --- Enviamos el correo con el PIN ---
    await enviar_pin_verificacion(usadb.correo, pin)

    return usadb


@router.post("/verificar-pin", tags=["usuario"])
async def verificar_pin(conexion: sesiondb, datos: verificarpin):
    buscar = select(usuariodb).where(func.lower(usuariodb.correo) == datos.correo.lower())
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
    correo = correo.strip().lower()
    buscar = select(usuariodb).where(func.lower(usuariodb.correo) == correo)
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
    # El usuario se compara sin distinguir mayúsculas
    buscar= select(usuariodb).where(
        func.lower(usuariodb.username)==formulario.username.strip().lower()
    )
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
    # Token vencido o inválido -> 401 (el frontend cierra la sesión), no error 500
    try:
        userid= jwt.decode(token,algo2,algorithms=[algo]).get("sub")
        iduser=int(userid)
    except (JWTError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión expirada, inicia sesión de nuevo",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    mostrar=conexion.get(usuariodb,iduser)
    if mostrar is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales invalidas"
            )
    return mostrar

@router.post("/renovar-sesion", tags=["login"])
async def renovar_sesion(usuario: usuariodb = Depends(confirmacion)):
    """
    Sesión por inactividad: mientras la persona siga activa, el frontend pide
    un token nuevo con otros 10 minutos de vida. Si pasa 10 minutos sin
    actividad nadie renueva el token y la sesión caduca.
    """
    tiempo = datetime.utcnow() + timedelta(minutes=t_estatico)
    token = jwt.encode({"sub": str(usuario.id), "exp": tiempo}, algo2, algorithm=algo)
    return {"access_token": token, "token_type": "bearer"}


@router.get ("/autorizado", response_model=usuariopublico, tags=["login"])
async def vizualizar(usuario:usuariodb=Depends(confirmacion)):
     return usuario


@router.put("/avatar", tags=["usuario"])
async def guardar_avatar(
    datos: actualizaravatar,
    conexion: sesiondb,
    usuario: usuariodb = Depends(confirmacion),
):
    """Guarda (o quita, si viene null) el avatar elegido por el usuario."""
    usuario.avatar = datos.avatar
    conexion.add(usuario)
    conexion.commit()
    conexion.refresh(usuario)
    return {"avatar": usuario.avatar}


@router.post("/recuperar-contrasena", tags=["usuario"])
async def recuperar_contrasena(conexion: sesiondb, datos: solicitarrecuperacion):
    """
    Primera mitad de "Olvidé mi contraseña": genera un token de un solo uso
    y lo envía por correo con el enlace para restablecer la contraseña.
    """
    buscar = select(usuariodb).where(func.lower(usuariodb.correo) == datos.correo.lower())
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