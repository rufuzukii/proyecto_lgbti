# Informe DataHub

El módulo público genera informes de diversidad e inclusión a partir de los
mismos servicios y figuras que utiliza la página de Estadísticas. Las cuentas
reciben plantillas adaptadas a su perfil y los visitantes reciben plantillas
generales.

- `models.py`: contratos, validación y saneado de la configuración.
- `builder.py`: métricas, interpretación determinista, gráficos explicados y secciones.
- `recommendations.py`: catálogo explícito de posibles actuaciones por perfil y resultado.
- `templates.py`: configuración canónica de perfiles, objetivos, plantillas y contenido.
- `service.py`: una consulta analítica compartida, medición de tiempos y gestión de temporales.
- `pdf_exporter.py`: composición PDF profesional con ReportLab.

La canalización es única y reproducible:

`ReportConfiguration → DataService → Metrics → InterpretationRules → ReportProfile → HTML/PDF`

La UI nunca acepta el perfil como fuente de permisos. El servidor lo resuelve
desde el usuario autenticado; un administrador puede previsualizar las
plantillas destinadas a otros perfiles sin modificar su rol real. Los textos
se generan mediante métricas, reglas y plantillas, sin servicios de IA externa.

La interfaz está disponible en `/es/informe` y `/en/report` sin autenticación.
Las rutas históricas se redirigen a su ruta canónica localizada.
