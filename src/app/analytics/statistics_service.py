from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import logging
import re
import time
from typing import Any

import pandas as pd

from app.cache import cache
from app.analytics.percentage_display import coerce_percentage
from app.analytics.repository import (
    ANALYTICS_CACHE_TIMEOUT_SECONDS,
    get_fra_indicator_answers,
    get_ilga_document_by_year,
    get_ilga_history_documents,
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
        percentage = coerce_percentage(
            _answer_percentage_value(answer),
            logger=logger,
            context={
                "collection": "Indicator_fra",
                "document_code": document.get("code"),
                "country": answer.get("country"),
                "country_code": answer.get("country_code"),
                "answer": answer.get("answer"),
                "field": "answers.percentage",
            },
        )
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
        disabled = (
            not _all_filter_type_available(dataframe, group)
            if filter_type == "All"
            else filter_type not in present
        )
        options.append(display_option(filter_type, filter_type, disabled=disabled))
    return options


def build_fra_default_filter_types(document: dict[str, Any] | None) -> tuple[str, str]:
    dataframe = fra_document_to_dataframe(document)
    if dataframe.empty:
        return "All", "All"
    if _has_exact_filter_labels(dataframe, "All", "All"):
        return "All", "All"

    for filter_type in FRA_FILTER_GROUP_B[1:]:
        if _has_rows_with_filter_types(dataframe, filter_a_type=None, filter_b_type=filter_type):
            return "All", filter_type
    for filter_type in FRA_FILTER_GROUP_A[1:]:
        if _has_rows_with_filter_types(dataframe, filter_a_type=filter_type, filter_b_type=None):
            return filter_type, "All"

    present_a = [filter_type for filter_type in FRA_FILTER_GROUP_A[1:] if filter_type in _present_filter_types(dataframe)]
    present_b = [filter_type for filter_type in FRA_FILTER_GROUP_B[1:] if filter_type in _present_filter_types(dataframe)]
    for filter_a_type in present_a:
        for filter_b_type in present_b:
            if _has_rows_with_filter_types(dataframe, filter_a_type=filter_a_type, filter_b_type=filter_b_type):
                return filter_a_type, filter_b_type
    return "All", "All"


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


def build_fra_control_payload(document: dict[str, Any] | None) -> dict[str, Any]:
    """Derive all FRA control options without constructing a pandas DataFrame."""
    if not isinstance(document, dict):
        return {"answers": [], "segmentations": [], "values": {}}

    answer_values: dict[str, str] = {}
    filter_values: dict[str, dict[str, str]] = {}
    for answer in document.get("answers", []):
        if not isinstance(answer, dict):
            continue
        answer_value = repair_text_encoding(answer.get("answer")).strip()
        country = repair_text_encoding(answer.get("country")).strip()
        if not answer_value or not country:
            continue
        answer_values.setdefault(answer_value, normalize_filter_value(answer_value))
        for raw_type, raw_value in _filters_to_dict(answer.get("filters")).items():
            filter_type = normalize_filter_type(raw_type)
            if not filter_type or filter_type == "All":
                continue
            filter_values.setdefault(filter_type, {}).setdefault(
                str(raw_value), normalize_filter_value(raw_value)
            )

    answers = [
        {"label": label, "value": value}
        for value, label in sorted(answer_values.items(), key=lambda item: item[1].casefold())
    ]
    ordered_types = ["All", *FRA_FILTER_GROUP_A[1:], *FRA_FILTER_GROUP_B[1:]]
    segmentations = [
        display_option(filter_type, filter_type)
        for filter_type in ordered_types
        if filter_type == "All" or filter_type in filter_values
    ]
    values: dict[str, list[dict[str, Any]]] = {"All": [display_option("All", "All")]}
    for filter_type in ordered_types[1:]:
        found = filter_values.get(filter_type)
        if not found:
            continue
        values[filter_type] = [
            {"label": label, "value": raw_value}
            for raw_value, label in sorted(found.items(), key=lambda item: item[1].casefold())
        ]
    return {"answers": answers, "segmentations": segmentations, "values": values}


def get_fra_control_payload(code: str) -> dict[str, Any]:
    clean_code = str(code or "").strip()
    if not clean_code:
        return {"code": "", "category": "", "answers": [], "segmentations": [], "values": {}}
    cache_key = f"fra-controls-v2:{clean_code}"
    cached = _server_cache_get(cache_key)
    if isinstance(cached, dict):
        return deepcopy(cached)

    document = get_fra_indicator_answers(clean_code)
    payload = build_fra_control_payload(document)
    payload["code"] = clean_code
    payload["category"] = str((document or {}).get("category") or "").strip()
    if isinstance(document, dict):
        _server_cache_set(cache_key, deepcopy(payload))
    return payload


def _fra_control_payload_from_dataframe(dataframe: pd.DataFrame) -> dict[str, Any]:
    if dataframe.empty:
        return {"answers": [], "segmentations": [], "values": {}}

    answers = [
        {"label": label, "value": value}
        for value, label in sorted(
            {
                str(row.answer): normalize_filter_value(row.answer)
                for row in dataframe[["answer"]].drop_duplicates().itertuples()
            }.items(),
            key=lambda item: item[1],
        )
    ]
    present = _present_filter_types(dataframe)
    ordered_types = ["All", *FRA_FILTER_GROUP_A[1:], *FRA_FILTER_GROUP_B[1:]]
    segmentations = [
        display_option(filter_type, filter_type)
        for filter_type in ordered_types
        if filter_type == "All" or filter_type in present
    ]
    values: dict[str, list[dict[str, Any]]] = {"All": [display_option("All", "All")]}
    records = dataframe[["filters"]].to_dict("records")
    for filter_type in ordered_types[1:]:
        if filter_type not in present:
            continue
        found: dict[str, str] = {}
        for row in records:
            filters = row.get("filters")
            if not isinstance(filters, dict):
                continue
            for raw_type, raw_value in filters.items():
                if normalize_filter_type(raw_type) == filter_type:
                    found.setdefault(str(raw_value), normalize_filter_value(raw_value))
        values[filter_type] = [
            {"label": label, "value": raw_value}
            for raw_value, label in sorted(found.items(), key=lambda item: item[1].casefold())
        ]
    return {"answers": answers, "segmentations": segmentations, "values": values}


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

    cache_key = _fra_statistics_cache_key(query)
    cached = _server_cache_get(cache_key)
    if isinstance(cached, dict):
        logger.debug(
            "fra_statistics_cache_hit",
            extra={"question_code": query.question_code, "cache_key": cache_key},
        )
        return deepcopy(cached)

    started_at = time.perf_counter()
    result = _build_fra_statistics(query)
    if result.get("status") == "ok":
        _server_cache_set(cache_key, deepcopy(result))
    logger.debug(
        "fra_statistics_computed",
        extra={
            "question_code": query.question_code,
            "processing_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "cached": False,
        },
    )
    return result


def _build_fra_statistics(query: FraStatisticsQuery) -> dict[str, Any]:
    clean_code = str(query.question_code or "").strip()
    dataframe = _fra_dataframe_for_code(clean_code)

    if dataframe.empty:
        return _status("empty", NO_DATA_MESSAGE)
    source_dataframe = dataframe
    effective_answer = query.answer or _default_fra_answer_from_dataframe(dataframe)
    dataframe = filter_fra_dataframe(dataframe, query, effective_answer=effective_answer)
    effective_filter_scope = None
    if dataframe.empty:
        effective_filter_scope = _available_filter_label_scope(dataframe=source_dataframe, answer=effective_answer)
        if effective_filter_scope is not None:
            dataframe = filter_fra_dataframe(
                source_dataframe,
                query,
                effective_answer=effective_answer,
                filter_scope=effective_filter_scope,
            )
    if dataframe.empty:
        return _status("empty", NO_DATA_MESSAGE)
    detail_dataframe = filter_fra_comparison_dataframe(source_dataframe, query)

    ranking = aggregate_fra_data(dataframe, ["country", "iso"], "percentage", "mean")
    ranking = ranking.rename(columns={"percentage": "value"})
    ranking = _complete_country_ranking(
        ranking,
        source_dataframe,
        countries=query.countries,
    )
    question = next(
        (
            str(value)
            for value in source_dataframe["question"].dropna().unique().tolist()
            if str(value).strip()
        ),
        clean_code,
    )
    return {
        "status": "ok",
        "message": "",
        "source": "FRA",
        "year": query.year,
        "category": query.category,
        "indicator": question,
        "indicator_code": clean_code,
        "answer": effective_answer,
        "data": dataframe.to_dict("records"),
        "detail_data": detail_dataframe.to_dict("records"),
        "available_countries": sorted(
            value for value in source_dataframe["iso"].dropna().astype(str).unique().tolist() if value
        ),
        "ranking": ranking.to_dict("records"),
        "metrics": _metrics_from_values(ranking["value"].tolist()),
        "methodology": (
            "FRA refleja respuestas de personas encuestadas. "
            "La puntuación ILGA mide leyes y políticas. "
            "Las fuentes no son directamente equivalentes."
        ),
    }


def _fra_dataframe_for_code(code: str) -> pd.DataFrame:
    if not code:
        return _empty_fra_dataframe()
    cache_key = f"fra-normalized-frame-v2:{code}"
    cached = _server_cache_get(cache_key)
    if isinstance(cached, pd.DataFrame):
        return cached.copy(deep=True)

    dataframe = fra_document_to_dataframe(get_fra_indicator_answers(code))
    if not dataframe.empty:
        _server_cache_set(cache_key, dataframe.copy(deep=True))
    return dataframe


def _fra_statistics_cache_key(query: FraStatisticsQuery) -> str:
    identity = {
        "year": query.year,
        "countries": sorted(str(country) for country in query.countries),
        "category": query.category,
        "question_code": query.question_code,
        "answer": query.answer,
        "filter_a_name": query.filter_a_name,
        "filter_a_value": query.filter_a_value,
        "filter_b_name": query.filter_b_name,
        "filter_b_value": query.filter_b_value,
        "group_by": list(query.group_by),
        "mode": query.mode,
    }
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"fra-statistics-v4:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def _server_cache_get(key: str) -> Any:
    if not getattr(cache, "app", None):
        return None
    try:
        return cache.get(key)
    except Exception:
        logger.debug("statistics_cache_read_failed", extra={"cache_key": key}, exc_info=True)
        return None


def _server_cache_set(key: str, value: Any) -> None:
    if not getattr(cache, "app", None):
        return
    try:
        cache.set(key, value, timeout=ANALYTICS_CACHE_TIMEOUT_SECONDS)
    except Exception:
        logger.debug("statistics_cache_write_failed", extra={"cache_key": key}, exc_info=True)


def get_ilga_statistics(
    query: IlgaStatisticsQuery,
    *,
    include_history: bool = True,
) -> dict[str, Any]:
    cache_key = _ilga_statistics_cache_key(query, include_history=include_history)
    cached = _server_cache_get(cache_key)
    if isinstance(cached, dict):
        return deepcopy(cached)

    result = _build_ilga_statistics(query, include_history=include_history)
    if result.get("status") == "ok":
        _server_cache_set(cache_key, deepcopy(result))
    return result


def _build_ilga_statistics(
    query: IlgaStatisticsQuery,
    *,
    include_history: bool,
) -> dict[str, Any]:
    document = get_ilga_document_by_year(query.year)
    source_dataframe = ilga_document_to_dataframe(document)
    if source_dataframe.empty:
        return _status("empty", "No hay datos ILGA-Europe para el año seleccionado.")

    dataframe = filter_ilga_dataframe(source_dataframe, query)
    if dataframe.empty:
        return _status("empty", "No hay datos ILGA-Europe para la combinación seleccionada.")

    if query.category and query.category != "Ranking total":
        ranking = _ilga_category_scores(dataframe)
    else:
        ranking = dataframe[dataframe["category"] == "Ranking total"][["country", "iso", "ranking"]]
        ranking = ranking.rename(columns={"ranking": "value"}).drop_duplicates()
    ranking = _complete_country_ranking(
        ranking,
        source_dataframe,
        countries=query.countries,
    )
    effective_year = _safe_int(document.get("year")) if isinstance(document, dict) else query.year
    return {
        "status": "ok",
        "message": "",
        "source": "ILGA-Europe",
        "year": effective_year,
        "category": query.category,
        "indicator": query.criterion or query.category or "Ranking total",
        "criterion": query.criterion,
        "data": dataframe.to_dict("records"),
        "ranking": ranking.to_dict("records"),
        "available_countries": sorted(
            value for value in source_dataframe["iso"].dropna().astype(str).unique().tolist() if value
        ),
        "history": get_ilga_history_rows(query.category, query.criterion) if include_history else [],
        "metrics": _metrics_from_values(ranking["value"].tolist()),
        "methodology": (
            "ILGA-Europe Rainbow Map mide leyes, políticas y protecciones jurídicas. "
            ""
        ),
    }


def _ilga_statistics_cache_key(
    query: IlgaStatisticsQuery,
    *,
    include_history: bool,
) -> str:
    identity = {
        "year": query.year,
        "countries": sorted(str(country) for country in query.countries),
        "category": query.category,
        "criterion": query.criterion,
        "mode": query.mode,
        "include_history": include_history,
    }
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"ilga-statistics-v3:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def filter_fra_dataframe(
    dataframe: pd.DataFrame,
    query: FraStatisticsQuery,
    *,
    effective_answer: str | None = None,
    filter_scope: tuple[str, str] | None = None,
) -> pd.DataFrame:
    filtered = dataframe.copy()
    if query.year is not None and "year" in filtered:
        filtered = filtered[(filtered["year"].isna()) | (filtered["year"] == query.year)]
    if query.countries:
        selected = {normalize_country_code(country) or str(country) for country in query.countries}
        filtered = filtered[filtered["iso"].isin(selected) | filtered["country"].isin(selected)]
    selected_answer = effective_answer if effective_answer is not None else query.answer
    if selected_answer:
        filtered = filtered[filtered["answer"] == selected_answer]
    filtered = _apply_exact_filter_scope(filtered, query, filter_scope=filter_scope)
    return filtered


