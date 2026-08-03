# Código fuente

Esta carpeta contiene el paquete Python de RainbowLens Datahub. Para ejecutar sus módulos, `src` debe estar en `PYTHONPATH`; los scripts de la raíz (`run_dash.py`, `run_api.py`, `run_auth.py` y `wsgi.py`) lo añaden automáticamente.

## Contenido

- `app/`: aplicación completa, dividida en interfaz Dash, API, autenticación, usuarios, analítica e importación de datos.

No se guardan aquí datos subidos ni dependencias instaladas. La persistencia se realiza en PostgreSQL y MongoDB.
