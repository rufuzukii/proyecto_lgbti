# API HTTP

Esta carpeta contiene la infraestructura FastAPI. Su aplicación es `app.api:app`, definida en
`src/app/api/__init__.py`.

## Archivos Python

- `__init__.py`: crea FastAPI, registra routers con clave general o administradora y deja
  público `GET /health`, que reutiliza el diagnóstico real de la aplicación.
- `security.py`: lee `API_KEYS` o `API_KEY`, recibe `X-API-Key` y compara claves con `hmac.compare_digest`. Responde `503` si no existe configuración y `401` si la clave no es válida.
- `routers/`: endpoints agrupados por dominio.

## Ejecución

```powershell
uvicorn app.api:app
```

FastAPI expone además documentación OpenAPI en `/docs` y `/redoc` cuando el servidor está activo.
En producción estas rutas de documentación se deshabilitan.