def filter_fra_detail_dataframe(
    dataframe: pd.DataFrame,
    query: FraStatisticsQuery,
    *,
    filter_scope: tuple[str, str] | None = None,
) -> pd.DataFrame:
    filtered = dataframe.copy()
    if query.year is not None and "year" in filtered:
        filtered = filtered[(filtered["year"].isna()) | (filtered["year"] == query.year)]
    filtered = _apply_exact_filter_scope(filtered, query, filter_scope=filter_scope)
    return filtered


def filter_fra_comparison_dataframe(
    dataframe: pd.DataFrame,
    query: FraStatisticsQuery,
) -> pd.DataFrame:
    """Return every response using a comparable scope for each response label.

    Some FRA questions store their aggregate response labels under different
    technical filter scopes. Selecting one response must not hide the others.
    """
    filtered = dataframe.copy()
    if query.year is not None and "year" in filtered:
        filtered = filtered[(filtered["year"].isna()) | (filtered["year"] == query.year)]
    if filtered.empty:
        return filtered

    requested_a = _selected_filter_label(query.filter_a_name, query.filter_a_value)
    requested_b = _selected_filter_label(query.filter_b_name, query.filter_b_value)
    if (requested_a, requested_b) != ("All", "All"):
        return _apply_exact_filter_scope(filtered, query)

    groups: list[pd.DataFrame] = []
    for answer in filtered["answer"].dropna().drop_duplicates().tolist():
        answer_rows = filtered[filtered["answer"] == answer]
        scope = _available_filter_label_scope(dataframe=answer_rows, answer=str(answer))
        if scope is not None:
            answer_rows = _apply_exact_filter_scope(answer_rows, query, filter_scope=scope)
        groups.append(answer_rows)
    return pd.concat(groups, ignore_index=True) if groups else filtered.iloc[0:0]


