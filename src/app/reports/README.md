# Informe DataHub

El módulo público genera informes de inclusión LGBTIQ+ orientados a RRHH y
diversidad e inclusión a partir de los mismos servicios y figuras que utiliza
Estadísticas. No existen plantillas diferentes por perfil de cuenta.

- `models.py`: contrato, validación y saneado de la configuración.
- `hr_reporting.py`: objetivos, secciones y gráficos permitidos para el enfoque RRHH.
- `builder.py`: métricas, interpretación determinista, gráficos explicados y secciones.
- `recommendations.py`: catálogo explícito de posibles actuaciones de RRHH según resultado.
- `service.py`: una consulta analítica compartida, medición de tiempos y gestión de temporales.
- `pdf_exporter.py`: composición PDF profesional con ReportLab.

La canalización es única y reproducible:

`ReportConfiguration → DataService → Metrics → InterpretationRules → HR configuration → HTML/PDF`

Los resultados FRA se describen como contexto social externo: no miden la
plantilla de una empresa ni constituyen una auditoría interna. Los textos se
generan mediante métricas, reglas y frases deterministas, sin servicios de IA
externa. Las secciones de conclusión se omiten cuando no hay base suficiente.

La interfaz está disponible en `/es/informe` y `/en/report` sin autenticación.
Las rutas históricas se redirigen a su ruta canónica localizada.
