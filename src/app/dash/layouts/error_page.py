from __future__ import annotations

from app.dash.compat import html
from app.dash.layouts.navigation import build_navbar
from app.errors import DatabaseUnavailableError


def build_database_unavailable_layout(
    error: DatabaseUnavailableError | None = None,
) -> html.Div:
    service = _service_name(error)
    return html.Div(
        [
            build_navbar(active=None),
            html.Main(
                [
                    html.P("Error 503", className="error-page-code"),
                    html.H1("Base de datos no disponible"),
                    html.P(
                        f"No se puede conectar con {service}. "
                        "Si el proyecto estaba pausado, reanudalo y vuelve a cargar la pagina en unos minutos.",
                        className="error-page-message",
                    ),
                    html.A("Volver al inicio", href="/", className="error-page-action"),
                ],
                className="error-page-panel",
            ),
        ],
        className="error-page-shell",
    )


def render_database_unavailable_response(
    error: DatabaseUnavailableError | None = None,
) -> tuple[str, int, dict[str, str]]:
    service = _service_name(error)
    body = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>503 - Base de datos no disponible</title>
  <link rel="stylesheet" href="/assets/styles.css">
  <link rel="icon" href="/assets/img/rainbow_lens_icono.ico">
</head>
<body>
  <main class="error-page-shell error-page-static">
    <section class="error-page-panel">
      <p class="error-page-code">Error 503</p>
      <h1>Base de datos no disponible</h1>
      <p class="error-page-message">No se puede conectar con {service}. Si el proyecto estaba pausado, reanudalo y vuelve a cargar la pagina en unos minutos.</p>
      <a class="error-page-action" href="/">Volver al inicio</a>
    </section>
  </main>
</body>
</html>"""
    return body, 503, {"Retry-After": "30"}


def _service_name(error: DatabaseUnavailableError | None) -> str:
    if error is None:
        return "la base de datos"
    if error.service == "PostgreSQL":
        return "PostgreSQL/Supabase"
    return error.service
