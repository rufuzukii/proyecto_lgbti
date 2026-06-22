# Routers FastAPI

## Archivos Python

- `__init__.py`: marcador de paquete, sin lógica.
- `users.py`: `GET /users/` lista usuarios de PostgreSQL y serializa `UserRead`.
- `data_io.py`: `POST /data/import` procesa rutas bajo `IMPORT_BASE_DIR`; `GET /data/export` es un placeholder.
- `charts.py`: `GET /charts/export`, todavía devuelve `{"status": "pending"}`.
- `reports.py`: `GET /reports/`, todavía pendiente.
- `edu.py`: `GET /edu/units`, actualmente devuelve una lista vacía.

## Detalle de `data_io.py`

`MongoJsonImportRequest` admite una ruta a CSV ILGA, un directorio FRA, año y una bandera informativa `import_to_mongo`. `_safe_import_path()` impide rutas absolutas y escapes fuera del directorio permitido.

El endpoint transforma CSV con los importadores actuales (`fra` e `ilga`) y registra el JSON generado como pendiente en `import_logs`. No inserta directamente en MongoDB.
