from sqlmodel import Session
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


def sembrar_datos_para_usuario(usuario_id: int):
    """
    Crea la copia PERSONAL de categorías y unidades de medida
    predeterminadas para un usuario recién registrado. Cada usuario
    obtiene sus propias filas en la base de datos, totalmente
    independientes de las de los demás usuarios.
    """
    with Session(engine) as sesion:
        for nombre in CATEGORIAS_PREDETERMINADAS:
            sesion.add(categoriadb(nombre=nombre, stock_minimo=0, usuario_id=usuario_id))

        for nombre, abreviatura in UNIDADES_PREDETERMINADAS:
            sesion.add(
                unidadmedidadb(nombre=nombre, abreviatura=abreviatura, usuario_id=usuario_id)
            )

        sesion.commit()