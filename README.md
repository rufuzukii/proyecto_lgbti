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
- `REDIS_URL`: activa automáticamente la caché Redis compartida entre workers Gunicorn.
- `CACHE_DEFAULT_TIMEOUT`: duración de consultas cacheadas, 300 segundos por defecto.
- `CACHE_VERSION`: versión incluida en el prefijo de claves para invalidar despliegues de forma controlada.
- `STATIC_CACHE_MAX_AGE`: caché del navegador para CSS, JavaScript e imágenes; 86400 segundos por defecto.

En desarrollo, si no existe `REDIS_URL`, se usa `SimpleCache`. En producción sin URL se
usa `NullCache`, evitando una caché en memoria incoherente entre workers. Una caída temporal
de Redis se trata como un fallo de caché y no interrumpe las peticiones. Las consultas de
indicadores FRA y datos ILGA se invalidan automáticamente cuando un administrador aprueba una
nueva importación.

## Despliegue y salud

`render.yaml` crea el servicio web y un Render Key Value privado, conecta su
`connectionString` como `REDIS_URL` y configura `GET /health` como health check. El endpoint
comprueba la aplicación, PostgreSQL, MongoDB, Redis y la configuración mínima sin devolver URI,
credenciales ni trazas. Para ejecutar las pruebas de humo contra un despliegue real, define
`RENDER_EXTERNAL_URL` antes de lanzar `pytest tests/smoke`.

## Seguridad de cuentas y correo

Los registros nuevos quedan pendientes de verificación. Los tokens de verificación y
recuperación son de un solo uso, se almacenan mediante hash y caducan. El envío se centraliza
con `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` y
`SMTP_TIMEOUT_SECONDS`. Los enlaces usan `PUBLIC_BASE_URL` o, en Render,
`RENDER_EXTERNAL_URL`; no se guardan credenciales ni URLs privadas en el repositorio.

Los límites se configuran con `EMAIL_TOKEN_MAX_ATTEMPTS`, `EMAIL_TOKEN_WINDOW_SECONDS`,
`PASSWORD_RESET_MAX_ATTEMPTS` y `PASSWORD_RESET_WINDOW_SECONDS`. Las operaciones sensibles
(informes, solicitudes de rol, contenido docente y subidas) requieren correo verificado.

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
