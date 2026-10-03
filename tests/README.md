# Pruebas automáticas de FreshLog (backend)

Se ejecutan sobre una base de datos en memoria: **no tocan `db.sqlite3`** ni envían correos reales.

## Cómo ejecutarlas (desde la raíz del proyecto, donde está `pytest.ini`)

    uv add --dev pytest pytest-cov        # una sola vez (o: pip install pytest pytest-cov)
    uv run pytest                          # todas
    uv run pytest tests/unitarias          # solo unitarias
    uv run pytest tests/integracion        # solo de integración
    uv run pytest tests/funcionales        # solo funcionales
    uv run pytest --cov=src --cov-report=term-missing    # con cobertura

## Organización

| Carpeta | Qué prueba | Prefijo de caso |
|---|---|---|
| `unitarias/` | Funciones sueltas: clasificación por días, reglas de contraseña, correo, avatar, resta de meses, stock, datos predeterminados | UT-xx |
| `integracion/` | Endpoints de la API trabajando con la base de datos: usuarios, catálogo, inventario/consumo, alertas, estadísticas | IT-xx |
| `funcionales/` | Recorridos completos de una persona usando la app (registro → compra → consumo → alertas...) | CF-xx |

`conftest.py` prepara la base de datos temporal, la bandeja de correos falsos y los usuarios de prueba (`ana`, `beto`).