def get_ilga_history_rows(
    category: str | None,
    criterion: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document in get_ilga_history_documents():
        dataframe = ilga_document_to_dataframe(document)
        if dataframe.empty:
            continue
        query = IlgaStatisticsQuery(category=category, criterion=criterion)
        filtered = filter_ilga_dataframe(dataframe, query)
        if category and category != "Ranking total":
            ranking = _ilga_category_scores(filtered)
        else:
            ranking = filtered[filtered["category"] == "Ranking total"][["country", "iso", "ranking"]]
            ranking = ranking.rename(columns={"ranking": "value"}).drop_duplicates()
        if ranking.empty:
            continue
        ranking["year"] = _safe_int(document.get("year"))
        rows.extend(
            {str(key): value for key, value in record.items()}
            for record in ranking[["year", "country", "iso", "value"]].to_dict("records")
        )
    return rows


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
    numeric_dataframe = dataframe.copy()
    numeric_dataframe[value_column] = pd.to_numeric(numeric_dataframe[value_column], errors="coerce")
    grouped = numeric_dataframe.groupby(group_by, dropna=False)[value_column]
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


def _apply_exact_filter_scope(
    dataframe: pd.DataFrame,
    query: FraStatisticsQuery,
    *,
    filter_scope: tuple[str, str] | None = None,
) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe
    if "filter_a" not in dataframe.columns or "filter_b" not in dataframe.columns:
        return dataframe

    expected_a, expected_b = filter_scope or (
        _selected_filter_label(query.filter_a_name, query.filter_a_value),
        _selected_filter_label(query.filter_b_name, query.filter_b_value),
    )
    return dataframe[
        dataframe["filter_a"].apply(lambda value: _same_filter_label(value, expected_a))
        & dataframe["filter_b"].apply(lambda value: _same_filter_label(value, expected_b))
    ]


def _selected_filter_label(filter_name: str | None, filter_value: str | None) -> str:
    clean_name = normalize_filter_type(filter_name)
    clean_value = repair_text_encoding(filter_value).strip()
    if not clean_name or clean_name == "All" or not clean_value or clean_value == "All":
        return "All"
    return normalize_filter_value(clean_value)


def _same_filter_label(value: Any, expected: str) -> bool:
    return normalize_filter_value(repair_text_encoding(value).strip()) == expected


def _available_filter_label_scope(
    *,
    dataframe: pd.DataFrame,
    answer: str | None,
) -> tuple[str, str] | None:
    if dataframe.empty or "filter_a" not in dataframe or "filter_b" not in dataframe:
        return None
    candidates = dataframe.copy()
    if answer:
        candidates = candidates[candidates["answer"] == answer]
    if candidates.empty:
        return None

    valid_candidates = candidates[candidates["percentage"].notna()] if "percentage" in candidates else candidates
    if valid_candidates.empty:
        valid_candidates = candidates

    if _has_exact_filter_labels(valid_candidates, "All", "All"):
        return "All", "All"

    all_a = valid_candidates[valid_candidates["filter_a"].apply(lambda value: _same_filter_label(value, "All"))]
    non_all_b_values = _sorted_non_all_filter_values(all_a, "filter_b")
    if non_all_b_values:
        return "All", non_all_b_values[0]

    all_b = valid_candidates[valid_candidates["filter_b"].apply(lambda value: _same_filter_label(value, "All"))]
    non_all_a_values = _sorted_non_all_filter_values(all_b, "filter_a")
    if non_all_a_values:
        return non_all_a_values[0], "All"

    pairs = sorted(
        {
            (normalize_filter_value(row.filter_a), normalize_filter_value(row.filter_b))
            for row in valid_candidates[["filter_a", "filter_b"]].itertuples()
            if not _same_filter_label(row.filter_a, "All") and not _same_filter_label(row.filter_b, "All")
        },
        key=lambda item: (item[0].casefold(), item[1].casefold()),
    )
    return pairs[0] if pairs else None


def _sorted_non_all_filter_values(dataframe: pd.DataFrame, column: str) -> list[str]:
    if dataframe.empty or column not in dataframe:
        return []
    values = {
        normalize_filter_value(value)
        for value in dataframe[column].dropna().tolist()
        if not _same_filter_label(value, "All")
    }
    return sorted(values, key=str.casefold)


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


def _all_filter_type_available(dataframe: pd.DataFrame, group: str) -> bool:
    if dataframe.empty or "filters" not in dataframe:
        return True
    allowed = FRA_FILTER_GROUP_A if group == "a" else FRA_FILTER_GROUP_B
    return any(
        not _row_has_group_filter(filters, allowed)
        for filters in dataframe["filters"]
    )


def _has_exact_filter_labels(dataframe: pd.DataFrame, filter_a: str, filter_b: str) -> bool:
    if dataframe.empty or "filter_a" not in dataframe or "filter_b" not in dataframe:
        return False
    return bool(
        (
            dataframe["filter_a"].apply(lambda value: _same_filter_label(value, filter_a))
            & dataframe["filter_b"].apply(lambda value: _same_filter_label(value, filter_b))
        ).any()
    )


def _has_rows_with_filter_types(
    dataframe: pd.DataFrame,
    *,
    filter_a_type: str | None,
    filter_b_type: str | None,
) -> bool:
    if dataframe.empty or "filters" not in dataframe:
        return False
    return any(
        _row_filter_scope_matches(filters, filter_a_type=filter_a_type, filter_b_type=filter_b_type)
        for filters in dataframe["filters"]
    )


def _row_filter_scope_matches(
    filters: Any,
    *,
    filter_a_type: str | None,
    filter_b_type: str | None,
) -> bool:
    if not isinstance(filters, dict):
        filters = {"All": "All"}
    if filter_a_type is None and _row_has_group_filter(filters, FRA_FILTER_GROUP_A):
        return False
    if filter_b_type is None and _row_has_group_filter(filters, FRA_FILTER_GROUP_B):
        return False
    if filter_a_type is not None and not _row_has_filter_type(filters, filter_a_type):
        return False
    if filter_b_type is not None and not _row_has_filter_type(filters, filter_b_type):
        return False
    return True


def _row_has_group_filter(filters: Any, allowed: tuple[str, ...]) -> bool:
    if not isinstance(filters, dict):
        return False
    allowed_keys = {normalize_filter_type(filter_type) for filter_type in allowed if filter_type != "All"}
    return any(normalize_filter_type(key) in allowed_keys for key in filters)


def _row_has_filter_type(filters: Any, filter_type: str) -> bool:
    if not isinstance(filters, dict):
        return False
    expected = normalize_filter_type(filter_type)
    return any(normalize_filter_type(key) == expected for key in filters)


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


def _complete_country_ranking(
    ranking: pd.DataFrame,
    source_dataframe: pd.DataFrame,
    *,
    countries: list[str] | None = None,
) -> pd.DataFrame:
    """Enrich one European result set once, retaining countries without values."""
    universe = source_dataframe[["country", "iso"]].copy()
    universe["iso"] = universe["iso"].fillna("").astype(str).str.upper()
    universe = universe[
        universe["country"].notna()
        & universe["country"].astype(str).str.strip().ne("")
        & universe["iso"].ne("EU27")
    ].drop_duplicates("iso", keep="first")
    if countries:
        selected = {
            normalize_country_code(country) or str(country)
            for country in countries
        }
        universe = universe[
            universe["iso"].isin(selected) | universe["country"].isin(selected)
        ]

    values = ranking[["iso", "value"]].copy() if not ranking.empty else pd.DataFrame(
        columns=["iso", "value"]
    )
    values["iso"] = values["iso"].fillna("").astype(str).str.upper()
    values["value"] = pd.to_numeric(values["value"], errors="coerce")
    values = values.groupby("iso", as_index=False, dropna=False)["value"].mean()

    completed = universe.merge(values, on="iso", how="left", validate="one_to_one")
    numeric_values = completed["value"].dropna()
    european_mean = float(numeric_values.mean()) if not numeric_values.empty else None
    completed["position"] = completed["value"].rank(
        method="min",
        ascending=False,
        na_option="keep",
    )
    completed["difference"] = (
        completed["value"] - european_mean if european_mean is not None else None
    )
    completed["absolute_difference"] = (
        completed["difference"].abs() if european_mean is not None else None
    )
    completed["percentage_difference"] = (
        completed["difference"] / european_mean * 100
        if european_mean not in (None, 0)
        else None
    )
    completed["european_mean"] = european_mean
    completed = completed.sort_values(
        ["value", "country"],
        ascending=[False, True],
        na_position="last",
    )
    for column in (
        "value",
        "position",
        "difference",
        "absolute_difference",
        "percentage_difference",
        "european_mean",
    ):
        completed[column] = completed[column].astype(object).where(
            pd.notna(completed[column]),
            None,
        )
    completed["position"] = pd.Series(
        [
            int(value) if value is not None and pd.notna(value) else None
            for value in completed["position"].tolist()
        ],
        index=completed.index,
        dtype=object,
    )
    return completed.reset_index(drop=True)


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
    return coerce_percentage(value)


def _answer_percentage_value(answer: dict[str, Any]) -> Any:
    if "percentage" in answer:
        return answer.get("percentage")
    return answer.get("value")


def _default_fra_answer_from_dataframe(dataframe: pd.DataFrame) -> str | None:
    if dataframe.empty or "answer" not in dataframe:
        return None
    values = {
        str(row.answer): normalize_filter_value(row.answer)
        for row in dataframe[["answer"]].drop_duplicates().itertuples()
        if str(row.answer or "").strip()
    }
    if not values:
        return None
    return sorted(values.items(), key=lambda item: item[1])[0][0]


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
