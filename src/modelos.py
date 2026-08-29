from sqlmodel import SQLModel,Field
from pydantic import EmailStr, field_validator
import re
from datetime import datetime, timedelta


class usuario(SQLModel):
    name:str
    correo:EmailStr=Field(unique=True)
    username:str=Field(unique=True)
    contraseña:str
    @field_validator("contraseña")
    @classmethod
    def validar_contraseña(cls, contraseña: str):

        if len(contraseña) < 8:
            raise ValueError("La contraseña debe tener mínimo 8 caracteres.")

        if not re.search(r"[A-Z]", contraseña):
            raise ValueError("Debe contener al menos una letra mayúscula.")

        if not re.search(r"[a-z]", contraseña):
            raise ValueError("Debe contener al menos una letra minúscula.")

        if not re.search(r"\d", contraseña):
            raise ValueError("Debe contener al menos un número.")

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=/\\[\]]", contraseña):
            raise ValueError("Debe contener al menos un carácter especial.")

        return contraseña

class usuariocreate(usuario):
    ...

class usuariodb(usuario,table=True):
    id:int| None =Field(default=None, primary_key=True)

    esta_verificado: bool = Field(default=False)
    pin_verificacion: str | None = Field(default=None)
    pin_expiracion: datetime | None = Field(default=None)

class verificarpin(SQLModel):
    correo: EmailStr
    pin: str


class categoria(SQLModel):
    nombre: str = Field(unique=True)
    stock_minimo: float = Field(default=0)


class categoriacreate(categoria):
    ...


class categoriaupdate(SQLModel):
    nombre: str | None = None
    stock_minimo: float | None = None


class categoriadb(categoria, table=True):
    id: int | None = Field(default=None, primary_key=True)


class unidadmedida(SQLModel):
    nombre: str = Field(unique=True)
    abreviatura: str = Field(unique=True)


class unidadmedidacreate(unidadmedida):
    ...


class unidadmedidaupdate(SQLModel):
    nombre: str | None = None
    abreviatura: str | None = None


class unidadmedidadb(unidadmedida, table=True):
    id: int | None = Field(default=None, primary_key=True)


class producto(SQLModel):
    nombre: str
    categoria_id: int = Field(foreign_key="categoriadb.id")
    unidad_de_medida_id: int = Field(foreign_key="unidadmedidadb.id")
    stock_minimo: float | None = Field(default=None)
    """Si es None, el producto hereda el stock_minimo de su categoría."""


class productocreate(producto):
    ...


class productoupdate(SQLModel):
    nombre: str | None = None
    categoria_id: int | None = None
    unidad_de_medida_id: int | None = None
    stock_minimo: float | None = None


class productodb(producto, table=True):
    id: int | None = Field(default=None, primary_key=True)


