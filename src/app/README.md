# Paquete principal `app`

`app` reúne la aplicación web y la lógica de dominio de RainbowLens DataHub.

## Entradas

- `main.py`: ejecución local de Dash.
- `dash_app.py`: composición Dash/Flask, rutas, sesiones y callbacks.
- `api/`: FastAPI separado para integraciones locales.
- `health.py`: contrato de salud compartido por Dash y FastAPI.
- `config.py` y `cache.py`: configuración y caché TTL local acotada.

## Subpaquetes activos

- `analytics/`: consultas, normalización, agregaciones, figuras y exportaciones.
- `auth/` y `users/`: autenticación, permisos, seguridad de cuenta y PostgreSQL.
- `dash/`: layouts, componentes, páginas, callbacks y assets.
- `edu/`: glosario, lecciones, juegos, recursos y progreso.
- `import_to_db/`: importadores FRA/ILGA/FELGTBI+, revisión y persistencia.
- `mail/`: entrega centralizada de correo.
- `reports/`: construcción y exportación PDF real.
- `trends/`: series históricas, validación y análisis.
- `api/`: endpoints FastAPI implementados y protegidos.

El antiguo paquete `charts/` se eliminó: contenía únicamente un exportador que devolvía
`pending`. Las exportaciones operativas viven en `analytics.statistics_exports` y en los
callbacks/recursos del frontend.

## Flujo principal

1. `create_dash_app()` crea Dash sobre Flask.
2. Flask-Login recupera usuarios mediante `users/service.py`.
3. Las páginas consultan servicios de `analytics/`, `edu/`, `reports/` y `trends/`.
4. Los archivos aceptados se normalizan y quedan pendientes en PostgreSQL.
5. Un administrador aprueba la persistencia final en MongoDB.

FastAPI (`app.api:app`) y la factoría de autenticación JSON son servicios separados para
desarrollo/integración. Render arranca únicamente `wsgi:server`.
