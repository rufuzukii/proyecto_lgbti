from __future__ import annotations

import math
import time
from typing import Any, cast

import pandas as pd

from app.analytics.statistics_charts import (
    build_combined_quadrant_chart,
    build_combined_scatter,
    build_comparative_ranking_chart,
    build_eu_average_comparison_chart,
    build_experience_legal_radar,
    build_fra_response_comparison_chart,
    build_ilga_response_details_chart,
    build_ranking_position_gap_chart,
    build_response_country_comparison_chart,
    build_temporal_evolution_chart,
)
from app.analytics.statistics_exports import prepare_figure_for_export
from app.analytics.statistics_normalizers import normalize_country_code
from app.reports.hr_reporting import hr_report_focus_label, hr_report_objective
from app.reports.models import (
    ReportChart,
    ReportConfiguration,
    ReportContent,
    ReportDataset,
    ReportMetric,
)
from app.reports.recommendations import (
    build_recommendations,
    indicator_semantics,
    is_hr_relevant_indicator,
    result_level,
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


class ReportBuilder:
    """Build deterministic HR-oriented content from one analytical payload."""

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
        eu_median = float(ranking["value"].median()) if not ranking.empty else None
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
        metrics.extend(_combined_report_metrics(configuration, result))
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
            benchmark=eu_median,
        )
        recommendations = build_recommendations(
            indicator=indicator,
            country_value=primary_value,
            benchmark=eu_median,
            language=configuration.language,
            answer=configuration.answer,
            source=configuration.source,
        )
        conclusions = _conclusions(
            configuration,
            indicator=indicator,
            primary_name=primary_name,
            primary_value=primary_value,
            benchmark=eu_median,
            result=result,
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
            sources=_sources(
                configuration.language,
                source_name,
                result.get("year"),
                combined_analysis=dict(result.get("combined_analysis") or {}),
            ),
            charts=charts[:8],
            table_rows=_table_rows(ranking, selected, result, indicator),
            timings={
                "query_seconds": round(dataset.query_seconds, 4),
                "build_seconds": round(time.perf_counter() - started, 4),
            },
            focus_label=hr_report_focus_label(configuration.language),
            objective_label=hr_report_objective(configuration.objective).label(
                configuration.language
            ),
        )
        return content


# Compatibility alias for integrations that imported the original builder.
HRReportBuilder = ReportBuilder


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
            "eu_median",
            "European median" if language == "en" else "Mediana europea",
            f"{float(dataframe['value'].median()):.1f} %",
            float(dataframe["value"].median()),
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
    if config.source in {"fra", "combined"}:
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
    if config.source == "ilga":
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
    if config.source == "combined":
        combined = dict(result.get("combined_analysis") or {})
        combined_rows = list(combined.get("rows") or [])
        combined_metrics_payload = dict(combined.get("metrics") or {})
        semantics = str((combined.get("semantics") or {}).get("direction") or "unknown")
        segmentation = " · ".join(_filter_labels(config))
        builders.extend(
            [
                (
                    "scatter",
                    _t(language, "Experiencia social y protección legal", "Social experience and legal protection"),
                    lambda: build_combined_scatter(
                        combined_rows,
                        language,
                        selected,
                        indicator=indicator,
                        answer=config.answer,
                        fra_year=combined.get("fra_year"),
                        ilga_year=combined.get("ilga_year"),
                        metrics=combined_metrics_payload,
                        segmentation=segmentation,
                    ),
                ),
                (
                    "quadrants",
                    _t(language, "Cuadrantes de experiencia y protección", "Experience and protection quadrants"),
                    lambda: build_combined_quadrant_chart(
                        combined_rows,
                        language,
                        selected,
                        semantic_direction=semantics,
                        answer=config.answer,
                        metrics=combined_metrics_payload,
                        segmentation=segmentation,
                    ),
                ),
                (
                    "ranking_gap",
                    _t(language, "Diferencia de posiciones entre rankings", "Difference in ranking positions"),
                    lambda: build_ranking_position_gap_chart(
                        dict(combined.get("ranking_gap") or result.get("ranking_gap") or {}),
                        language,
                        answer=config.answer,
                    ),
                ),
            ]
        )

    if config.source != "combined" and "radar" in config.charts:
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
    combined_support = dict(
        (result.get("combined_analysis") or {}).get("supported_analyses") or {}
    )
    for key, title, factory in builders:
        if key not in config.charts:
            continue
        if key in {"quadrants", "ranking_gap"} and not combined_support.get(key, False):
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
        what_shows, how_to_read, observation = _chart_explanation(
            key, config, result, indicator
        )
        charts.append(
            ReportChart(
                key,
                title,
                figure,
                source,
                what_shows=what_shows,
                how_to_read=how_to_read,
                observation=observation,
            )
        )
    return charts


