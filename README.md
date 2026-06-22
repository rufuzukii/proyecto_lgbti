# proyecto_lgbti

Plataforma para el analisis y visualizacion de datos del colectivo LGBTIQ+ en Europa. El objetivo es integrar fuentes oficiales (datos socioeconomicos, legislativos y estadisticos), permitir comparativas entre paises y ofrecer salidas reutilizables (graficos, tablas e informes) para mejorar la toma de decisiones en ambitos institucionales, educativos y de RRHH.

## Enfoque
- Integracion de datos multifuente (CSV, APIs, informes) en bases relacional y no relacional.
- Analisis comparativo por pais, categoria y periodo temporal.
- Visualizaciones interactivas y exportables.
- Informes de diversidad basados en evidencia.

## Seguridad basica (configuracion)
- `API_KEY` o `API_KEYS`: clave(s) para acceder a la API (cabecera `X-API-Key`).
- `DASH_BASIC_AUTH`: credenciales para la interfaz Dash (`usuario:password,otro:password`).
- `IMPORT_BASE_DIR`: carpeta base permitida para importar CSV en la API.
- `AUTH_MAX_ATTEMPTS` y `AUTH_WINDOW_SECONDS`: limites de intentos para login/registro.

## Cache
- `CACHE_TYPE`: `SimpleCache` por defecto. En produccion puede configurarse como `RedisCache`.
- `CACHE_DEFAULT_TIMEOUT`: duracion de consultas cacheadas, 300 segundos por defecto.
- `CACHE_REDIS_URL` o `REDIS_URL`: conexion Redis compartida entre procesos Gunicorn.
- `STATIC_CACHE_MAX_AGE`: cache del navegador para CSS, JavaScript e imagenes; 86400 segundos por defecto.

Las consultas de indicadores FRA y datos ILGA se invalidan automaticamente cuando un administrador aprueba una nueva importacion.

## Puntos de entrada

- `run_dash.py`: inicia la interfaz Dash en el host y puerto configurados.
- `run_api.py`: inicia FastAPI con Uvicorn.
- `run_auth.py`: inicia el servicio Flask JSON de autenticacion.
- `wsgi.py`: expone el servidor Flask interno de Dash para Gunicorn/Render.
- `render.yaml`: despliega `wsgi:server` en produccion.
- `requirements.txt`: dependencias Python.
- `.env`: configuracion local sensible; no debe compartirse.
- `dash-server.out.log` y `dash-server.err.log`: salidas generadas al ejecutar el servidor, no codigo fuente.

## Documentacion interna

- `registro_funcionalidades/`: inventario funcional, arquitectura, estado y limitaciones.
- Cada carpeta de `src/` y `tests/` contiene un `README.md` con el detalle de sus archivos Python.
