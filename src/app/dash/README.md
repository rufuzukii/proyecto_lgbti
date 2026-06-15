# Dash frontend

Interfaz principal construida con Dash. Esta vista se centra en una experiencia visual inicial, con un mapa interactivo de Europa y secciones de bienvenida, funcionalidades y objetivos.

## Ejecucion rapida

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_dash.py
```

## Estructura

- `src/app/dash/layouts/home.py`: layout de la pagina principal.
- `src/app/dash/assets/styles.css`: estilos globales del frontend.
- `src/app/dash/pages/upload.py`: pagina de carga de CSV.

## Seguridad

- `DASH_BASIC_AUTH`: credenciales en formato `usuario:password,otro:password`.


