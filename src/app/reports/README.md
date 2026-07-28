# Informes

El módulo genera informes de diversidad e inclusión para RRHH a partir de los
mismos servicios y figuras que utiliza la página de Estadísticas.

- `models.py`: contratos, validación y saneado de la configuración.
- `builder.py`: métricas, textos parametrizados, gráficos y secciones.
- `recommendations.py`: reglas explícitas para recomendaciones de RRHH.
- `service.py`: consulta única, medición de tiempos y gestión de temporales.
- `pdf_exporter.py`: composición PDF profesional con ReportLab.
- `generator.py`: entrada de compatibilidad hacia el servicio completo.

La interfaz está disponible en `/informes` y `/reports`. La ruta heredada
`/report` redirige a `/informes`.
