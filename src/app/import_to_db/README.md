# Importación y persistencia

Este paquete transforma CSV de fuentes externas en JSON normalizado, registra una revisión pendiente en PostgreSQL y, tras aprobación administrativa, inserta el contenido en MongoDB.

## Flujo efectivo

1. `dash/pages/upload.py` recibe uno o varios CSV.
2. `fra/` o `ilga/` construye el JSON.
3. Para FRA, el catálogo `categories`/`indicators` se sincroniza inmediatamente en PostgreSQL.
4. `register_pending_import()` guarda el JSON en `import_logs.file_json` con estado `pending`.
5. `/admin/imports` muestra el JSON pendiente para revisión.
6. El administrador rechaza el log o aprueba la inserción en MongoDB.
7. Tras aprobar, se invalida la caché analítica y se elimina el log.

La implementación elimina el registro pendiente en vez de conservar un historial `approved/imported/rejected`.

## Archivos Python

### `__init__.py`

Reexporta parsers FRA/ILGA. Las funciones de log usan imports diferidos para evitar ciclos.

### `utils.py`

- `parse_float()`: elimina `%`, espacios y convierte coma decimal.
- `normalize_header()`: minúsculas, sin acentos y en `snake_case`.
- `clean_cell()`: acceso seguro a columnas CSV.

### `import_log.py`

- `PendingImportLog`: modelo de un elemento revisable.
- `_resolve_postgres_dsn()`: exige `DATABASE_URL`.
- `insert_import_log()`: inserción genérica.
- `register_pending_import()` y `register_failed_import()`: altas especializadas.
- `list_pending_import_logs()` y `get_pending_import_log()`: lectura con etiqueta de usuario.
- `delete_import_log()`: elimina el elemento.
- `test_connection()`: prueba `SELECT 1`.

`load_dotenv()` carga valores locales sin sobrescribir variables ya presentes en el proceso.

### `error_handler.py`

Clasifica errores de conexión y esquema en mensajes seguros. Oculta contraseñas dentro de DSN PostgreSQL y evita mostrar excepciones técnicas completas al usuario.

## Subpaquetes

- `fra/`: CSV heterogéneo de EU LGBTIQ+ Survey III, detección de cabecera variable, separación de metadatos y pies de nota, catálogo PostgreSQL y `Indicator_fra`.
- `ilga/`: Rainbow Map anual e `Indicator_ilga`.

## Persistencia esperada

PostgreSQL: `users`, `import_logs`, `categories`, `indicators`.

MongoDB: `Indicator_fra`, `Indicator_ilga`.
