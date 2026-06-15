from app.dash.compat import dcc, html
from app.dash.layouts.navigation import build_navbar
import plotly.graph_objects as go


EUROPE_SNAPSHOT = [
    {"country": "Spain", "score": 72, "note": "Legal framework improving"},
    {"country": "Portugal", "score": 74, "note": "Strong local practices"},
    {"country": "France", "score": 78, "note": "Stable public policies"},
    {"country": "Germany", "score": 76, "note": "Active education programs"},
    {"country": "Italy", "score": 62, "note": "Ongoing social debate"},
    {"country": "Netherlands", "score": 90, "note": "Equality benchmark"},
    {"country": "Belgium", "score": 86, "note": "Broad protections"},
    {"country": "Ireland", "score": 80, "note": "Legislative progress"},
    {"country": "Sweden", "score": 88, "note": "Strong support services"},
    {"country": "Norway", "score": 87, "note": "Institutional commitment"},
    {"country": "Poland", "score": 50, "note": "Pending challenges"},
    {"country": "Hungary", "score": 52, "note": "Needs improvement"},
    {"country": "Greece", "score": 60, "note": "Growing initiatives"},
    {"country": "Romania", "score": 54, "note": "Emerging programs"},
    {"country": "Czech Republic", "score": 66, "note": "New initiatives"},
]


def build_europe_map_figure() -> go.Figure:
    countries = [entry["country"] for entry in EUROPE_SNAPSHOT]
    scores = [entry["score"] for entry in EUROPE_SNAPSHOT]
    notes = [entry["note"] for entry in EUROPE_SNAPSHOT]

    figure = go.Figure(
        go.Choropleth(
            locations=countries,
            locationmode="country names",
            z=scores,
            text=notes,
            zmin=45,
            zmax=95,
            colorscale=[[0.0, "#e0e7ff"], [0.5, "#818cf8"], [1.0, "#312e81"]],
            marker={"line": {"color": "#ffffff", "width": 0.6}},
            colorbar={"title": "Index", "ticksuffix": "/100", "thickness": 12},
            hovertemplate="<b>%{location}</b><br>Index: %{z}/100<br>%{text}<extra></extra>",
        )
    )
    figure.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        geo=dict(
            scope="europe",
            projection_type="natural earth",
            showframe=False,
            showcoastlines=False,
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure


def _stat_card(value: str, label: str) -> html.Div:
    return html.Div(
        [
            html.Div(value, className="stat-value"),
            html.Div(label, className="stat-label"),
        ],
        className="stat-card",
    )


def build_home_layout() -> html.Div:
    map_figure = build_europe_map_figure()
    return html.Div(
        [
            build_navbar(active="home"),
            html.Main(
                [
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Span(
                                                "RainbowLens",
                                                className="hero-eyebrow",
                                            ),
                                            html.H1(
                                                "Welcome to the LGBTIQ+ analysis and support platform",
                                                className="hero-title",
                                            ),
                                            html.P(
                                                "Explore data, trends, and resources that strengthen LGBTIQ+ advocacy. "
                                                "This version prioritizes a clear visual experience while detailed "
                                                "analytics continue to evolve.",
                                                className="hero-text",
                                            ),
                                            html.Div(
                                                [
                                                    html.A(
                                                        "View features",
                                                        href="#features",
                                                        className="hero-pill",
                                                    ),
                                                    html.A(
                                                        "Learn the purpose",
                                                        href="#purpose",
                                                        className="hero-pill secondary",
                                                    ),
                                                ],
                                                className="hero-actions",
                                            ),
                                            html.Div(
                                                [
                                                    _stat_card(
                                                        str(len(EUROPE_SNAPSHOT)),
                                                        "Countries on the map",
                                                    ),
                                                    _stat_card("6", "Initial indicators"),
                                                    _stat_card("4", "Sources in progress"),
                                                ],
                                                className="hero-stats",
                                            ),
                                        ],
                                        className="hero-card",
                                    ),
                                    html.Div(
                                        [
                                            html.H3(
                                                "Interactive Europe map",
                                                className="map-title",
                                            ),
                                            html.P(
                                                "Hover over a country to view its summary and compare progress.",
                                                className="map-caption",
                                            ),
                                            dcc.Graph(
                                                id="europe-map",
                                                figure=map_figure,
                                                className="hero-map-graph",
                                                config={
                                                    "displayModeBar": False,
                                                    "scrollZoom": True,
                                                },
                                            ),
                                            html.P(
                                                "Initial reference map. Values will be adjusted with real data.",
                                                className="map-caption",
                                            ),
                                        ],
                                        id="map",
                                        className="hero-map-card",
                                    ),
                                ],
                                className="hero-grid container",
                            )
                        ],
                        className="hero-section",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.H2(
                                        "Main features",
                                        className="section-title",
                                        id="features",
                                    ),
                                    html.P(
                                        "A general view of what the platform offers to research, compare, "
                                        "and communicate key data.",
                                        className="section-subtitle",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.H3("Data upload and cleaning"),
                                                    html.P(
                                                        "Import CSV files and centralize official-source information "
                                                        "to analyze trends across Europe."
                                                    ),
                                                ],
                                                className="feature-card",
                                            ),
                                            html.Div(
                                                [
                                                    html.H3("Dynamic dashboard"),
                                                    html.P(
                                                        "View indicators, rankings, and country comparisons "
                                                        "with maps, charts, and cards."
                                                    ),
                                                ],
                                                className="feature-card",
                                            ),
                                            html.Div(
                                                [
                                                    html.H3("Reports and export"),
                                                    html.P(
                                                        "Generate share-ready reports and export charts "
                                                        "for institutions and working teams."
                                                    ),
                                                ],
                                                className="feature-card",
                                            ),
                                            html.Div(
                                                [
                                                    html.H3("Education module"),
                                                    html.P(
                                                        "Access educational resources and awareness guides "
                                                        "focused on diversity and respect."
                                                    ),
                                                ],
                                                className="feature-card",
                                            ),
                                            html.Div(
                                                [
                                                    html.H3("User management"),
                                                    html.P(
                                                        "Define permissions and profiles for secure collaboration "
                                                        "between institutions, HR teams, and educators."
                                                    ),
                                                ],
                                                className="feature-card",
                                            ),
                                        ],
                                        className="features-grid",
                                    ),
                                ],
                                className="container",
                            )
                        ],
                        className="features-section",
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.H2(
                                        "Purpose and commitment",
                                        className="section-title",
                                        id="purpose",
                                    ),
                                    html.P(
                                        "Our purpose is to support the LGBTIQ+ community by providing "
                                        "evidence, visibility, and practical action tools.",
                                        className="section-subtitle",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.H3("Visibility through data"),
                                                    html.P(
                                                        "We turn scattered information into clear narratives "
                                                        "that make real progress and challenges visible."
                                                    ),
                                                ],
                                                className="mission-card",
                                            ),
                                            html.Div(
                                                [
                                                    html.H3("Institutional support"),
                                                    html.P(
                                                        "We support evidence-based decisions for public, "
                                                        "educational, and HR policies."
                                                    ),
                                                ],
                                                className="mission-card",
                                            ),
                                            html.Div(
                                                [
                                                    html.H3("Education and empathy"),
                                                    html.P(
                                                        "We provide resources that promote awareness "
                                                        "and respect for diversity across Europe."
                                                    ),
                                                ],
                                                className="mission-card",
                                            ),
                                        ],
                                        className="mission-grid",
                                    ),
                                ],
                                className="container",
                            )
                        ],
                        className="mission-section",
                    ),
                ],
                className="page-shell",
            ),
        ]
    )
