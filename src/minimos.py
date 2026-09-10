from sqlmodel import Session
from db import engine
from modelos import categoriadb, unidadmedidadb

CATEGORIAS_PREDETERMINADAS = [
    {"nombre": "Granos", "icono": "wheat", "color": "amber"},
    {"nombre": "Lácteos", "icono": "milk", "color": "sky"},
    {"nombre": "Proteína", "icono": "drumstick", "color": "rose"},
    {"nombre": "Embutidos", "icono": "sandwich", "color": "orange"},
    {"nombre": "Frutas", "icono": "apple", "color": "pink"},
    {"nombre": "Verduras", "icono": "carrot", "color": "green"},
    {"nombre": "Grasas", "icono": "droplet", "color": "yellow"},
    {"nombre": "Aseo", "icono": "spray-can", "color": "cyan"},
    {"nombre": "Bebidas", "icono": "cup-soda", "color": "purple"},
    {"nombre": "Panadería", "icono": "croissant", "color": "stone"},
    {"nombre": "Congelados", "icono": "snowflake", "color": "blue"},
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
    obtiene sus propias filas, independientes de las de los demás.
    """
    with Session(engine) as sesion:
        for cat in CATEGORIAS_PREDETERMINADAS:
            sesion.add(
                categoriadb(
                    nombre=cat["nombre"],
                    stock_minimo=0,
                    icono=cat["icono"],
                    color=cat["color"],
                    usuario_id=usuario_id,
                )
            )

        for nombre, abreviatura in UNIDADES_PREDETERMINADAS:
            sesion.add(
                unidadmedidadb(nombre=nombre, abreviatura=abreviatura, usuario_id=usuario_id)
            )

        sesion.commit()