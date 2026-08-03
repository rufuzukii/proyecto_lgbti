from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from app.dash.i18n import text, text_attrs
from app.dash.layouts.navigation import build_navbar
from app.errors import DatabaseUnavailableError


def build_database_unavailable_layout(
    error: DatabaseUnavailableError | None = None,
) -> Component:
    return html.Div(
        [
            build_navbar(active=None),
            html.Main(
                [
                    html.P(
                        "Servicio no disponible",
                        className="error-page-code",
                        **text_attrs("Servicio no disponible", "Service unavailable"),
                    ),
                    html.H1(
                        text(
                            "No ha sido posible cargar la información",
                            "The information could not be loaded",
                        )
                    ),
                    html.P(
                        text(
                            "No ha sido posible obtener la información en este momento. Inténtalo de nuevo más tarde.",
                            "The information could not be retrieved right now. Please try again later.",
                        ),
                        className="error-page-message",
                    ),
                    html.A(
                        text("Volver al inicio", "Back to home"),
                        href="/",
                        className="error-page-action",
                    ),
                ],
                className="error-page-panel",
            ),
        ],
        className="error-page-shell",
    )


def render_database_unavailable_response(
    error: DatabaseUnavailableError | None = None,
) -> tuple[str, int, dict[str, str]]:
    body = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RainbowLens Datahub · Servicio no disponible</title>
  <link rel="stylesheet" href="/assets/styles.css">
  <link rel="icon" href="/assets/img/rainbow_lens_icono.ico">
</head>
<body>
  <main class="error-page-shell error-page-static">
    <section class="error-page-panel">
      <p class="error-page-code">Servicio no disponible</p>
      <h1>No ha sido posible cargar la información</h1>
      <p class="error-page-message">No ha sido posible obtener la información en este momento. Inténtalo de nuevo más tarde.</p>
      <a class="error-page-action" href="/">Volver al inicio</a>
    </section>
  </main>
</body>
</html>"""
    return body, 503, {"Retry-After": "30"}
