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

