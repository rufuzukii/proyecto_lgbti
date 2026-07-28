from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import re
from typing import Any, Mapping

import bleach
import plotly.graph_objects as go

from app.analytics.statistics_normalizers import normalize_country_code


DEFAULT_REPORT_SECTIONS: tuple[str, ...] = (
    "executive",
    "methodology",
    "metrics",
    "workplace",
    "comparison",
    "demographics",
    "risks",
    "recommendations",
    "limitations",
    "sources",
)

DEFAULT_REPORT_CHARTS: tuple[str, ...] = (
    "ranking",
    "average",
    "countries",
    "responses",
    "temporal",
    "radar",
)


def sanitize_report_text(value: Any, *, maximum: int = 160) -> str:
    """Strip markup/control characters and bound user-provided report text."""
    clean = bleach.clean(str(value or ""), tags=[], attributes={}, strip=True)
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", clean)
    return " ".join(clean.split())[:maximum].strip()


def normalize_report_countries(values: Any) -> tuple[str, ...]:
    if isinstance(values, str):
        candidates = values.split(",")
    elif isinstance(values, (list, tuple, set)):
        candidates = list(values)
    else:
        candidates = []
    countries: list[str] = []
    for candidate in candidates:
        code = normalize_country_code(candidate)
        if code and len(code) <= 3 and code not in countries:
            countries.append(code)
    return tuple(countries)


@dataclass(frozen=True)
class ReportConfiguration:
    source: str = "fra"
    category: str = ""
    indicator_id: str = ""
    indicator_label: str = ""
    answer: str = ""
    criterion: str = ""
    year: int | None = None
    countries: tuple[str, ...] = ()
    primary_country: str = ""
    filter_a_name: str = "All"
    filter_a_value: str = "All"
    filter_b_name: str = "All"
    filter_b_value: str = "All"
    title: str = "Informe de diversidad e inclusión LGTBIQ+"
    organization: str = ""
    author: str = ""
    language: str = "es"
    mode: str = "automatic"
    detail_level: str = "standard"
    sections: tuple[str, ...] = DEFAULT_REPORT_SECTIONS
    charts: tuple[str, ...] = DEFAULT_REPORT_CHARTS
    generated_on: str = field(default_factory=lambda: date.today().isoformat())

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "ReportConfiguration":
        payload = values or {}
        source = "ilga" if str(payload.get("source") or "").lower() == "ilga" else "fra"
        language = "en" if str(payload.get("language") or "").lower() == "en" else "es"
        mode = "custom" if str(payload.get("mode") or "").lower() == "custom" else "automatic"
        detail_level = (
            "detailed"
            if str(payload.get("detail_level") or "").lower() == "detailed"
            else "standard"
        )
        countries = normalize_report_countries(payload.get("countries"))
        primary = normalize_country_code(payload.get("primary_country"))
        if not primary and countries:
            primary = countries[0]
        if primary and primary not in countries:
            countries = (primary, *countries)
        if mode == "automatic":
            sections = DEFAULT_REPORT_SECTIONS
            charts = DEFAULT_REPORT_CHARTS
        else:
            sections = _allowed_values(
                payload.get("sections"),
                DEFAULT_REPORT_SECTIONS,
            )
            charts = _allowed_values(
                payload.get("charts"),
                DEFAULT_REPORT_CHARTS,
            )
        return cls(
            source=source,
            category=sanitize_report_text(payload.get("category"), maximum=180),
            indicator_id=sanitize_report_text(payload.get("indicator_id"), maximum=120),
            indicator_label=sanitize_report_text(payload.get("indicator_label"), maximum=240),
            answer=sanitize_report_text(payload.get("answer"), maximum=120),
            criterion=sanitize_report_text(payload.get("criterion"), maximum=240),
            year=_safe_year(payload.get("year")),
            countries=countries,
            primary_country=primary,
            filter_a_name=sanitize_report_text(payload.get("filter_a_name"), maximum=120) or "All",
            filter_a_value=sanitize_report_text(payload.get("filter_a_value"), maximum=160) or "All",
            filter_b_name=sanitize_report_text(payload.get("filter_b_name"), maximum=120) or "All",
            filter_b_value=sanitize_report_text(payload.get("filter_b_value"), maximum=160) or "All",
            title=sanitize_report_text(payload.get("title"), maximum=180)
            or (
                "LGBTIQ+ diversity and inclusion report"
                if language == "en"
                else "Informe de diversidad e inclusión LGTBIQ+"
            ),
            organization=sanitize_report_text(payload.get("organization"), maximum=120),
            author=sanitize_report_text(payload.get("author"), maximum=120),
            language=language,
            mode=mode,
            detail_level=detail_level,
            sections=sections,
            charts=charts,
            generated_on=_safe_date(payload.get("generated_on")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReportDataset:
    result: dict[str, Any]
    query_seconds: float


@dataclass(frozen=True)
class ReportMetric:
    key: str
    label: str
    display_value: str
    numeric_value: float | None = None
    unit: str = ""


@dataclass(frozen=True)
class ReportRecommendation:
    text: str
    derived_from_metrics: bool


@dataclass
class ReportChart:
    key: str
    title: str
    figure: go.Figure
    source: str


@dataclass
class ReportContent:
    configuration: ReportConfiguration
    source_name: str
    indicator: str
    country_names: list[str]
    metrics: list[ReportMetric]
    executive_summary: list[str]
    methodology: list[str]
    workplace_analysis: list[str]
    demographic_analysis: list[str]
    conclusions: list[str]
    recommendations: list[ReportRecommendation]
    limitations: list[str]
    sources: list[str]
    charts: list[ReportChart]
    table_rows: list[dict[str, Any]]
    timings: dict[str, float] = field(default_factory=dict)


def _allowed_values(
    value: Any,
    allowed: tuple[str, ...],
) -> tuple[str, ...]:
    values = value.split(",") if isinstance(value, str) else list(value or [])
    return tuple(item for item in allowed if item in {str(candidate) for candidate in values})


def _safe_year(value: Any) -> int | None:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2200 else None


def _safe_date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        return date.today().isoformat()
