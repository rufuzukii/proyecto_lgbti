# Código fuente

Esta carpeta contiene el paquete Python de RainbowLens DataHub. La instalación editable declarada
en `pyproject.toml` expone el paquete y el comando `rainbowlens-dash`; Render utiliza `wsgi.py`.

## Contenido

- `app/`: aplicación completa, dividida en interfaz Dash, API, autenticación, usuarios, analítica e importación de datos.

No se guardan aquí datos subidos ni dependencias instaladas. La persistencia se realiza en PostgreSQL y MongoDB.
