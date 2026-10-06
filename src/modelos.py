from sqlmodel import SQLModel,Field
from pydantic import EmailStr, field_validator
import re
from datetime import datetime, date
from sqlalchemy import CheckConstraint


def validar_reglas_contraseña(contraseña: str) -> str:
    """
    Reglas de contraseña compartidas: se usan tanto al crear la cuenta
    como al restablecerla desde "Olvidé mi contraseña", para que en los
    dos casos se exija exactamente lo mismo.
    """
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


class usuario(SQLModel):
    name:str
    correo:EmailStr=Field(unique=True)
    username:str=Field(unique=True)
    contraseña:str
    @field_validator("contraseña")
    @classmethod
    def validar_contraseña(cls, contraseña: str):
        return validar_reglas_contraseña(contraseña)

    @field_validator("username")
    @classmethod
    def limpiar_username(cls, username: str):
        # Se conserva como lo escribió la persona, solo sin espacios sobrantes
        username = username.strip()
        if not username:
            raise ValueError("El nombre de usuario no puede estar vacío.")
        return username

    @field_validator("correo")
    @classmethod
    def correo_en_minusculas(cls, correo: str):
        # El correo siempre se guarda en minúsculas
        return correo.strip().lower()

class usuariocreate(usuario):
    ...

class usuariodb(usuario,table=True):
    id:int| None =Field(default=None, primary_key=True)

    esta_verificado: bool = Field(default=False)
    pin_verificacion: str | None = Field(default=None)
    pin_expiracion: datetime | None = Field(default=None)
    promedio_desperdicio: float = Field(default=10.0)
    meta_desperdicio: float = Field(default=2.0)

    # --- Recuperación de contraseña ("Olvidé mi contraseña") ---
    token_recuperacion: str | None = Field(default=None)
    token_recuperacion_expiracion: datetime | None = Field(default=None)

    # --- Avatar elegido por el usuario (id del catálogo del frontend: a1..a12) ---
    avatar: str | None = Field(default=None)

class usuariopublico(SQLModel):
    """Datos del usuario que se pueden devolver por la API (sin contraseña, PIN ni tokens)."""
    id: int
    name: str
    correo: str
    username: str
    avatar: str | None = None
    esta_verificado: bool = False
    promedio_desperdicio: float = 10.0
    meta_desperdicio: float = 2.0


class actualizaravatar(SQLModel):
    avatar: str | None = None

    @field_validator("avatar")
    @classmethod
    def validar_avatar(cls, avatar):
        if avatar is not None and not re.fullmatch(r"a([1-9]|1[0-2])", avatar):
            raise ValueError("Avatar no válido.")
        return avatar


class verificarpin(SQLModel):
    correo: EmailStr
    pin: str

    @field_validator("correo")
    @classmethod
    def correo_en_minusculas(cls, correo: str):
        return correo.strip().lower()


# --- Schemas para el flujo de "Olvidé mi contraseña" ---
class solicitarrecuperacion(SQLModel):
    correo: EmailStr

    @field_validator("correo")
    @classmethod
    def correo_en_minusculas(cls, correo: str):
        return correo.strip().lower()


class restablecercontrasena(SQLModel):
    token: str
    nueva_contraseña: str

    @field_validator("nueva_contraseña")
    @classmethod
    def validar_nueva_contraseña(cls, contraseña: str):
        return validar_reglas_contraseña(contraseña)

class categoria(SQLModel):
    nombre: str
    stock_minimo: float = Field(default=0)
    icono: str = Field(default="package")
    color: str = Field(default="slate")

class categoriacreate(categoria):
    ...

class categoriaupdate(SQLModel):
    nombre: str | None = None
    stock_minimo: float | None = None
    icono: str | None = None
    color: str | None = None

class categoriadb(categoria, table=True):
    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuariodb.id")
    # Eliminación lógica: la fila se conserva para no romper el historial
    eliminada: bool = Field(default=False)


class unidadmedida(SQLModel):
    nombre: str
    abreviatura: str


class unidadmedidacreate(unidadmedida):
    ...


class unidadmedidaupdate(SQLModel):
    nombre: str | None = None
    abreviatura: str | None = None


class unidadmedidadb(unidadmedida, table=True):
    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuariodb.id")
    # Eliminación lógica: la fila se conserva para no romper el historial
    eliminada: bool = Field(default=False)


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
    usuario_id: int = Field(foreign_key="usuariodb.id")



class compra(SQLModel):
    fecha_compra: date = Field(default_factory=date.today)


class compracreate(compra):
    ...


class compradb(compra, table=True):
    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuariodb.id")


class lotebase(SQLModel):
    producto_id: int = Field(foreign_key="productodb.id")
    compra_id: int = Field(foreign_key="compradb.id")
    fecha_vencimiento: date
    cantidad_inicial: float


class lotecreate(lotebase):
    ...


class loteupdate(SQLModel):
    cantidad_actual: float | None = None
    fecha_vencimiento: date | None = None


class lotedb(lotebase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuariodb.id")
    cantidad_actual: float
    estado: str = Field(default="vigente")

class transaccion(SQLModel):
    lote_id: int = Field(foreign_key="lotedb.id")
    tipo: str = Field(default="consumo")
    cantidad: float
    fecha: datetime = Field(default_factory=datetime.utcnow)

class transaccioncreate(SQLModel):
    lote_id: int
    cantidad: float
    tipo: str = "consumo"

class transacciondb(transaccion, table=True):
    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuariodb.id")

class alerta(SQLModel):
    tipo: str
    """ 'proximo_a_vencer' | 'vencido' | 'stock_minimo' """
    producto_id: int | None = Field(default=None, foreign_key="productodb.id")
    lote_id: int | None = Field(default=None, foreign_key="lotedb.id")
    fecha_generada: datetime = Field(default_factory=datetime.utcnow)
    atendida: bool = Field(default=False)
    oculta: bool = Field(default=False)
    """ True cuando el usuario eliminó el registro del historial de seguimiento """


class alertadb(alerta, table=True):
    __table_args__ = (
        CheckConstraint(
            "producto_id IS NOT NULL OR lote_id IS NOT NULL",
            name="chk_alerta_referencia",
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuariodb.id")