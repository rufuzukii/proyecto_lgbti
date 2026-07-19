from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

from app.analytics.repository import (
    get_fra_indicator_answers,
    get_ilga_document_by_year,
)
from app.analytics.statistics_models import (
    FRA_FILTER_GROUP_A,
    FRA_FILTER_GROUP_B,
    FraStatisticsQuery,
    IlgaStatisticsQuery,
    validate_fra_query,
)
from app.analytics.statistics_normalizers import (
    display_option,
    normalize_country_code,
    normalize_filter_type,
    normalize_filter_value,
    repair_text_encoding,
)

logger = logging.getLogger(__name__)
NO_DATA_MESSAGE = (
    "No hay datos disponibles para esta combinación de país, indicador y filtros. "
    "Prueba a seleccionar All en uno de los grupos o utiliza una segmentación menos específica."
)


def fra_document_to_dataframe(document: dict[str, Any] | None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not isinstance(document, dict):
        return _empty_fra_dataframe()

    for answer in document.get("answers", []):
        if not isinstance(answer, dict):
            continue
        percentage = _safe_float(answer.get("percentage"))
        if percentage is None:
            continue
        country = repair_text_encoding(answer.get("country")).strip()
        answer_value = repair_text_encoding(answer.get("answer")).strip()
        if not country or not answer_value:
            continue
        filters = _filters_to_dict(answer.get("filters"))
        rows.append(
            {
                "source": "FRA",
                "category": repair_text_encoding(document.get("category")).strip(),
                "specific_category": repair_text_encoding(document.get("specific_category")).strip(),
                "question": repair_text_encoding(document.get("question")).strip(),
                "question_code": repair_text_encoding(document.get("code")).strip(),
                "country": country,
                "iso": normalize_country_code(answer.get("country_code"), country),
                "answer": answer_value,
                "answer_label": normalize_filter_value(answer_value),
                "percentage": percentage,
                "year": _extract_year(answer.get("date")),
                "filters": filters,
                "filter_a": _first_matching_filter(filters, FRA_FILTER_GROUP_A),
                "filter_b": _first_matching_filter(filters, FRA_FILTER_GROUP_B),
            }
        )
    return pd.DataFrame(rows) if rows else _empty_fra_dataframe()


def ilga_document_to_dataframe(document: dict[str, Any] | None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not isinstance(document, dict):
        return _empty_ilga_dataframe()

    year = _safe_int(document.get("year"))
    for country in document.get("countries", []):
        if not isinstance(country, dict):
            continue
        ranking = _safe_float(country.get("ranking"))
        if ranking is None:
            continue
        country_name = repair_text_encoding(country.get("country")).strip()
        iso = normalize_country_code(country.get("country_code"), country_name)
        rows.append(
            {
                "source": "ILGA-Europe",
                "year": year,
                "country": country_name,
                "iso": iso,
                "ranking": ranking,
                "category": "Ranking total",
                "criterion": "",
                "criterion_value": None,
                "criterion_weight": None,
            }
        )
        criteria = country.get("criteria")
        if not isinstance(criteria, list):
            continue
        for criterion in criteria:
            if not isinstance(criterion, dict):
                continue
            value = criterion.get("value")
            criterion_value = _safe_float(value)
            rows.append(
                {
                    "source": "ILGA-Europe",
                    "year": year,
                    "country": country_name,
                    "iso": iso,
                    "ranking": float(ranking),
                    "category": repair_text_encoding(criterion.get("category")).strip(),
                    "criterion": repair_text_encoding(criterion.get("indicator")).strip(),
                    "criterion_value": criterion_value,
                    "criterion_weight": criterion.get("weight"),
                }
            )
    return pd.DataFrame(rows) if rows else _empty_ilga_dataframe()


def build_fra_filter_type_options(document: dict[str, Any] | None, group: str) -> list[dict[str, Any]]:
    allowed = FRA_FILTER_GROUP_A if group == "a" else FRA_FILTER_GROUP_B
    dataframe = fra_document_to_dataframe(document)
    present = _present_filter_types(dataframe)
    options = []
    for filter_type in allowed:
        disabled = filter_type != "All" and filter_type not in present
        options.append(display_option(filter_type, filter_type, disabled=disabled))
    return options


def build_fra_filter_value_options(
    document: dict[str, Any] | None,
    filter_type: str | None,
) -> list[dict[str, Any]]:
    clean_type = normalize_filter_type(filter_type)
    if not clean_type or clean_type == "All":
        return [display_option("All", "All")]

    values: dict[str, str] = {}
    for row in fra_document_to_dataframe(document).to_dict("records"):
        filters = row.get("filters")
        if not isinstance(filters, dict):
            continue
        for raw_type, raw_value in filters.items():
            if normalize_filter_type(raw_type) != clean_type:
                continue
            label = normalize_filter_value(raw_value)
            if label:
                values.setdefault(str(raw_value), label)
    return [
        {"label": label, "value": raw_value}
        for raw_value, label in sorted(values.items(), key=lambda item: item[1])
    ] or [display_option("All", "All", disabled=True)]


def build_fra_answer_options(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    dataframe = fra_document_to_dataframe(document)
    if dataframe.empty:
        return []
    values = {
        str(row.answer): normalize_filter_value(row.answer)
        for row in dataframe[["answer"]].drop_duplicates().itertuples()
    }
    return [
        {"label": label, "value": value}
        for value, label in sorted(values.items(), key=lambda item: item[1])
    ]


def build_fra_country_options(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    dataframe = fra_document_to_dataframe(document)
    if dataframe.empty:
        return []
    countries = dataframe[["country", "iso"]].drop_duplicates().sort_values("country")
    return [
        {"label": f"{row.country} ({row.iso})" if row.iso else row.country, "value": row.iso or row.country}
        for row in countries.itertuples()
        if row.country
    ]


def build_ilga_country_options(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    dataframe = ilga_document_to_dataframe(document)
    if dataframe.empty:
        return []
    countries = dataframe[["country", "iso"]].drop_duplicates().sort_values("country")
    return [
        {"label": f"{row.country} ({row.iso})" if row.iso else row.country, "value": row.iso or row.country}
        for row in countries.itertuples()
        if row.country
    ]


def get_fra_statistics(query: FraStatisticsQuery) -> dict[str, Any]:
    validation = validate_fra_query(query)
    if not validation.ok:
        return _status("invalid", validation.message)

    document = get_fra_indicator_answers(query.question_code or "")
    dataframe = fra_document_to_dataframe(document)
    if dataframe.empty:
        return _status("empty", NO_DATA_MESSAGE)
    detail_dataframe = filter_fra_detail_dataframe(dataframe, query)
    dataframe = filter_fra_dataframe(dataframe, query)
    if dataframe.empty:
        return _status("empty", NO_DATA_MESSAGE)

    ranking = aggregate_fra_data(dataframe, ["country", "iso"], "percentage", "mean")
    ranking = ranking.rename(columns={"percentage": "value"}).sort_values("value", ascending=False)
    return {
        "status": "ok",
        "message": "",
        "source": "FRA",
        "data": dataframe.to_dict("records"),
        "detail_data": detail_dataframe.to_dict("records"),
        "ranking": ranking.to_dict("records"),
        "metrics": _metrics_from_values(ranking["value"].tolist()),
        "methodology": (
            "FRA: porcentajes medios de respuestas de personas encuestadas. "
            "La agregación por país usa la media de los valores disponibles para la combinación seleccionada."
        ),
    }


def get_ilga_statistics(query: IlgaStatisticsQuery) -> dict[str, Any]:
    document = get_ilga_document_by_year(query.year)
    dataframe = ilga_document_to_dataframe(document)
    if dataframe.empty:
        return _status("empty", "No hay datos ILGA-Europe para el año seleccionado.")

    dataframe = filter_ilga_dataframe(dataframe, query)
    if dataframe.empty:
        return _status("empty", "No hay datos ILGA-Europe para la combinación seleccionada.")

    if query.category and query.category != "Ranking total":
        ranking = _ilga_category_scores(dataframe)
    else:
        ranking = dataframe[dataframe["category"] == "Ranking total"][["country", "iso", "ranking"]]
        ranking = ranking.rename(columns={"ranking": "value"}).drop_duplicates()
    ranking = ranking.sort_values("value", ascending=False)
    return {
        "status": "ok",
        "message": "",
        "source": "ILGA-Europe",
        "data": dataframe.to_dict("records"),
        "ranking": ranking.to_dict("records"),
        "metrics": _metrics_from_values(ranking["value"].tolist()),
        "methodology": (
            "ILGA-Europe Rainbow Map mide leyes, políticas y protecciones jurídicas. "
            ""
        ),
    }


def filter_fra_dataframe(dataframe: pd.DataFrame, query: FraStatisticsQuery) -> pd.DataFrame:
    filtered = dataframe.copy()
    if query.year is not None and "year" in filtered:
        filtered = filtered[(filtered["year"].isna()) | (filtered["year"] == query.year)]
    if query.countries:
        selected = {normalize_country_code(country) or str(country) for country in query.countries}
        filtered = filtered[filtered["iso"].isin(selected) | filtered["country"].isin(selected)]
    if query.answer:
        filtered = filtered[filtered["answer"] == query.answer]
    filtered = _apply_filter_pair(filtered, query.filter_a_name, query.filter_a_value)
    filtered = _apply_filter_pair(filtered, query.filter_b_name, query.filter_b_value)
    return filtered


def filter_fra_detail_dataframe(dataframe: pd.DataFrame, query: FraStatisticsQuery) -> pd.DataFrame:
    filtered = dataframe.copy()
    if query.year is not None and "year" in filtered:
        filtered = filtered[(filtered["year"].isna()) | (filtered["year"] == query.year)]
    filtered = _apply_filter_pair(filtered, query.filter_a_name, query.filter_a_value)
    filtered = _apply_filter_pair(filtered, query.filter_b_name, query.filter_b_value)
    return filtered


def filter_ilga_dataframe(dataframe: pd.DataFrame, query: IlgaStatisticsQuery) -> pd.DataFrame:
    filtered = dataframe.copy()
    if query.countries:
        selected = {normalize_country_code(country) or str(country) for country in query.countries}
        filtered = filtered[filtered["iso"].isin(selected) | filtered["country"].isin(selected)]
    if query.category and query.category != "Ranking total":
        filtered = filtered[filtered["category"] == query.category]
    if query.criterion:
        filtered = filtered[filtered["criterion"] == query.criterion]
    return filtered


def aggregate_fra_data(
    dataframe: pd.DataFrame,
    group_by: list[str],
    value_column: str,
    aggregation: str = "mean",
) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=[*group_by, value_column])
    if value_column not in dataframe.columns:
        raise ValueError("invalid_value_column")
    if aggregation not in {"mean", "median", "max", "min", "count", "sum"}:
        raise ValueError("invalid_aggregation")
    if aggregation == "sum" and value_column == "percentage":
        raise ValueError("cannot_sum_percentages")
    missing = [column for column in group_by if column not in dataframe.columns]
    if missing:
        raise ValueError("invalid_group_by")
    grouped = dataframe.groupby(group_by, dropna=False)[value_column]
    if aggregation == "mean":
        result = grouped.mean()
    elif aggregation == "median":
        result = grouped.median()
    elif aggregation == "max":
        result = grouped.max()
    elif aggregation == "min":
        result = grouped.min()
    elif aggregation == "count":
        result = grouped.count()
    else:
        result = grouped.sum()
    return result.reset_index()


def classify_external_data_error(payload: Any) -> str:
    if isinstance(payload, dict):
        message = " ".join(str(item) for item in payload.get("message", []))
        error = " ".join(str(item) for item in payload.get("error", []))
        if "No data for this query" in message:
            logger.warning("fra_query_without_data", extra={"technical_error": error})
            return "empty"
        if "500" in error:
            logger.error("fra_internal_error", extra={"technical_error": error})
            return "internal_error"
    return "invalid_response"


def _apply_filter_pair(
    dataframe: pd.DataFrame,
    filter_name: str | None,
    filter_value: str | None,
) -> pd.DataFrame:
    clean_name = normalize_filter_type(filter_name)
    clean_value = repair_text_encoding(filter_value).strip()
    if not clean_name or clean_name == "All" or not clean_value or clean_value == "All":
        return dataframe
    return dataframe[
        dataframe["filters"].apply(
            lambda filters: _filter_matches(filters, clean_name, clean_value)
        )
    ]


def _filter_matches(filters: Any, filter_name: str, filter_value: str) -> bool:
    if not isinstance(filters, dict):
        return False
    expected_label = normalize_filter_value(filter_value)
    for raw_type, raw_value in filters.items():
        if normalize_filter_type(raw_type) != filter_name:
            continue
        if repair_text_encoding(raw_value).strip() == filter_value or normalize_filter_value(raw_value) == expected_label:
            return True
    return False


def _filters_to_dict(filters: Any) -> dict[str, str]:
    if not isinstance(filters, list):
        return {"All": "All"}
    output: dict[str, str] = {}
    for item in filters:
        if not isinstance(item, dict):
            continue
        filter_type = normalize_filter_type(item.get("type"))
        filter_value = repair_text_encoding(item.get("value")).strip()
        if filter_type and filter_value:
            output[filter_type] = filter_value
    return output or {"All": "All"}


def _present_filter_types(dataframe: pd.DataFrame) -> set[str]:
    present: set[str] = set()
    if dataframe.empty:
        return present
    for filters in dataframe["filters"]:
        if isinstance(filters, dict):
            present.update(normalize_filter_type(key) for key in filters)
    return present


def _first_matching_filter(filters: dict[str, str], allowed: tuple[str, ...]) -> str:
    for filter_type, filter_value in filters.items():
        clean_type = normalize_filter_type(filter_type)
        if clean_type in allowed and clean_type != "All" and filter_value != "All":
            return normalize_filter_value(filter_value)
    return "All"


def _ilga_category_scores(dataframe: pd.DataFrame) -> pd.DataFrame:
    criteria = dataframe[dataframe["category"] != "Ranking total"].copy()
    criteria = criteria[criteria["criterion_value"].notna()]
    if criteria.empty:
        return pd.DataFrame(columns=["country", "iso", "value"])
    criteria["weighted_value"] = criteria.apply(
        lambda row: float(row["criterion_value"]) * float(row["criterion_weight"] or 1),
        axis=1,
    )
    criteria["weight"] = criteria["criterion_weight"].apply(lambda value: float(value or 1))
    grouped = criteria.groupby(["country", "iso"], dropna=False)[["weighted_value", "weight"]].sum()
    grouped["value"] = 100 * grouped["weighted_value"] / grouped["weight"]
    return grouped.reset_index()[["country", "iso", "value"]]


def _metrics_from_values(values: list[float]) -> dict[str, Any]:
    series = pd.Series([value for value in values if pd.notna(value)], dtype="float")
    if series.empty:
        return {}
    return {
        "mean": round(float(series.mean()), 2),
        "median": round(float(series.median()), 2),
        "max": round(float(series.max()), 2),
        "min": round(float(series.min()), 2),
        "countries": int(series.count()),
    }


def _extract_year(value: Any) -> int | None:
    text = str(value or "")
    match = re.search(r"(?<!\d)(20\d{2})(?!\d)", text)
    return int(match.group(1)) if match else None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace("%", "").replace(",", ".")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _status(status: str, message: str) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "data": [],
        "ranking": [],
        "metrics": {},
        "methodology": "",
    }


def _empty_fra_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "source",
            "category",
            "specific_category",
            "question",
            "question_code",
            "country",
            "iso",
            "answer",
            "answer_label",
            "percentage",
            "year",
            "filters",
            "filter_a",
            "filter_b",
        ]
    )


def _empty_ilga_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "source",
            "year",
            "country",
            "iso",
            "ranking",
            "category",
            "criterion",
            "criterion_value",
            "criterion_weight",
        ]
    )
