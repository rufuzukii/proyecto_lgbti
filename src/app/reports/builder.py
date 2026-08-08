from __future__ import annotations

import math
import time
from typing import Any, cast

import pandas as pd

from app.analytics.statistics_charts import (
    build_comparative_ranking_chart,
    build_eu_average_comparison_chart,
    build_experience_legal_radar,
    build_fra_response_comparison_chart,
    build_ilga_response_details_chart,
    build_response_country_comparison_chart,
    build_temporal_evolution_chart,
)
from app.analytics.statistics_exports import prepare_figure_for_export
from app.analytics.statistics_normalizers import normalize_country_code
from app.reports.models import (
    ReportChart,
    ReportConfiguration,
    ReportContent,
    ReportDataset,
    ReportMetric,
)
from app.reports.recommendations import (
    build_recommendations,
    indicator_direction,
    is_hr_relevant_indicator,
)
from app.source_attribution import attribution_for_sources


def _first_comparable_radar_country(payload: dict[str, Any]) -> str | None:
    dataframe = pd.DataFrame(payload.get("rows") or [])
    required = {"iso", "dimension", "experience_score", "legal_score"}
    if dataframe.empty or not required.issubset(dataframe.columns):
        return None
    dataframe["experience_score"] = pd.to_numeric(dataframe["experience_score"], errors="coerce")
    dataframe["legal_score"] = pd.to_numeric(dataframe["legal_score"], errors="coerce")
    comparable = dataframe.dropna(subset=["experience_score", "legal_score"])
    coverage = comparable.groupby("iso")["dimension"].nunique().sort_values(ascending=False)
    valid = coverage[coverage.ge(3)]
    return str(valid.index[0]) if not valid.empty else None


class HRReportBuilder:
    """Build controlled HR report content from a shared statistics result."""

    def build(
        self,
        configuration: ReportConfiguration,
        dataset: ReportDataset,
    ) -> ReportContent:
        started = time.perf_counter()
        result = dataset.result
        ranking = _ranking_frame(result.get("ranking") or [])
        source_name = str(result.get("source") or "")
        indicator = str(
            result.get("indicator")
            or configuration.indicator_label
            or configuration.indicator_id
            or configuration.category
            or ""
        )
        selected = list(configuration.countries)
        country_names = _country_names(ranking, selected)
        primary_row = _primary_row(ranking, configuration.primary_country)
        eu_average = float(ranking["value"].mean()) if not ranking.empty else None
        primary_value = _number(primary_row.get("value")) if primary_row is not None else None
        primary_name = (
            str(primary_row.get("country"))
            if primary_row is not None
            else (country_names[0] if country_names else "")
        )
        metrics = _metrics(
            ranking,
            primary_row,
            eu_average,
            language=configuration.language,
        )
        charts = _charts(
            configuration,
            result,
            ranking,
            selected,
            country_names,
            indicator,
        )
        summary = _executive_summary(
            configuration,
            indicator=indicator,
            primary_name=primary_name,
            primary_value=primary_value,
            eu_average=eu_average,
        )
        recommendations = build_recommendations(
            indicator=indicator,
            country_value=primary_value,
            eu_average=eu_average,
            language=configuration.language,
        )
        conclusions = _conclusions(
            configuration,
            indicator=indicator,
            primary_name=primary_name,
            primary_value=primary_value,
            eu_average=eu_average,
        )
        limitations = _limitations(configuration, indicator, result)
        content = ReportContent(
            configuration=configuration,
            source_name=source_name,
            indicator=indicator,
            country_names=country_names,
            metrics=metrics,
            executive_summary=summary,
            methodology=_methodology(configuration.language, source_name, result),
            workplace_analysis=_workplace_analysis(
                configuration,
                indicator,
                primary_name,
                primary_value,
                eu_average,
            ),
            demographic_analysis=_demographic_analysis(configuration),
            conclusions=conclusions,
            recommendations=recommendations,
            limitations=limitations,
            sources=_sources(configuration.language, source_name, result.get("year")),
            charts=charts[:8],
            table_rows=_table_rows(ranking, selected, result, indicator),
            timings={
                "query_seconds": round(dataset.query_seconds, 4),
                "build_seconds": round(time.perf_counter() - started, 4),
            },
        )
        return content


def _ranking_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    dataframe = pd.DataFrame(rows)
    if dataframe.empty or "value" not in dataframe:
        return pd.DataFrame(columns=["country", "iso", "value", "position"])
    dataframe = dataframe.copy()
    dataframe["iso"] = [
        normalize_country_code(iso, country)
        for iso, country in zip(
            dataframe.get("iso", pd.Series(index=dataframe.index, dtype=object)),
            dataframe.get("country", pd.Series(index=dataframe.index, dtype=object)),
            strict=True,
        )
    ]
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    dataframe = dataframe.dropna(subset=["value"]).sort_values(
        ["value", "country"], ascending=[False, True]
    )
    dataframe["position"] = range(1, len(dataframe) + 1)
    return dataframe.reset_index(drop=True)