def _executive_summary(
    config: ReportConfiguration,
    *,
    indicator: str,
    primary_name: str,
    primary_value: float | None,
    benchmark: float | None,
) -> list[str]:
    language = config.language
    year = str(config.year or "")
    if primary_value is None or benchmark is None or not primary_name:
        return [
            _t(
                language,
                f"El informe analiza {indicator} en el ámbito europeo para {year}.",
                f"This report analyses {indicator} across Europe for {year}.",
            )
        ]
    difference = primary_value - benchmark
    direction = (
        _t(language, "por encima", "above")
        if difference >= 0
        else _t(language, "por debajo", "below")
    )
    if language == "en":
        sentence = (
            f"In {primary_name}, the value for {indicator} is {primary_value:.1f} %. "
            f"This is {abs(difference):.1f} percentage points {direction} the European "
            f"median in {year}."
        )
    else:
        sentence = (
            f"En {primary_name}, el valor de {indicator} es {primary_value:.1f} %. "
            f"Este resultado se sitúa {abs(difference):.1f} puntos porcentuales "
            f"{direction} de la mediana de los países analizados en {year}."
        )
    return [sentence]


def _conclusions(
    config: ReportConfiguration,
    *,
    indicator: str,
    primary_name: str,
    primary_value: float | None,
    benchmark: float | None,
    result: dict[str, Any],
) -> list[str]:
    combined = result.get("combined_analysis") or {}
    if config.source == "combined":
        return _combined_conclusions(config, combined)
    if primary_value is None or benchmark is None:
        return []
    difference = primary_value - benchmark
    semantics = indicator_semantics(indicator, config.answer, source=config.source)
    level = result_level(
        semantics=semantics,
        country_value=primary_value,
        benchmark=benchmark,
        threshold=2.0,
    )
    if abs(difference) < 2:
        assessment = _t(
            config.language,
            "El resultado es próximo a la media europea.",
            "The result is close to the European average.",
        )
    elif level in {"adverse", "favourable"}:
        assessment = _t(
            config.language,
            "El resultado es relativamente desfavorable para la respuesta seleccionada."
            if level == "adverse"
            else "El resultado es relativamente favorable para la respuesta seleccionada.",
            "The result is relatively unfavourable for the selected answer."
            if level == "adverse"
            else "The result is relatively favourable for the selected answer.",
        )
    else:
        assessment = _t(
            config.language,
            "La diferencia describe la posición respecto al valor central. No permite afirmar si el resultado es mejor o peor.",
            "The difference describes the position relative to the midpoint. It does not establish whether the result is better or worse.",
        )
    return [f"{primary_name}: {assessment}"]


