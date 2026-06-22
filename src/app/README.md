# Paquete principal `app`

`app` reúne todos los componentes ejecutables y la lógica de dominio de RainbowLens.

## Archivos de primer nivel

- `__init__.py`: marca la carpeta como paquete Python. No ejecuta inicialización.
- `config.py`: carga `.env`, interpreta variables y construye la configuración de aplicación, PostgreSQL y MongoDB.
- `cache.py`: configura Flask-Caching y las cabeceras de caché para assets estáticos.
- `main.py`: punto de entrada Python de Dash; obtiene host, puerto y modo debug desde `config.py`.
- `dash_app.py`: composición principal de la aplicación web Dash/Flask. Registra rutas, sesiones, callbacks y operaciones administrativas.
- `api.py`: aplicación FastAPI protegida con clave API. Es el objetivo usado por `run_api.py`.

## Subpaquetes

- `analytics/`: consultas de indicadores y construcción de visualizaciones.
- `api/`: seguridad y routers HTTP.
- `auth/`: autenticación Flask independiente, CSRF y matriz de permisos.
- `charts/`: futura exportación de gráficos.
- `dash/`: layouts, páginas y assets del frontend.
- `edu/`: futuro contenido didáctico.
- `import_to_db/`: parseo FRA/ILGA, cola de revisión y persistencia.
- `reports/`: futura generación de informes.
- `users/`: modelos y acceso a usuarios en PostgreSQL.

## Flujo principal

1. `create_dash_app()` crea Dash sobre un servidor Flask.
2. Flask-Login recupera usuarios mediante `users/service.py`.
3. Los layouts consultan `analytics/`, que lee PostgreSQL y MongoDB.
4. Los CSV subidos se transforman con `import_to_db/`.
5. El JSON queda pendiente en PostgreSQL.
6. Un administrador lo aprueba y se inserta en MongoDB.

## Estado

La interfaz, autenticación, usuarios, analítica FRA/ILGA e importación revisable están implementadas. `charts`, `reports`, `edu` y varias páginas de navegación siguen siendo esqueletos.
