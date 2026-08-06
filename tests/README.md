# Pruebas

La suite usa `pytest` y cubre pruebas unitarias, integraciones con dobles persistentes o
servicios locales, flujos E2E HTTP y smoke tests opcionales contra Render.

```powershell
$env:PYTHONPATH="$PWD\src"
.\.venv\Scripts\python.exe -m pytest -q
```

## Carpetas

- `unit/`: contratos aislados, normalización, permisos, callbacks y componentes.
- `integration/`: interacción entre importadores, persistencia, analítica, informes y PostgreSQL.
- `e2e/`: flujos HTTP completos de cuenta, permisos, administración y errores.
- `smoke/`: rutas locales y comprobación opcional de `RENDER_EXTERNAL_URL`.

La integración PostgreSQL es de solo lectura y se omite únicamente cuando no hay una base
configurada accesible. Las comprobaciones externas contra Render se activan mediante
`RENDER_EXTERNAL_URL`; no hay URLs ni credenciales codificadas en el repositorio.
