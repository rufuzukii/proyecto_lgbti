from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, cast

import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from app.analytics.percentage_display import coerce_percentage, format_percentage
from app.analytics.statistics_normalizers import normalize_country_code
from app.source_attribution import source_metadata

LEGAL_MAP_EXPORT_WIDTH = 1800
LEGAL_MAP_EXPORT_HEIGHT = 1200
LEGAL_MAP_EXPORT_SCALE = 1.5

CountryNameResolver = Callable[[str, str], str]


class LegalMapExportError(RuntimeError):
    """Raised when the combined legal map image cannot be rendered."""


@dataclass(frozen=True, slots=True)
class LegalRankingEntry:
    country_code: str
    country_name: str
    score: float

    @property
    def score_text(self) -> str:
        return format_percentage(self.score) or ""


def build_legal_ranking(
    document: Mapping[str, Any] | None,
    *,
    country_name_resolver: CountryNameResolver | None = None,
) -> list[LegalRankingEntry]:
    """Build one stable descending ranking from an ILGA map document."""
    countries = document.get("countries") if isinstance(document, Mapping) else None
    if not isinstance(countries, list):
        return []

    entries: list[LegalRankingEntry] = []
    for country in countries:
        if not isinstance(country, Mapping):
            continue
        score = coerce_percentage(country.get("ranking"))
        if score is None:
            continue
        country_code = normalize_country_code(
            country.get("country_code"),
            country.get("country"),
        )
        if not country_code:
            continue
        fallback = str(country.get("country") or country_code).strip() or country_code
        country_name = (
            country_name_resolver(country_code, fallback)
            if country_name_resolver is not None
            else fallback
        )
        entries.append(
            LegalRankingEntry(
                country_code=country_code,
                country_name=str(country_name or fallback).strip() or fallback,
                score=score,
            )
        )
    return _sort_legal_ranking(entries)


def legal_ranking_payload(entries: Sequence[LegalRankingEntry]) -> list[dict[str, Any]]:
    """Return the small JSON-safe payload shared with the export callback."""
    return [asdict(entry) for entry in entries]


def legal_ranking_from_payload(rows: Sequence[Mapping[str, Any]] | None) -> list[LegalRankingEntry]:
    """Validate and order a ranking received back from a Dash store."""
    entries: list[LegalRankingEntry] = []
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        country_code = normalize_country_code(row.get("country_code"))
        country_name = str(row.get("country_name") or "").strip()
        score = coerce_percentage(row.get("score"))
        if not country_code or not country_name or score is None:
            continue
        entries.append(LegalRankingEntry(country_code, country_name, score))
    return _sort_legal_ranking(entries)


