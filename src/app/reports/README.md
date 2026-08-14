# Informe DataHub

El módulo público genera informes de diversidad e inclusión a partir de los
mismos servicios y figuras que utiliza la página de Estadísticas. Las cuentas
reciben plantillas adaptadas a su perfil y los visitantes reciben plantillas
generales.

- `models.py`: contratos, validación y saneado de la configuración.
- `builder.py`: métricas, textos parametrizados, gráficos y secciones.
- `recommendations.py`: reglas explícitas para recomendaciones de RRHH.
- `templates.py`: catálogo canónico de plantillas por perfil y plantillas públicas.
- `service.py`: consulta única, medición de tiempos y gestión de temporales.
- `pdf_exporter.py`: composición PDF profesional con ReportLab.

La interfaz está disponible en `/es/informe` y `/en/report` sin autenticación.
Las rutas históricas se redirigen a su ruta canónica localizada.
