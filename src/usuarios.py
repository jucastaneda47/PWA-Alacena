from modelos import usuariocreate, usuariodb, verificarpin
from db import sesiondb
from fastapi import APIRouter,HTTPException, status, Depends
from passlib.hash import argon2
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlmodel import select
from datetime import datetime, timedelta
from jose import jwt
from correo import generar_pin, enviar_pin_verificacion, PIN_VALIDEZ_MINUTOS
import os
from pathlib import Path
from dotenv import load_dotenv
from minimos import sembrar_datos_para_usuario

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

algo2=str(os.getenv("algo2"))
router = APIRouter()
t_estatico = 30
algo= "HS256"
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

    # --- Carga la copia personal de categorías y unidades de medida ---
    sembrar_datos_para_usuario(usadb.id)

    # --- Enviamos el correo con el PIN ---
    await enviar_pin_verificacion(usadb.correo, pin)

    return usadb

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
    if not user.esta_verificado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes verificar tu correo antes de iniciar sesión"
        )

    tiempo=datetime.utcnow()+timedelta(seconds=t_estatico)
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