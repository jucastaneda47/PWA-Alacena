from sqlmodel import Session, select
from db import engine
from modelos import categoriadb, unidadmedidadb

CATEGORIAS_PREDETERMINADAS = [
    "Granos",
    "Lácteos",
    "Proteína",
    "Embutidos",
    "Frutas",
    "Verduras",
    "Grasas",
    "Aseo",
    "Bebidas",
    "Panadería",
    "Congelados",
]

# (nombre, abreviatura)
UNIDADES_PREDETERMINADAS = [
    ("Kilogramo", "kg"),
    ("Gramo", "g"),
    ("Litro", "l"),
    ("Mililitro", "ml"),
]


def sembrar_datos_iniciales():
    """
    Inserta las categorías y unidades de medida predeterminadas si todavía
    no existen. Es seguro llamarla en cada arranque del servidor: no
    duplica registros ya creados.
    """
    with Session(engine) as sesion:
        for nombre in CATEGORIAS_PREDETERMINADAS:
            existe = sesion.exec(
                select(categoriadb).where(categoriadb.nombre == nombre)
            ).first()
            if not existe:
                sesion.add(categoriadb(nombre=nombre, stock_minimo=0))

        for nombre, abreviatura in UNIDADES_PREDETERMINADAS:
            existe = sesion.exec(
                select(unidadmedidadb).where(unidadmedidadb.nombre == nombre)
            ).first()
            if not existe:
                sesion.add(unidadmedidadb(nombre=nombre, abreviatura=abreviatura))

        sesion.commit()