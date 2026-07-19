# proyecto_lgbti

Plataforma para el análisis y visualización de datos del colectivo LGBTIQ+ en Europa. El objetivo es integrar fuentes oficiales (datos socioeconómicos, legislativos y estadísticos), permitir comparativas entre países y ofrecer salidas reutilizables (gráficos, tablas e informes) para mejorar la toma de decisiones en ámbitos institucionales, educativos y de RRHH.

## Enfoque
- Integración de datos multifuente (CSV, APIs, informes) en bases relacional y no relacional.
- Análisis comparativo por país, categoría y periodo temporal.
- Visualizaciones interactivas y exportables.
- Informes de diversidad basados en evidencia.

## Seguridad básica (configuración)
- `API_KEY` o `API_KEYS`: clave(s) para acceder a la API (cabecera `X-API-Key`).
- `DASH_BASIC_AUTH`: credenciales para la interfaz Dash (`usuario:password,otro:password`).
- `IMPORT_BASE_DIR`: carpeta base permitida para importar CSV en la API.
- `AUTH_MAX_ATTEMPTS` y `AUTH_WINDOW_SECONDS`: límites de intentos para login/registro.

## Cache
- `CACHE_TYPE`: `SimpleCache` por defecto. En producción se recomienda `RedisCache`; si se configura Redis sin URL, la app cae a caché local.
- `CACHE_DEFAULT_TIMEOUT`: duración de consultas cacheadas, 300 segundos por defecto.
- `CACHE_REDIS_URL` o `REDIS_URL`: conexión Redis compartida entre procesos Gunicorn.
- `CACHE_VERSION`: versión incluida en el prefijo de claves para invalidar despliegues de forma controlada.
- `STATIC_CACHE_MAX_AGE`: caché del navegador para CSS, JavaScript e imágenes; 86400 segundos por defecto.

Las consultas de indicadores FRA y datos ILGA se invalidan automáticamente cuando un administrador aprueba una nueva importación.

## Puntos de entrada

- `run_dash.py`: inicia la interfaz Dash en el host y puerto configurados.
- `run_api.py`: inicia FastAPI con Uvicorn.
- `run_auth.py`: inicia el servicio Flask JSON de autenticación.
- `wsgi.py`: expone el servidor Flask interno de Dash para Gunicorn/Render.
- `render.yaml`: despliega `wsgi:server` en producción.
- `requirements.txt`: dependencias Python.
- `.env`: configuración local sensible; no debe compartirse.
- `dash-server.out.log` y `dash-server.err.log`: salidas generadas al ejecutar el servidor, no código fuente.

## Documentación interna

- `registro_funcionalidades/`: inventario funcional, arquitectura, estado y limitaciones.
- Cada carpeta de `src/` y `tests/` contiene un `README.md` con el detalle de sus archivos Python.
