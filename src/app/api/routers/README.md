# Routers FastAPI

- `users.py`: `GET /users/`, lectura administrativa desde PostgreSQL.
- `reports.py`: `POST /reports`, validación y generación del PDF real.
- `edu.py`: `GET /edu/units`, índice ligero de las unidades didácticas reales.

`GET /charts/export`, `GET /data/export` y el antiguo `GET /reports/` informativo fueron
eliminados por carecer de implementación o consumidores. La salud se registra en
`app.api.create_api_app()` y reutiliza `app.health.build_health_report()`.

Todos los routers se protegen al registrarlos: usuarios con clave administradora e
informes/educación con clave general.
