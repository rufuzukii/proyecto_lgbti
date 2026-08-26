# proyecto_lgbti

Plataforma para el análisis y visualización de datos del colectivo LGBTIQ+ en Europa. El objetivo es integrar fuentes oficiales (datos socioeconómicos, legislativos y estadísticos), permitir comparativas entre países y ofrecer salidas reutilizables (gráficos, tablas e informes) para mejorar la toma de decisiones en ámbitos institucionales, educativos y de RRHH.

## Enfoque
- Integración de datos multifuente (CSV, APIs, informes) en bases relacional y no relacional.
- Análisis comparativo por país, categoría y periodo temporal.
- Visualizaciones interactivas y exportables.
- Informes de diversidad basados en evidencia.

## Seguridad básica (configuración)
- `API_KEY` o `API_KEYS`: clave(s) para acceder a la API (cabecera `X-API-Key`).
- `AUTH_MAX_ATTEMPTS` y `AUTH_WINDOW_SECONDS`: límites de intentos para login/registro.

## Cache
- `CACHE_DEFAULT_TIMEOUT`: duración de consultas cacheadas, 300 segundos por defecto.
- `CACHE_VERSION`: versión incluida en el prefijo de claves para invalidar despliegues de forma controlada.
- `LOCAL_CACHE_MAX_ENTRIES`: máximo de entradas por worker, 512 por defecto.
- `LOCAL_CACHE_MAX_VALUE_BYTES`: tamaño máximo de un resultado cacheado, 4 MiB por defecto.
- `LOCAL_CACHE_MAX_TOTAL_BYTES`: presupuesto total por worker, 64 MiB por defecto.
- `HTTP_GZIP_MIN_BYTES`: tamaño mínimo para comprimir respuestas JSON/CSS/JS, 1024 bytes por defecto.
- `STATIC_CACHE_MAX_AGE`: caché del navegador para CSS, JavaScript e imágenes; 86400 segundos por defecto.

La caché es local, acotada, con TTL y aislada por worker. No es una fuente de verdad ni necesita
servicios externos: tras un reinicio se reconstruye bajo demanda desde PostgreSQL, MongoDB o
Supabase. Las consultas de indicadores FRA y datos ILGA se invalidan automáticamente cuando un
administrador aprueba una nueva importación.

## Despliegue y salud

`render.yaml` crea un único servicio web y configura `GET /health` como health check. El endpoint
es una comprobación ligera de vida de la aplicación y no abre conexiones externas en cada sondeo.
Para ejecutar las pruebas de humo contra un despliegue real, define
`RENDER_EXTERNAL_URL` antes de lanzar `pytest tests/smoke`.

## Seguridad de cuentas y correo

Los registros nuevos quedan pendientes de verificación. Los tokens de verificación y
recuperación son de un solo uso, se almacenan mediante hash y caducan. El envío se centraliza
en un servicio que solo informa de éxito cuando el proveedor acepta el mensaje. En local se usa
`EMAIL_TRANSPORT=smtp`; requiere `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_SSL`, `SMTP_STARTTLS`,
`SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` y `SMTP_TIMEOUT_SECONDS`. Los servicios
Render Free no permiten salida por los puertos SMTP habituales, por lo que `render.yaml` selecciona
`EMAIL_TRANSPORT=gmail_api` y requiere `GMAIL_API_CLIENT_ID`, `GMAIL_API_CLIENT_SECRET`,
`GMAIL_API_REFRESH_TOKEN` y `GMAIL_API_TIMEOUT_SECONDS`. Este transporte usa HTTPS y el permiso
OAuth mínimo de envío de Gmail; no necesita Redis ni una librería adicional.

Los enlaces usan `PUBLIC_BASE_URL`, `RENDER_EXTERNAL_URL` o el hostname externo proporcionado por
Render, en ese orden. En producción se exige HTTPS. No se guardan credenciales ni URLs privadas
en el repositorio. Para dominios personalizados se puede definir `TRUSTED_HOSTS` como una lista
separada por comas. Un error de correo no impide arrancar la aplicación: el intento falla de forma
controlada y deja la cuenta pendiente y con opción de reenvío.

Los límites se configuran con `EMAIL_TOKEN_MAX_ATTEMPTS`, `EMAIL_TOKEN_WINDOW_SECONDS`,
`PASSWORD_RESET_MAX_ATTEMPTS` y `PASSWORD_RESET_WINDOW_SECONDS`. Las operaciones sensibles
(informes, solicitudes de rol, contenido docente y subidas) requieren correo verificado.

## Puntos de entrada

- `rainbowlens-dash`: inicia la interfaz local mediante el entrypoint declarado en `pyproject.toml`.
- `uvicorn app.api:app`: inicia la API FastAPI cuando se necesita como servicio independiente.
- `wsgi.py`: expone el servidor Flask interno de Dash para Gunicorn/Render.
- `render.yaml`: despliega `wsgi:server` en producción.
- `requirements.txt`: dependencias Python.
- `.env`: configuración local sensible; no debe compartirse.