def _primary_row(
    dataframe: pd.DataFrame,
    primary_country: str,
) -> dict[str, Any] | None:
    if dataframe.empty:
        return None
    code = normalize_country_code(primary_country)
    if not code:
        return None
    matches = dataframe[dataframe["iso"] == code]
    return cast(dict[str, Any], matches.iloc[0].to_dict()) if not matches.empty else None


def _country_names(dataframe: pd.DataFrame, selected: list[str]) -> list[str]:
    if not selected:
        return []
    names = {str(row.iso): str(row.country or row.iso) for row in dataframe.itertuples()}
    return [names.get(normalize_country_code(code), code) for code in selected]


def _metrics(
    dataframe: pd.DataFrame,
    primary: dict[str, Any] | None,
    eu_average: float | None,
    *,
    language: str,
) -> list[ReportMetric]:
    if dataframe.empty or eu_average is None:
        return []
    items = [
        ReportMetric(
            "eu_average",
            "European average" if language == "en" else "Media europea",
            f"{eu_average:.1f} %",
            eu_average,
            "%",
        ),
        ReportMetric(
            "countries",
            "Countries with data" if language == "en" else "Países con datos",
            str(len(dataframe)),
            float(len(dataframe)),
            "",
        ),
        ReportMetric(
            "highest",
            "Highest value" if language == "en" else "Valor más alto",
            f"{dataframe.iloc[0]['country']} - {dataframe.iloc[0]['value']:.1f} %",
            float(dataframe.iloc[0]["value"]),
            "%",
        ),
    ]
    if primary is not None:
        value = float(primary["value"])
        difference = value - eu_average
        relative = (difference / eu_average * 100) if eu_average else None
        items.extend(
            [
                ReportMetric(
                    "country_value",
                    "Main country" if language == "en" else "País principal",
                    f"{primary['country']} - {value:.1f} %",
                    value,
                    "%",
                ),
                ReportMetric(
                    "difference",
                    "Difference from EU average"
                    if language == "en"
                    else "Diferencia con la media UE",
                    f"{difference:+.1f} pp",
                    difference,
                    "pp",
                ),
                ReportMetric(
                    "relative_difference",
                    "Relative difference" if language == "en" else "Diferencia relativa",
                    f"{relative:+.1f} %" if relative is not None else "N/A",
                    relative,
                    "%",
                ),
                ReportMetric(
                    "rank",
                    "European position" if language == "en" else "Posición europea",
                    f"{int(primary['position'])}/{len(dataframe)}",
                    float(primary["position"]),
                    "",
                ),
            ]
        )
    return items


def _charts(
    config: ReportConfiguration,
    result: dict[str, Any],
    ranking: pd.DataFrame,
    selected: list[str],
    country_names: list[str],
    indicator: str,
) -> list[ReportChart]:
    rows = cast(list[dict[str, Any]], ranking.to_dict("records"))
    source = str(result.get("source") or "")
    detail = list(result.get("detail_data") or result.get("data") or [])
    language = config.language
    builders: list[tuple[str, str, Any]] = [
        (
            "ranking",
            _t(language, "Ranking comparativo", "Comparative ranking"),
            lambda: build_comparative_ranking_chart(rows, selected, language),
        ),
        (
            "average",
            _t(language, "Comparación con la media europea", "European average comparison"),
            lambda: build_eu_average_comparison_chart(rows, selected, language),
        ),
    ]
    if source == "FRA":
        builders.extend(
            [
                (
                    "countries",
                    _t(language, "Comparación de respuestas", "Response comparison"),
                    lambda: build_response_country_comparison_chart(
                        detail,
                        selected,
                        language,
                        indicator=indicator,
                        year=result.get("year"),
                    ),
                ),
                (
                    "responses",
                    _t(language, "Detalle de respuestas", "Response detail"),
                    lambda: build_fra_response_comparison_chart(
                        detail,
                        selected_countries=selected,
                        language=language,
                    ),
                ),
            ]
        )
    else:
        builders.extend(
            [
                (
                    "responses",
                    _t(language, "Criterios jurídicos", "Legal criteria"),
                    lambda: build_ilga_response_details_chart(
                        detail,
                        selected,
                        language=language,
                        indicator=indicator,
                        year=result.get("year"),
                    ),
                ),
                (
                    "temporal",
                    _t(language, "Evolución temporal", "Temporal evolution"),
                    lambda: build_temporal_evolution_chart(
                        list(result.get("history") or []),
                        selected,
                        language,
                        visible_countries=selected or None,
                    ),
                ),
            ]
        )
    if "radar" in config.charts:
        radar_payload = result.get("experience_legal_radar") or {}
        radar_country = selected[0] if selected else _first_comparable_radar_country(radar_payload)
        radar, compatible, _metadata, _interpretation = build_experience_legal_radar(
            radar_payload,
            radar_country,
            language,
        )
        if compatible:
            builders.append(
                (
                    "radar",
                    _t(
                        language,
                        "Experiencia real y protección legal",
                        "Real-life experience and legal protection",
                    ),
                    lambda radar=radar: radar,
                )
            )

    charts: list[ReportChart] = []
    for key, title, factory in builders:
        if key not in config.charts:
            continue
        figure = factory()
        if not figure.data:
            continue
        prepare_figure_for_export(
            figure,
            chart_type=key,
            chart_title=title,
            indicator=indicator,
            countries=country_names,
            year=result.get("year"),
            source=source,
            filters=_filter_labels(config),
            language=language,
        )
        charts.append(ReportChart(key, title, figure, source))
    return charts