def _methodology(
    language: str,
    source: str,
    result: dict[str, Any],
) -> list[str]:
    source_key = str(source or "").casefold()
    if "fra" in source_key and "ilga" in source_key:
        combined = result.get("combined_analysis") or {}
        return [
            _t(
                language,
                f"El análisis cruza la encuesta social de {combined.get('fra_year') or '—'} con la puntuación legal de {combined.get('ilga_year') or '—'}, utilizando únicamente países con ambos valores.",
                f"The analysis links the {combined.get('fra_year') or '—'} social survey with the {combined.get('ilga_year') or '—'} legal score, using only countries with both values.",
            ),
            _t(
                language,
                "Los valores ausentes no se sustituyen por cero. La media y la mediana solo incluyen observaciones válidas con los mismos filtros.",
                "Missing values are not replaced with zero. The mean and median include only valid observations under the same filters.",
            ),
            _t(
                language,
                "La relación observada resume si ambas medidas tienden a variar juntas. No demuestra que una sea la causa de la otra.",
                "The observed relationship summarises whether both measures tend to vary together. It does not prove that one causes the other.",
            ),
        ]
    if "fra" in source_key:
        return [
            _t(
                language,
                "Los valores FRA proceden de respuestas agregadas de personas encuestadas. Se excluyen los países sin datos del cálculo de la media.",
                "FRA values come from aggregated survey responses. Countries without data are excluded from the average.",
            ),
            _t(
                language,
                "Las diferencias se expresan en puntos porcentuales. No implican causalidad ni representan datos internos de la organización.",
                "Differences are expressed in percentage points. They do not imply causality or represent internal organisation data.",
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
    if config.source not in {"fra", "combined"} or not active:
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
    if config.source == "combined":
        combined = result.get("combined_analysis") or {}
        fra_year = combined.get("fra_year")
        ilga_year = combined.get("ilga_year")
        items.append(
            _t(
                config.language,
                "Que dos valores aparezcan relacionados no significa que uno sea la causa del otro. La realidad de cada país depende de factores sociales, económicos, culturales, institucionales y metodológicos no controlados aquí.",
                "A relationship between two values does not mean that one causes the other. Each country's reality depends on social, economic, cultural, institutional and methodological factors not controlled here.",
            )
        )
        if fra_year and ilga_year and fra_year != ilga_year:
            items.append(
                _t(
                    config.language,
                    f"La encuesta social ({fra_year}) y la puntuación legal ({ilga_year}) corresponden a años diferentes. La comparación es exploratoria y no simultánea.",
                    f"The social survey ({fra_year}) and legal score ({ilga_year}) are from different years. The comparison is exploratory rather than simultaneous.",
                )
            )
    if not is_hr_relevant_indicator(indicator):
        items.append(
            _t(
                config.language,
                "El indicador seleccionado no se ha clasificado como directamente laboral. Las recomendaciones mostradas son generales.",
                "The selected indicator was not classified as directly workplace-related. The recommendations shown are general.",
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


def _sources(
    language: str,
    source: str,
    year: Any,
    *,
    combined_analysis: dict[str, Any] | None = None,
) -> list[str]:
    clean_year = int(year) if isinstance(year, int | float) else None
    source_keys: list[str] = []
    source_value = str(source or "").casefold()
    if "fra" in source_value:
        source_keys.append("fra")
    if "ilga" in source_value or "rainbow map" in source_value:
        source_keys.append("ilga")
    if "felgtbi" in source_value or "felgtb" in source_value:
        source_keys.append("felgtbi")
    if "fra" in source_keys and "ilga" in source_keys:
        combined = combined_analysis or {}
        sources = attribution_for_sources(
            ["fra"],
            language=language,
            year=_safe_int(combined.get("fra_year")) or clean_year,
        )
        sources.extend(
            attribution_for_sources(
                ["ilga"],
                language=language,
                year=_safe_int(combined.get("ilga_year")) or clean_year,
            )
        )
        if "felgtbi" in source_keys:
            sources.extend(attribution_for_sources(["felgtbi"], language=language))
        return list(dict.fromkeys(sources))
    return attribution_for_sources(source_keys or ["fra"], language=language, year=clean_year)


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


def _combined_report_metrics(
    config: ReportConfiguration,
    result: dict[str, Any],
) -> list[ReportMetric]:
    if config.source != "combined":
        return []
    metrics = dict((result.get("combined_analysis") or {}).get("metrics") or {})
    n = int(metrics.get("n") or 0)
    correlation = _number(metrics.get("spearman"))
    items = [
        ReportMetric(
            "combined_countries",
            _t(config.language, "Países con ambos datos", "Countries with both values"),
            str(n),
            float(n),
        )
    ]
    if correlation is not None:
        items.append(
            ReportMetric(
                "observed_relationship",
                _t(config.language, "Relación observada", "Observed relationship"),
                f"{correlation:+.2f}",
                correlation,
            )
        )
    return items


def _combined_conclusions(
    config: ReportConfiguration,
    combined: dict[str, Any],
) -> list[str]:
    metrics = dict(combined.get("metrics") or {})
    n = int(metrics.get("n") or 0)
    correlation = _number(metrics.get("spearman"))
    if n < 5 or correlation is None:
        return []
    strengths_es = {
        "very_weak": "muy débil", "weak": "débil", "moderate": "moderada",
        "strong": "fuerte", "very_strong": "muy fuerte",
    }
    strengths_en = {
        "very_weak": "very weak", "weak": "weak", "moderate": "moderate",
        "strong": "strong", "very_strong": "very strong",
    }
    strength_key = str(metrics.get("strength") or "unavailable")
    strength = (strengths_en if config.language == "en" else strengths_es).get(
        strength_key, _t(config.language, "no concluyente", "inconclusive")
    )
    if abs(correlation) < 0.20:
        relationship = _t(
            config.language,
            "No se observa una relación clara entre ambas medidas en los países disponibles.",
            "No clear relationship is observed between the two measures in the available countries.",
        )
    else:
        direction = _t(
            config.language,
            "positiva" if correlation > 0 else "negativa",
            "positive" if correlation > 0 else "negative",
        )
        relationship = _t(
            config.language,
            f"En los {n} países comparables se observa una asociación {direction} {strength}: ambas medidas tienden a {'aumentar o disminuir juntas' if correlation > 0 else 'moverse en sentidos opuestos'}.",
            f"Across the {n} comparable countries, a {strength} {direction} association is observed: the measures tend to {'rise or fall together' if correlation > 0 else 'move in opposite directions'}.",
        )
    caution = _t(
        config.language,
        "Esta asociación es descriptiva y no demuestra que la protección legal cause el resultado social.",
        "This association is descriptive and does not prove that legal protection causes the social outcome.",
    )
    if n < 10:
        caution = _t(
            config.language,
            f"{caution} La muestra de {n} países debe leerse como exploratoria.",
            f"{caution} The sample of {n} countries should be read as exploratory.",
        )
    return [relationship, caution]


def _chart_explanation(
    key: str,
    config: ReportConfiguration,
    result: dict[str, Any],
    indicator: str,
) -> tuple[str, str, str]:
    language = config.language
    explanations = {
        "ranking": (
            _t(language, "Ordena los países según el valor del indicador seleccionado.", "Ranks countries by the selected indicator value."),
            _t(language, "Una posición alta solo significa un valor numérico mayor. No implica automáticamente una situación mejor.", "A high position only means a higher numeric value. It is not automatically better."),
        ),
        "average": (
            _t(language, "Compara los países elegidos con la media de los países que tienen un dato válido.", "Compares selected countries with the mean among countries with a valid value."),
            _t(language, "La distancia se expresa en puntos porcentuales cuando el indicador procede de una encuesta.", "Distance is shown in percentage points for survey indicators."),
        ),
        "countries": (
            _t(language, "Muestra cómo se reparte la respuesta seleccionada entre los países.", "Shows how the selected answer varies across countries."),
            _t(language, "Lee siempre el resultado junto con la pregunta y la respuesta elegida.", "Always read the result together with the selected question and answer."),
        ),
        "responses": (
            _t(language, "Detalla las respuestas de encuesta o los criterios legales disponibles.", "Details available survey answers or legal criteria."),
            _t(language, "Los valores ausentes se mantienen como ausencia y no se convierten en cero.", "Missing values remain missing and are not converted to zero."),
        ),
        "temporal": (
            _t(language, "Muestra cómo cambia la puntuación legal a lo largo de los años disponibles.", "Shows how the legal score changes across available years."),
            _t(language, "Compara años con cautela cuando la metodología o la escala hayan cambiado.", "Compare years cautiously when methodology or scale has changed."),
        ),
        "scatter": (
            _t(language, "Cada punto representa un país y cruza su resultado social con su protección legal.", "Each point is a country, linking its social result and legal protection."),
            _t(language, "Más a la derecha significa mayor puntuación legal. Más arriba significa mayor porcentaje para la respuesta elegida.", "Further right means a higher legal score. Further up means a higher percentage for the selected answer."),
        ),
        "quadrants": (
            _t(language, "Sitúa cada país respecto a la mediana legal y la mediana social del conjunto comparable.", "Places each country relative to the legal and social medians of the comparable set."),
            _t(language, "Las zonas permiten detectar combinaciones distintas sin restar dos escalas que miden aspectos diferentes.", "The areas reveal different combinations without subtracting scales that measure different things."),
        ),
        "ranking_gap": (
            _t(language, "Compara la posición legal y la posición social de cada país.", "Compares each country's legal and social positions."),
            _t(language, "Una separación grande muestra posiciones relativas distintas, pero no demuestra causalidad.", "A large gap shows different relative positions but does not establish causality."),
        ),
    }
    what_shows, how_to_read = explanations.get(
        key,
        (
            _t(language, f"Presenta información sobre {indicator}.", f"Presents information about {indicator}."),
            _t(language, "Interprétalo junto con la fuente y los filtros indicados.", "Read it together with the stated source and filters."),
        ),
    )
    combined_notes = (
        _combined_conclusions(config, dict(result.get("combined_analysis") or {}))
        if key in {"scatter", "quadrants", "ranking_gap"}
        else []
    )
    observation = (
        combined_notes[0]
        if combined_notes
        else _t(
            language,
            "La gráfica resume los datos válidos de la selección actual.",
            "The chart summarises valid data for the current selection.",
        )
    )
    return what_shows, how_to_read, observation


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except TypeError, ValueError:
        return None
    return number if math.isfinite(number) else None


def _safe_int(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _t(language: str, es: str, en: str) -> str:
    return en if language == "en" else es
