# Frontend Dash

Esta carpeta contiene la presentación de RainbowLens. La composición y el enrutamiento viven en `src/app/dash_app.py`; aquí se almacenan componentes reutilizables, páginas y estilos.

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
- `/upload`: importación de CSV.
- `/login`, `/register`, `/user`: sesión y perfil.
- `/admin`, `/admin/imports`: administración.

Los enlaces `/report`, `/didactics` y `/about` aparecen en la barra, pero `dash_app.py` no tiene ramas para ellos: actualmente muestran el inicio.

## Ejecución

```powershell
python run_dash.py
```

La autenticación usa sesiones Flask-Login; no usa `DASH_BASIC_AUTH`.