def _executive_summary(
    config: ReportConfiguration,
    *,
    indicator: str,
    primary_name: str,
    primary_value: float | None,
    eu_average: float | None,
) -> list[str]:
    language = config.language
    year = str(config.year or "")
    if primary_value is None or eu_average is None or not primary_name:
        return [
            _t(
                language,
                f"El informe analiza {indicator} en el ámbito europeo para {year}.",
                f"This report analyses {indicator} across Europe for {year}.",
            )
        ]
    difference = primary_value - eu_average
    direction = (
        _t(language, "por encima", "above")
        if difference >= 0
        else _t(language, "por debajo", "below")
    )
    if language == "en":
        sentence = (
            f"In {primary_name}, the value for {indicator} is {primary_value:.1f} %. "
            f"This is {abs(difference):.1f} percentage points {direction} the European "
            f"average in {year}."
        )
    else:
        sentence = (
            f"En {primary_name}, el valor de {indicator} es {primary_value:.1f} %. "
            f"Este resultado se sitúa {abs(difference):.1f} puntos porcentuales "
            f"{direction} de la media europea en {year}."
        )
    return [sentence]


def _conclusions(
    config: ReportConfiguration,
    *,
    indicator: str,
    primary_name: str,
    primary_value: float | None,
    eu_average: float | None,
) -> list[str]:
    if primary_value is None or eu_average is None:
        return [
            _t(
                config.language,
                "No hay datos suficientes para formular una conclusión nacional comparativa.",
                "There is insufficient data for a comparative national conclusion.",
            )
        ]
    difference = primary_value - eu_average
    polarity = indicator_direction(indicator)
    if abs(difference) < 2:
        assessment = _t(
            config.language,
            "El resultado es próximo a la media europea.",
            "The result is close to the European average.",
        )
    elif polarity == "negative":
        assessment = _t(
            config.language,
            "El valor requiere especial atención de RRHH."
            if difference > 0
            else "El valor es más favorable que la referencia europea.",
            "The value requires particular HR attention."
            if difference > 0
            else "The value is more favourable than the European benchmark.",
        )
    elif polarity == "positive":
        assessment = _t(
            config.language,
            "El valor requiere especial atención de RRHH."
            if difference < 0
            else "El valor es más favorable que la referencia europea.",
            "The value requires particular HR attention."
            if difference < 0
            else "The value is more favourable than the European benchmark.",
        )
    else:
        assessment = _t(
            config.language,
            "La diferencia describe una brecha comparativa, no una relación causal.",
            "The difference describes a comparative gap, not a causal relationship.",
        )
    return [f"{primary_name}: {assessment}"]


def _methodology(
    language: str,
    source: str,
    result: dict[str, Any],
) -> list[str]:
    if source == "FRA":
        return [
            _t(
                language,
                "Los valores FRA proceden de respuestas agregadas de personas encuestadas. Se excluyen los países sin datos del cálculo de la media.",
                "FRA values come from aggregated survey responses. Countries without data are excluded from the average.",
            ),
            _t(
                language,
                "Las diferencias se expresan en puntos porcentuales; no implican causalidad ni representan datos internos de la organización.",
                "Differences are expressed in percentage points; they do not imply causality or represent internal organisation data.",
            ),
        ]
    return [
        _t(
            language,
            "La puntuación ILGA-Europe resume leyes y políticas nacionales. No mide por sí sola la experiencia individual en el trabajo.",
            "The ILGA-Europe score summarises national laws and policies. It does not by itself measure individual workplace experience.",
        )
    ]


