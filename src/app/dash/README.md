# Frontend Dash

Esta carpeta contiene la presentación de RainbowLens Datahub. La composición y el enrutamiento viven en `src/app/dash_app.py`; aquí se almacenan componentes reutilizables, páginas y estilos.

## Archivo Python

- Los módulos de UI importan directamente los componentes modernos de Dash (`Dash`, `dcc`, `html`, `dash_table`, `Input`, `Output`, `State`) desde `dash`.
- `__init__.py`: marcador de paquete.

## Carpetas

- `layouts/`: navegación, inicio y perfil.
- `pages/`: pantallas de sesión, administración, estadísticas y carga.
- `assets/`: CSS e imágenes servidos automáticamente por Dash.

## Rutas efectivas

- `/`: inicio con mapa ILGA.
- `/statistics`: panel FRA/ILGA.
- `/didactica` y sus subrutas: recursos educativos, juegos, lecciones y progreso.
- `/upload`: importación de CSV.
- `/login`, `/register`, `/user`: sesión y perfil.
- `/admin`, `/admin/imports`: administración.

La ruta histórica `/didactics` redirige a `/didactica`. El espacio
`/didactica/docentes` requiere el perfil interno `docente` o el rol `admin`, que
hereda todos los permisos. El acceso se vuelve a validar en servicios, rutas,
callbacks y descargas. `/upload` es exclusivo de administración; `/informes`
requiere sesión y reserva su configuración avanzada para RRHH, Político y ONG.

## Ejecución

```powershell
rainbowlens-dash
```

La autenticación usa sesiones Flask-Login; no usa `DASH_BASIC_AUTH`.
