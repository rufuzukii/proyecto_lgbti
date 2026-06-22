# API HTTP

Esta carpeta contiene la infraestructura FastAPI. La aplicación desplegada por `run_api.py` es `app.api:app`, definida en `src/app/api/__init__.py`.

## Archivos Python

- `__init__.py`: crea la instancia FastAPI con `create_api_app()`, registra routers y aplica `Depends(require_api_key)` a todos los routers. `GET /health` queda público.
- `security.py`: lee `API_KEYS` o `API_KEY`, recibe `X-API-Key` y compara claves con `hmac.compare_digest`. Responde `503` si no existe configuración y `401` si la clave no es válida.
- `routers/`: endpoints agrupados por dominio.

## Ejecución

```powershell
python run_api.py
```

FastAPI expone además documentación OpenAPI en `/docs` y `/redoc` cuando el servidor está activo.