def _workplace_analysis(
    config: ReportConfiguration,
    indicator: str,
    primary_name: str,
    primary_value: float | None,
    eu_average: float | None,
) -> list[str]:
    if not is_hr_relevant_indicator(indicator):
        return []
    if primary_value is None or eu_average is None:
        return [
            _t(
                config.language,
                "El indicador seleccionado es relevante para RRHH, pero no hay un valor nacional suficiente para compararlo con la referencia europea.",
                "The selected indicator is relevant to HR, but there is no sufficient national value for comparison with the European benchmark.",
            )
        ]
    difference = primary_value - eu_average
    return [
        _t(
            config.language,
            (
                f"El análisis del entorno laboral sitúa a {primary_name} en "
                f"{primary_value:.1f} %, con una diferencia de {difference:+.1f} "
                "puntos porcentuales frente a la media europea."
            ),
            (
                f"The workplace analysis places {primary_name} at "
                f"{primary_value:.1f} %, a difference of {difference:+.1f} "
                "percentage points from the European average."
            ),
        )
    ]


def _demographic_analysis(
    config: ReportConfiguration,
) -> list[str]:
    active = [
        f"{name}: {value}"
        for name, value in (
            (config.filter_a_name, config.filter_a_value),
            (config.filter_b_name, config.filter_b_value),
        )
        if name != "All" or value != "All"
    ]
    if config.source != "fra" or not active:
        return []
    scope = "; ".join(active)
    return [
        _t(
            config.language,
            (
                f"Los resultados se han calculado para la segmentación {scope}. "
                "La comparación describe este grupo agregado y no identifica a personas."
            ),
            (
                f"Results were calculated for the segmentation {scope}. "
                "The comparison describes this aggregated group and does not identify individuals."
            ),
        )
    ]


def _limitations(
    config: ReportConfiguration,
    indicator: str,
    result: dict[str, Any],
) -> list[str]:
    items = [
        _t(
            config.language,
            "Los resultados son agregados y no deben utilizarse para identificar personas o inferir situaciones individuales.",
            "Results are aggregated and must not be used to identify people or infer individual circumstances.",
        )
    ]
    if not is_hr_relevant_indicator(indicator):
        items.append(
            _t(
                config.language,
                "El indicador seleccionado no se ha clasificado como directamente laboral; las recomendaciones mostradas son generales.",
                "The selected indicator was not classified as directly workplace-related; recommendations shown are general.",
            )
        )
    missing = sum(1 for row in result.get("ranking") or [] if row.get("value") is None)
    if missing:
        country_label = (
            ("country" if missing == 1 else "countries")
            if config.language == "en"
            else ("país" if missing == 1 else "países")
        )
        items.append(
            _t(
                config.language,
                f"{missing} {country_label} no dispone de valor para la selección y se excluye de los cálculos."
                if missing == 1
                else f"{missing} {country_label} no disponen de valor para la selección y se excluyen de los cálculos.",
                f"{missing} {country_label} has no value for this selection and is excluded from calculations."
                if missing == 1
                else f"{missing} {country_label} have no value for this selection and are excluded from calculations.",
            )
        )
    return items


def _sources(language: str, source: str, year: Any) -> list[str]:
    clean_year = int(year) if isinstance(year, int | float) else None
    source_keys: list[str] = []
    source_value = str(source or "").casefold()
    if "fra" in source_value:
        source_keys.append("fra")
    if "ilga" in source_value or "rainbow map" in source_value:
        source_keys.append("ilga")
    if "felgtbi" in source_value or "felgtb" in source_value:
        source_keys.append("felgtbi")
    return attribution_for_sources(
        source_keys or ["fra"],
        language=language,
        year=clean_year,
    )


def _table_rows(
    ranking: pd.DataFrame,
    selected: list[str],
    result: dict[str, Any],
    indicator: str,
) -> list[dict[str, Any]]:
    if ranking.empty:
        return []
    table = ranking
    if selected:
        table = ranking[ranking["iso"].isin(selected)]
    eu_average = float(ranking["value"].mean())
    rows: list[dict[str, Any]] = []
    for row in table.itertuples():
        value = _number(getattr(row, "value", None))
        position = _number(getattr(row, "position", None))
        if value is None or position is None:
            continue
        rows.append(
            {
                "country": str(getattr(row, "country", "")),
                "value": round(value, 2),
                "position": int(position),
                "difference": round(value - eu_average, 2),
                "year": result.get("year"),
                "indicator": indicator,
            }
        )
    return rows


def _filter_labels(config: ReportConfiguration) -> list[str]:
    labels = []
    if config.answer:
        labels.append(config.answer)
    for name, value in (
        (config.filter_a_name, config.filter_a_value),
        (config.filter_b_name, config.filter_b_value),
    ):
        if name != "All" or value != "All":
            labels.append(f"{name}: {value}")
    return labels


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None


def _t(language: str, es: str, en: str) -> str:
    return en if language == "en" else es