def build_legal_map_export_figure(
    map_figure: Mapping[str, Any] | go.Figure,
    ranking_rows: Sequence[Mapping[str, Any]] | None,
    *,
    year: int | str | None,
    language: str,
    theme: str = "light",
) -> go.Figure:
    """Compose the visible legal map and its ranking into one Plotly figure."""
    source_figure = go.Figure(map_figure)
    ranking = legal_ranking_from_payload(ranking_rows)
    english = language == "en"
    colors = _export_colors(theme)
    ranking_title = "Country ranking" if english else "Ranking de países"
    country_label = "Country" if english else "País"
    score_label = "Legal score" if english else "Puntuación legal"
    map_title = "European LGBTIQ+ map" if english else "Mapa europeo LGBTIQ+"

    figure = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "geo"}, {"type": "table"}]],
        column_widths=[0.7, 0.3],
        horizontal_spacing=0.055,
    )
    for source_trace in cast(Any, source_figure).data:
        trace = go.Choropleth(source_trace) if source_trace.type == "choropleth" else source_trace
        if trace.type == "choropleth":
            trace.update(
                colorbar={
                    "title": "%",
                    "ticksuffix": "%",
                    "thickness": 14,
                    "len": 0.64,
                    "x": 0.015,
                    "xanchor": "left",
                    "y": 0.5,
                    "tickfont": {"color": colors["muted_text"]},
                    "title_font": {"color": colors["text"]},
                }
            )
            trace.update(marker={"line": {"color": colors["country_border"], "width": 0.7}})
        figure.add_trace(trace, row=1, col=1)

    if not source_figure.data:
        figure.add_annotation(
            text=("No legal data available" if english else "No hay datos legales disponibles"),
            x=0.33,
            y=0.5,
            showarrow=False,
        )

    figure.add_trace(
        go.Table(
            columnwidth=[28, 155, 58],
            header={
                "values": ["#", f"<b>{country_label}</b>", f"<b>{score_label}</b>"],
                "align": ["right", "left", "right"],
                "fill_color": colors["table_header"],
                "font": {"color": colors["table_header_text"], "size": 13},
                "height": 26,
                "line_color": colors["table_line"],
            },
            cells={
                "values": [
                    list(range(1, len(ranking) + 1)),
                    [entry.country_name for entry in ranking],
                    [entry.score_text for entry in ranking],
                ],
                "align": ["right", "left", "right"],
                "fill_color": colors["background"],
                "font": {"color": colors["text"], "size": 12},
                "height": 18,
                "line_color": colors["table_line"],
            },
        ),
        row=1,
        col=2,
    )

    geo_layout = source_figure.layout.geo.to_plotly_json()
    geo_layout.pop("domain", None)
    geo_layout.update(
        {
            "bgcolor": colors["background"],
            "landcolor": colors["land"],
            "oceancolor": colors["ocean"],
            "coastlinecolor": colors["coast"],
        }
    )
    figure.update_geos(**geo_layout, row=1, col=1)
    source = source_metadata("ilga", year=_clean_year(year)).attribution(
        language,
        compact=True,
    )
    year_suffix = f" · {year}" if year is not None and str(year).strip() else ""
    figure.update_layout(
        width=LEGAL_MAP_EXPORT_WIDTH,
        height=LEGAL_MAP_EXPORT_HEIGHT,
        margin={"l": 55, "r": 42, "t": 112, "b": 78},
        paper_bgcolor=colors["background"],
        plot_bgcolor=colors["background"],
        font={"family": "Segoe UI, Arial, sans-serif", "color": colors["text"]},
        title={
            "text": f"<b>RainbowLens DataHub</b><br><sup>{map_title}{year_suffix}</sup>",
            "x": 0.025,
            "xanchor": "left",
            "font": {"size": 24},
        },
        annotations=[
            {
                "text": f"<b>{ranking_title}{year_suffix}</b>",
                "x": 0.84,
                "y": 1.035,
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "font": {"size": 16, "color": colors["text"]},
            },
            {
                "text": source,
                "x": 0.025,
                "y": -0.055,
                "xref": "paper",
                "yref": "paper",
                "xanchor": "left",
                "showarrow": False,
                "font": {"size": 11, "color": colors["muted_text"]},
            },
        ],
    )
    return figure


def export_legal_map_png(figure: go.Figure) -> bytes:
    """Render the combined map/ranking figure as a PNG with Kaleido."""
    try:
        return pio.to_image(
            figure,
            format="png",
            width=LEGAL_MAP_EXPORT_WIDTH,
            height=LEGAL_MAP_EXPORT_HEIGHT,
            scale=LEGAL_MAP_EXPORT_SCALE,
            validate=True,
        )
    except Exception as exc:
        raise LegalMapExportError("The legal map image could not be generated.") from exc


def legal_map_export_filename(year: int | str | None) -> str:
    clean_year = _clean_year(year)
    suffix = f"_{clean_year}" if clean_year is not None else ""
    return f"rainbowlens_ranking_legal_europa{suffix}.png"


def _sort_legal_ranking(entries: Sequence[LegalRankingEntry]) -> list[LegalRankingEntry]:
    return sorted(
        entries,
        key=lambda entry: (
            -entry.score,
            _sort_text(entry.country_name),
            entry.country_code,
        ),
    )


def _sort_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _clean_year(value: int | str | None) -> int | None:
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _export_colors(theme: str) -> dict[str, str]:
    if str(theme or "").strip().casefold() == "dark":
        return {
            "background": "#111827",
            "text": "#f7f9fc",
            "muted_text": "#aeb8c7",
            "land": "#1a2232",
            "ocean": "#172132",
            "coast": "#536176",
            "country_border": "#d8dee9",
            "table_header": "#203342",
            "table_header_text": "#f7f9fc",
            "table_line": "#344054",
        }
    return {
        "background": "#ffffff",
        "text": "#252a31",
        "muted_text": "#5f6672",
        "land": "#edf1f4",
        "ocean": "#dcebf2",
        "coast": "#b9c0ca",
        "country_border": "#ffffff",
        "table_header": "#e8f3ee",
        "table_header_text": "#17352a",
        "table_line": "#d7e2dc",
    }
