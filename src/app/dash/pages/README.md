# Páginas Dash

## Módulos activos

- `statistics.py`: panel FRA/ILGA, controles, Top paginado, tablas, comparadores y exportación.
- `upload.py`: subida administrativa CSV/JSON/PDF, validación y alta pendiente de revisión.
- `reports.py`: configuración, vista previa y generación del Informe DataHub.
- `spain.py`: navegación por informes y secciones FELGTBI+.
- `didactica.py`: glosario, lecciones, juegos, progreso y herramientas Docente.
- `admin/`: gestión de usuarios e importaciones.
- `session/`: registro, login, verificación y recuperación de contraseña.
- `__init__.py`: marcador necesario del paquete.

Los antiguos archivos vacíos `didactics.py` y `report.py` se eliminaron. Las rutas históricas
`/didactics` y `/report` se redirigen desde `dash_app.py` a las páginas reales.

## Registro de callbacks

Cada módulo expone su builder y, cuando corresponde, una función `register_*_callbacks()`.
`create_dash_app()` registra 61 callbacks. Las páginas se construyen de forma dinámica y por eso
Dash usa `suppress_callback_exceptions=True`; los endpoints `/_dash-layout` y
`/_dash-dependencies` se comprueban en smoke tests.

Los estados `dcc.Store` están limitados a preferencias, selección, paginación, juegos, informes
y edición. Todos tienen consumidores registrados; no conservan archivos fallidos grandes.
