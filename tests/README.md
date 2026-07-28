# Pruebas

La suite usa `pytest` y se centra en configuración e importadores. No requiere iniciar los servidores.

```powershell
$env:PYTHONPATH="$PWD\src"
.\.venv\Scripts\python.exe -m pytest -q
```

## Carpetas

- `unit/config/`: variables de entorno y configuración.
- `unit/import_to_db/`: transformación FRA/ILGA y operaciones Mongo simuladas.

Actualmente no hay pruebas de integración contra PostgreSQL/MongoDB ni pruebas de callbacks, autenticación o API.
