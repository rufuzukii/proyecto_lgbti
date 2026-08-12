from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Literal

from dash import html
from dash.development.base_component import Component

from app.dash.i18n import dash_attrs, text_attrs
from app.dash.layouts.navigation import build_navbar
from app.dash.routes import normalize_language, route_path
from app.errors import DatabaseUnavailableError

ErrorKind = Literal["401", "403", "404", "500", "503", "insufficient_data"]


@dataclass(frozen=True, slots=True)
class ErrorPageCopy:
    code_es: str
    code_en: str
    title_es: str
    title_en: str
    message_es: str
    message_en: str
    http_status: int


ERROR_PAGES: dict[ErrorKind, ErrorPageCopy] = {
    "401": ErrorPageCopy(
        "401 \u2014 Autenticaci\u00f3n necesaria",
        "401 \u2014 Authentication required",
        "Inicia sesi\u00f3n para continuar",
        "Sign in to continue",
        "Esta secci\u00f3n requiere una cuenta autenticada.",
        "This section requires an authenticated account.",
        401,
    ),
    "403": ErrorPageCopy(
        "403 \u2014 Acceso denegado",
        "403 \u2014 Access denied",
        "No tienes permiso para acceder",
        "You do not have permission to access",
        "Tu cuenta no dispone del permiso necesario para esta operaci\u00f3n.",
        "Your account does not have the required permission for this operation.",
        403,
    ),
    "404": ErrorPageCopy(
        "404 \u2014 P\u00e1gina no encontrada",
        "404 \u2014 Page not found",
        "La p\u00e1gina que buscas no existe",
        "The page you are looking for does not exist",
        "Comprueba la direcci\u00f3n o vuelve al inicio para seguir navegando.",
        "Check the address or return home to continue browsing.",
        404,
    ),
    "500": ErrorPageCopy(
        "500 \u2014 Error interno",
        "500 \u2014 Internal error",
        "No ha sido posible completar la operaci\u00f3n",
        "The operation could not be completed",
        "Se ha registrado el error. Int\u00e9ntalo de nuevo m\u00e1s tarde.",
        "The error has been logged. Please try again later.",
        500,
    ),
    "503": ErrorPageCopy(
        "Servicio no disponible",
        "Service unavailable",
        "No ha sido posible cargar la informaci\u00f3n",
        "The information could not be loaded",
        "No ha sido posible obtener la informaci\u00f3n en este momento. Int\u00e9ntalo de nuevo m\u00e1s tarde.",
        "The information could not be retrieved right now. Please try again later.",
        503,
    ),
    "insufficient_data": ErrorPageCopy(
        "Datos insuficientes",
        "Insufficient data",
        "No hay datos suficientes para este an\u00e1lisis",
        "There is not enough data for this analysis",
        "Cambia los filtros o selecciona otro indicador.",
        "Change the filters or select another indicator.",
        422,
    ),
}


def build_error_layout(
    kind: ErrorKind,
    *,
    include_navigation: bool = True,
    language: str | None = None,
) -> Component:
    copy = ERROR_PAGES[kind]
    selected_language = normalize_language(language)
    is_english = selected_language == "en"
    panel = html.Main(
        [
            html.P(
                copy.code_en if is_english else copy.code_es,
                className="error-page-code",
                **text_attrs(copy.code_es, copy.code_en),
            ),
            html.H1(
                copy.title_en if is_english else copy.title_es,
                **text_attrs(copy.title_es, copy.title_en),
            ),
            html.P(
                copy.message_en if is_english else copy.message_es,
                className="error-page-message",
                **text_attrs(copy.message_es, copy.message_en),
            ),
            html.A(
                "Back to home" if is_english else "Volver al inicio",
                href=route_path("home", selected_language),
                className="error-page-action",
                **dash_attrs(
                    {
                        **text_attrs("Volver al inicio", "Back to home"),
                    }
                ),
            ),
        ],
        className="error-page-panel",
    )
    children: list[Component] = [panel]
    if include_navigation:
        children.insert(0, build_navbar(active=None))
    return html.Div(children, className="error-page-shell")


def render_error_response(
    kind: ErrorKind,
    *,
    language: str = "es",
) -> tuple[str, int, dict[str, str]]:
    copy = ERROR_PAGES[kind]
    is_english = language == "en"
    code = copy.code_en if is_english else copy.code_es
    title = copy.title_en if is_english else copy.title_es
    message = copy.message_en if is_english else copy.message_es
    action = "Back to home" if is_english else "Volver al inicio"
    page_language = "en" if is_english else "es"
    home_path = route_path("home", page_language)
    body = f"""<!DOCTYPE html>
<html lang="{page_language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RainbowLens Datahub \u00b7 {escape(code)}</title>
  <link rel="stylesheet" href="/assets/styles.css">
  <link rel="icon" href="/assets/img/rainbow_lens_icono.ico">
</head>
<body>
  <main class="error-page-shell error-page-static">
    <section class="error-page-panel">
      <p class="error-page-code">{escape(code)}</p>
      <h1>{escape(title)}</h1>
      <p class="error-page-message">{escape(message)}</p>
      <a class="error-page-action" href="{home_path}">{escape(action)}</a>
    </section>
  </main>
</body>
</html>"""
    headers = {"Content-Type": "text/html; charset=utf-8"}
    if kind == "503":
        headers["Retry-After"] = "30"
    return body, copy.http_status, headers


def build_database_unavailable_layout(
    error: DatabaseUnavailableError | None = None,
) -> Component:
    del error
    return build_error_layout("503")


def render_database_unavailable_response(
    error: DatabaseUnavailableError | None = None,
) -> tuple[str, int, dict[str, str]]:
    del error
    return render_error_response("503")
