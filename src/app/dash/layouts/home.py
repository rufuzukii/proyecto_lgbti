from dash import html


def build_home_layout() -> html.Div:
    return html.Div(
        [
            html.Nav(
                [
                    html.Div("LGBTIQ+ Insights", className="nav-brand"),
                    html.Ul(
                        [
                            html.Li(html.A("Inicio", href="#", className="nav-link")),
                            html.Li(html.A("Datos", href="#", className="nav-link")),
                            html.Li(html.A("Informes", href="#", className="nav-link")),
                            html.Li(html.A("Didactica", href="#", className="nav-link")),
                            html.Li(html.A("Usuarios", href="#", className="nav-link")),
                        ],
                        className="nav-links",
                    ),
                ],
                className="navbar",
            ),
            html.Main(
                [
                    html.Header(
                        [
                            html.H1("Pagina principal"),
                            html.P(
                                "Contenido de ejemplo. Aqui se mostraran modulos, "
                                "estadisticas y navegacion"
                            ),
                        ],
                        className="page-header",
                    ),
                    html.Section(
                        [
                            html.Div(
                                "Placeholder generico para el contenido principal.",
                                className="placeholder-card",
                            )
                        ],
                        className="page-section",
                    ),
                ],
                className="page-container",
            ),
        ]
    )
