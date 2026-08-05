from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from copy import deepcopy
from typing import Any

import pandas as pd

from app.analytics.legal_criteria import get_criterion_status
from app.analytics.percentage_display import (
    coerce_percentage,
    normalize_percentage_values,
)
from app.analytics.repository import (
    ANALYTICS_CACHE_TIMEOUT_SECONDS,
    get_fra_indicator_answers,
    get_fra_indicator_documents,
    get_ilga_analysis_rows,
    get_ilga_document_by_year,
)
from app.analytics.statistics_models import (
    FRA_FILTER_GROUP_A,
    FRA_FILTER_GROUP_B,
    ExperienceLegalRadarQuery,
    FraStatisticsQuery,
    IlgaStatisticsQuery,
    validate_fra_query,
)
from app.analytics.statistics_normalizers import (
    display_option,
    normalize_country_code,
    normalize_filter_type,
    normalize_filter_value,
    normalize_text_key,
    repair_text_encoding,
)
from app.cache import cache

logger = logging.getLogger(__name__)
NO_DATA_MESSAGE = (
    "No hay datos disponibles para esta combinación de país, indicador y filtros. "
    "Prueba a seleccionar All en uno de los grupos o utiliza una segmentación menos específica."
)

RADAR_MAPPING_VERSION = "fra-ilga-v1"
ILGA_RESPONSE_ORDER = {
    "not_met": 0,
    "partially_met": 1,
    "fully_met": 2,
    "not_available": 3,
    "overall_score": 4,
}
RADAR_DIMENSION_MAPPING: dict[str, dict[str, Any]] = {
    "equal_treatment": {
        "label_es": "Igualdad y no discriminación",
        "label_en": "Equality and non-discrimination",
        "fra": ({"code": "D1_1", "answer": "Yes", "invert": True},),
        "ilga": {"category": "Equality & non-discrimination", "prefixes": ()},
    },
    "goods_services": {
        "label_es": "Bienes y servicios",
        "label_en": "Goods and services",
        "fra": ({"code": "D1_2_f", "answer": "Yes", "invert": True},),
        "ilga": {
            "category": "Equality & non-discrimination",
            "prefixes": ("Goods & services",),
        },
    },
    "education": {
        "label_es": "Educación",
        "label_en": "Education",
        "fra": (
            {"code": "C9_E", "answer": "Never", "invert": False},
            {"code": "C9_C", "answer": "Never", "invert": False},
        ),
        "ilga": {
            "category": "Equality & non-discrimination",
            "prefixes": ("Education",),
        },
    },
    "health": {
        "label_es": "Salud",
        "label_en": "Health",
        "fra": ({"code": "G16", "answer": "Very good", "invert": False},),
        "ilga": {
            "category": "Equality & non-discrimination",
            "prefixes": ("Health",),
        },
    },
    "equality_bodies": {
        "label_es": "Acceso a organismos de igualdad",
        "label_en": "Access to equality bodies",
        "fra": ({"code": "C20_Any_EB", "answer": "Yes", "invert": False},),
        "ilga": {
            "category": "Equality & non-discrimination",
            "prefixes": ("Equality body mandate",),
        },
    },
}


def fra_document_to_dataframe(document: dict[str, Any] | None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not isinstance(document, dict):
        return _empty_fra_dataframe()

    answers = [answer for answer in document.get("answers", []) if isinstance(answer, dict)]
    raw_percentages = [_answer_percentage_value(answer) for answer in answers]
    normalized_percentages = normalize_percentage_values(
        raw_percentages,
        logger=logger,
        context={
            "collection": "Indicator_fra",
            "indicator": document.get("code"),
            "field": "answers.percentage",
            "countries": sorted(
                {
                    str(answer.get("country_code") or answer.get("country") or "").strip()
                    for answer in answers
                    if str(answer.get("country_code") or answer.get("country") or "").strip()
                }
            ),
            "years": sorted(
                {
                    year
                    for answer in answers
                    if (year := _extract_year(answer.get("date"))) is not None
                }
            ),
        },
    )
    for answer, percentage in zip(answers, normalized_percentages, strict=True):
        country = repair_text_encoding(answer.get("country")).strip()
        answer_value = repair_text_encoding(answer.get("answer")).strip()
        if not country or not answer_value:
            continue
        filters = _filters_to_dict(answer.get("filters"))
        rows.append(
            {
                "source": "FRA",
                "category": repair_text_encoding(document.get("category")).strip(),
                "specific_category": repair_text_encoding(
                    document.get("specific_category")
                ).strip(),
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


def ilga_analysis_rows_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Normalize projected ILGA country rows into one canonical analysis frame.

    Duplicate resolution is deterministic: the newest Mongo document id wins;
    exact duplicates inside that document collapse to one row; conflicting
    values inside the winning document become missing instead of being averaged.
    """
    normalized: list[dict[str, Any]] = []
    discarded: dict[str, int] = {
        "invalid_year": 0,
        "missing_country": 0,
        "invalid_ranking": 0,
        "invalid_criterion_value": 0,
        "invalid_weight": 0,
    }
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            continue
        year = _safe_int(raw_row.get("year"))
        if year is None:
            discarded["invalid_year"] += 1
            continue
        country_name = repair_text_encoding(raw_row.get("country_name")).strip()
        country_code = normalize_country_code(raw_row.get("country_code"), country_name)
        if not country_code or not country_name or country_code == "EU27":
            discarded["missing_country"] += 1
            continue
        document_id = str(raw_row.get("document_id") or "")
        country_index = _safe_int(raw_row.get("country_index")) or 0
        ranking = coerce_percentage(raw_row.get("ranking"))
        if ranking is None and raw_row.get("ranking") is not None:
            discarded["invalid_ranking"] += 1
        normalized.append(
            {
                "document_id": document_id,
                "country_index": country_index,
                "criterion_index": -1,
                "source": "ILGA-Europe",
                "year": year,
                "country": country_name,
                "country_name": country_name,
                "iso": country_code,
                "country_code": country_code,
                "ranking": ranking,
                "category": "Ranking total",
                "criterion": "",
                "indicator_id": "Ranking total",
                "criterion_value": None,
                "criterion_weight": None,
                "value": ranking,
                "response": "overall_score",
                "response_order": ILGA_RESPONSE_ORDER["overall_score"],
            }
        )
        criteria = raw_row.get("criteria")
        if not isinstance(criteria, list):
            continue
        for criterion_index, criterion in enumerate(criteria):
            if not isinstance(criterion, dict):
                continue
            category = repair_text_encoding(criterion.get("category")).strip()
            indicator = repair_text_encoding(criterion.get("indicator")).strip()
            if not category or not indicator:
                continue
            raw_value = _safe_unit_score(criterion.get("value"))
            if raw_value is None and criterion.get("value") is not None:
                discarded["invalid_criterion_value"] += 1
            weight = _safe_positive_float(criterion.get("weight"))
            if weight is None and criterion.get("weight") is not None:
                discarded["invalid_weight"] += 1
            response = get_criterion_status(raw_value, 1, "en")["id"]
            normalized.append(
                {
                    "document_id": document_id,
                    "country_index": country_index,
                    "criterion_index": criterion_index,
                    "source": "ILGA-Europe",
                    "year": year,
                    "country": country_name,
                    "country_name": country_name,
                    "iso": country_code,
                    "country_code": country_code,
                    "ranking": ranking,
                    "category": category,
                    "criterion": indicator,
                    "indicator_id": indicator,
                    "criterion_value": raw_value,
                    "criterion_weight": weight,
                    "value": raw_value * 100 if raw_value is not None else None,
                    "response": response,
                    "response_order": ILGA_RESPONSE_ORDER[response],
                }
            )
    if not normalized:
        return _empty_ilga_analysis_dataframe()

    dataframe = pd.DataFrame(normalized)
    resolved_rows: list[dict[str, Any]] = []
    duplicate_groups = 0
    conflicting_groups = 0
    group_columns = ["year", "country_code", "indicator_id", "category"]
    for _key, group in dataframe.groupby(group_columns, sort=False, dropna=False):
        latest_document = max(group["document_id"].astype(str).tolist(), default="")
        candidates = group[group["document_id"].astype(str).eq(latest_document)].sort_values(
            ["country_index", "criterion_index"], kind="stable"
        )
        duplicate_groups += int(len(group) > 1)
        numeric_values = {
            float(value)
            for value in candidates["value"].tolist()
            if value is not None and pd.notna(value)
        }
        chosen = candidates.iloc[0].to_dict()
        if len(numeric_values) > 1:
            conflicting_groups += 1
            chosen["value"] = None
            chosen["criterion_value"] = None
            chosen["response"] = "not_available"
            chosen["response_order"] = ILGA_RESPONSE_ORDER["not_available"]
        resolved_rows.append(chosen)

    resolved = pd.DataFrame(resolved_rows)
    latest_names = (
        resolved.sort_values(["year", "document_id", "country_index"], kind="stable")
        .groupby("country_code", sort=False)
        .tail(1)
        .set_index("country_code")["country_name"]
        .to_dict()
    )
    resolved["country_name"] = resolved["country_code"].map(latest_names)
    resolved["country"] = resolved["country_name"]
    discarded = {key: value for key, value in discarded.items() if value}
    if discarded or duplicate_groups or conflicting_groups:
        logger.warning(
            "ilga_analysis_quality discarded=%r duplicate_groups=%d conflicting_groups=%d",
            discarded,
            duplicate_groups,
            conflicting_groups,
            extra={
                "discarded": discarded,
                "duplicate_group_count": duplicate_groups,
                "conflicting_group_count": conflicting_groups,
            },
        )
    return resolved[_empty_ilga_analysis_dataframe().columns.tolist()].reset_index(drop=True)


def build_fra_filter_type_options(
    document: dict[str, Any] | None, group: str
) -> list[dict[str, Any]]:
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

    present_a = [
        filter_type
        for filter_type in FRA_FILTER_GROUP_A[1:]
        if filter_type in _present_filter_types(dataframe)
    ]
    present_b = [
        filter_type
        for filter_type in FRA_FILTER_GROUP_B[1:]
        if filter_type in _present_filter_types(dataframe)
    ]
    for filter_a_type in present_a:
        for filter_b_type in present_b:
            if _has_rows_with_filter_types(
                dataframe, filter_a_type=filter_a_type, filter_b_type=filter_b_type
            ):
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
        {
            "label": f"{row.country} ({row.iso})" if row.iso else row.country,
            "value": row.iso or row.country,
        }
        for row in countries.itertuples()
        if row.country
    ]


def build_ilga_country_options(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    dataframe = ilga_document_to_dataframe(document)
    if dataframe.empty:
        return []
    countries = dataframe[["country", "iso"]].drop_duplicates().sort_values("country")
    return [
        {
            "label": f"{row.country} ({row.iso})" if row.iso else row.country,
            "value": row.iso or row.country,
        }
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
    dataframe = _fra_dataframe_for_code(clean_code, query.category)

    if dataframe.empty:
        return _status("empty", NO_DATA_MESSAGE)
    source_dataframe = dataframe
    effective_answer = query.answer or _default_fra_answer_from_dataframe(dataframe)
    dataframe = filter_fra_dataframe(dataframe, query, effective_answer=effective_answer)
    effective_filter_scope = None
    if dataframe.empty:
        effective_filter_scope = _available_filter_label_scope(
            dataframe=source_dataframe, answer=effective_answer
        )
        if effective_filter_scope is not None:
            dataframe = filter_fra_dataframe(
                source_dataframe,
                query,
                effective_answer=effective_answer,
                filter_scope=effective_filter_scope,
            )
    if dataframe.empty:
        return _status("empty", NO_DATA_MESSAGE)
    detail_dataframe, country_universe, detail_diagnostics = _prepare_fra_response_details(
        source_dataframe,
        query,
        effective_answer=effective_answer,
    )

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
        "country_universe": country_universe.to_dict("records"),
        "response_details_diagnostics": detail_diagnostics,
        "available_countries": sorted(
            value for value in country_universe["iso"].dropna().astype(str).tolist() if value
        ),
        "ranking": ranking.to_dict("records"),
        "metrics": _metrics_from_values(ranking["value"].tolist()),
        "methodology": (
            "FRA refleja respuestas de personas encuestadas. "
            "La puntuación ILGA mide leyes y políticas. "
            "Las fuentes no son directamente equivalentes."
        ),
    }


def _prepare_fra_response_details(
    source_dataframe: pd.DataFrame,
    query: FraStatisticsQuery,
    *,
    effective_answer: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Build the single canonical dataframe used by response details.

    The country universe is derived from the same year and sociodemographic
    scope as the detail rows. It deliberately ignores map selection and keeps
    rows with a missing percentage so absence is never converted to zero.
    """
    rows_loaded = len(source_dataframe)
    countries_before = int(source_dataframe["iso"].replace("", pd.NA).nunique())
    detail = filter_fra_comparison_dataframe(source_dataframe, query).copy()

    detail["country_code"] = detail["iso"].fillna("").map(normalize_country_code)
    detail["country_name"] = detail["country"].fillna("").astype(str).str.strip()
    detail["response"] = detail["answer"].fillna("").astype(str).str.strip()
    detail["indicator_id"] = detail["question_code"].fillna("").astype(str).str.strip()

    missing_iso_mask = detail["country_code"].eq("")
    missing_country_mask = detail["country_name"].eq("")
    missing_response_mask = detail["response"].eq("")
    aggregate_mask = detail["country_code"].eq("EU27") | detail["country_name"].str.upper().eq(
        "EU27"
    )
    discarded_mask = (
        missing_iso_mask | missing_country_mask | missing_response_mask | aggregate_mask
    )
    discarded_reasons = {
        "missing_country_code": int(missing_iso_mask.sum()),
        "missing_country_name": int(missing_country_mask.sum()),
        "missing_response": int(missing_response_mask.sum()),
        "non_country_aggregate": int(aggregate_mask.sum()),
    }
    detail = detail.loc[~discarded_mask].copy()
    detail["iso"] = detail["country_code"]
    detail["country"] = detail["country_name"]
    detail["answer"] = detail["response"]
    detail["question_code"] = detail["indicator_id"]

    duplicate_mask = detail.duplicated(["country_code", "response"], keep=False)
    duplicate_groups = int(
        detail.loc[duplicate_mask, ["country_code", "response"]].drop_duplicates().shape[0]
    )
    country_universe = _fra_country_universe(detail, None)
    country_codes = set(country_universe["country_code"].astype(str))
    selected_answer_rows = detail[detail["response"].eq(str(effective_answer or ""))]
    countries_with_data = set(
        selected_answer_rows.loc[selected_answer_rows["percentage"].notna(), "country_code"].astype(
            str
        )
    ).intersection(country_codes)
    countries_without_data = country_codes.difference(countries_with_data)
    diagnostics = {
        "records_loaded": rows_loaded,
        "records_after_filters": len(detail),
        "countries_before_filters": countries_before,
        "countries_loaded": len(country_codes),
        "countries_rendered": len(countries_with_data),
        "countries_without_data": len(countries_without_data),
        "duplicate_country_response_groups": duplicate_groups,
        "discarded": discarded_reasons,
    }
    logger.info(
        "response_details countries_loaded=%d countries_rendered=%d countries_without_data=%d",
        diagnostics["countries_loaded"],
        diagnostics["countries_rendered"],
        diagnostics["countries_without_data"],
        extra={"question_code": query.question_code, **diagnostics},
    )
    if any(discarded_reasons.values()) or duplicate_groups:
        logger.debug(
            "response_details_quality discarded=%r duplicate_country_response_groups=%d",
            discarded_reasons,
            duplicate_groups,
            extra={"question_code": query.question_code, **diagnostics},
        )
    return detail, country_universe, diagnostics


def _fra_country_universe(dataframe: pd.DataFrame, year: int | None) -> pd.DataFrame:
    """Canonical country universe represented by the supplied filtered rows."""
    universe = dataframe.copy()
    if year is not None and "year" in universe:
        universe = universe[(universe["year"].isna()) | (universe["year"] == year)]
    universe = universe[
        universe["iso"].astype(str).str.upper().ne("EU27")
        & universe["country"].astype(str).str.upper().ne("EU27")
    ]
    optional_columns = [
        column for column in ("question", "question_code", "indicator_id") if column in universe
    ]
    country_universe = universe[["country", "iso", "year", "source", *optional_columns]].copy()
    country_universe["country_code"] = country_universe["iso"].map(normalize_country_code)
    country_universe["country_name"] = country_universe["country"].astype(str).str.strip()
    return (
        country_universe[
            country_universe["country_code"].ne("") & country_universe["country_name"].ne("")
        ]
        .sort_values(["country_name", "country_code"])
        .drop_duplicates("country_code", keep="first")
        .reset_index(drop=True)
    )


def _fra_dataframe_for_code(code: str, category: str | None = None) -> pd.DataFrame:
    if not code:
        return _empty_fra_dataframe()
    clean_category = str(category or "").strip()
    cache_key = f"fra-normalized-frame-v3:{code}:{clean_category}"
    cached = _server_cache_get(cache_key)
    if isinstance(cached, pd.DataFrame):
        return cached.copy(deep=True)

    document = (
        get_fra_indicator_answers(code, clean_category)
        if clean_category
        else get_fra_indicator_answers(code)
    )
    dataframe = fra_document_to_dataframe(document)
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
    return f"fra-statistics-v5:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


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


def get_experience_legal_radar(
    query: ExperienceLegalRadarQuery,
) -> dict[str, Any]:
    """Build comparable FRA/ILGA dimensions without per-country queries.

    FRA scores use the stored final percentages. Only indicators explicitly
    marked ``invert`` are transformed as ``100 - percentage``. ILGA legal
    scores are the awarded criterion points divided by their available maximum
    weight, expressed on a 0-100 scale.
    """
    identity = {
        "mapping_version": RADAR_MAPPING_VERSION,
        "fra_year": query.fra_year,
        "ilga_year": query.ilga_year,
        "countries": sorted(query.countries),
        "filter_a_name": query.filter_a_name,
        "filter_a_value": query.filter_a_value,
        "filter_b_name": query.filter_b_name,
        "filter_b_value": query.filter_b_value,
    }
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cache_key = f"experience-legal-radar:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"
    cached = _server_cache_get(cache_key)
    if isinstance(cached, dict):
        return deepcopy(cached)

    fra_rows = _experience_radar_rows(query)
    legal_rows, effective_ilga_year = _legal_radar_rows(query)
    if fra_rows.empty or legal_rows.empty:
        result = {
            "status": "empty",
            "rows": [],
            "dimensions": _radar_dimension_metadata(),
            "mapping_version": RADAR_MAPPING_VERSION,
            "fra_year": query.fra_year,
            "ilga_year": effective_ilga_year,
        }
        _server_cache_set(cache_key, deepcopy(result))
        return result

    merged = fra_rows.rename(columns={"country": "experience_country"}).merge(
        legal_rows.rename(columns={"country": "legal_country"}),
        on=["iso", "dimension"],
        how="outer",
        validate="one_to_one",
    )
    merged["country"] = merged["experience_country"].combine_first(merged["legal_country"])
    merged = merged.drop(columns=["experience_country", "legal_country"])
    selected = {
        normalize_country_code(country) or str(country).strip().upper()
        for country in query.countries
    }
    if selected:
        merged = merged[merged["iso"].isin(selected)]
    merged = merged.sort_values(["country", "dimension"], kind="stable")
    serialized_rows = merged.astype(object).where(pd.notna(merged), None).to_dict("records")
    result = {
        "status": "ok" if not merged.empty else "empty",
        "rows": serialized_rows,
        "dimensions": _radar_dimension_metadata(),
        "mapping_version": RADAR_MAPPING_VERSION,
        "fra_year": _effective_dataframe_year(fra_rows, query.fra_year),
        "ilga_year": effective_ilga_year,
        "sources": {"experience": "FRA", "legal": "ILGA-Europe"},
        "methodology": (
            "FRA percentages are used as published; only D1_1 and D1_2_f are explicitly "
            "inverted because a higher discrimination percentage means a worse experience. "
            "ILGA criterion points are normalized against their available weights."
        ),
    }
    _server_cache_set(cache_key, deepcopy(result))
    return result


def _radar_dimension_metadata() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "label_es": str(mapping["label_es"]),
            "label_en": str(mapping["label_en"]),
        }
        for key, mapping in RADAR_DIMENSION_MAPPING.items()
    ]


def _experience_radar_rows(query: ExperienceLegalRadarQuery) -> pd.DataFrame:
    fra_configs = [
        {"dimension": dimension, **indicator}
        for dimension, mapping in RADAR_DIMENSION_MAPPING.items()
        for indicator in mapping["fra"]
    ]
    codes = tuple(config["code"] for config in fra_configs)
    documents = get_fra_indicator_documents(codes)
    frames = [fra_document_to_dataframe(document) for document in documents]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=["iso", "country", "dimension", "experience_score", "fra_year"])

    dataframe = pd.concat(frames, ignore_index=True)
    filter_query = FraStatisticsQuery(
        year=query.fra_year,
        filter_a_name=query.filter_a_name,
        filter_a_value=query.filter_a_value,
        filter_b_name=query.filter_b_name,
        filter_b_value=query.filter_b_value,
    )
    dataframe = filter_fra_comparison_dataframe(dataframe, filter_query)
    if dataframe.empty:
        return pd.DataFrame(columns=["iso", "country", "dimension", "experience_score", "fra_year"])

    config_frame = pd.DataFrame(fra_configs)
    config_frame["answer_key"] = config_frame["answer"].map(normalize_text_key)
    dataframe["answer_key"] = dataframe["answer"].map(normalize_text_key)
    matched = dataframe.merge(
        config_frame[["code", "answer_key", "dimension", "invert"]],
        left_on=["question_code", "answer_key"],
        right_on=["code", "answer_key"],
        how="inner",
        validate="many_to_one",
    )
    matched["percentage"] = pd.to_numeric(matched["percentage"], errors="coerce")
    matched = matched[matched["percentage"].between(0, 100, inclusive="both")]
    matched["experience_score"] = matched["percentage"].where(
        ~matched["invert"], 100 - matched["percentage"]
    )
    matched = matched[
        matched["iso"].astype(str).str.strip().ne("")
        & matched["iso"].astype(str).str.upper().ne("EU27")
    ]
    if matched.empty:
        return pd.DataFrame(columns=["iso", "country", "dimension", "experience_score", "fra_year"])
    return matched.groupby(["iso", "dimension"], as_index=False, dropna=False).agg(
        country=("country", "first"),
        experience_score=("experience_score", "mean"),
        fra_year=("year", "max"),
    )


def _legal_radar_rows(
    query: ExperienceLegalRadarQuery,
) -> tuple[pd.DataFrame, int | None]:
    document = get_ilga_document_by_year(query.ilga_year)
    dataframe = ilga_document_to_dataframe(document)
    effective_year = (
        _safe_int(document.get("year")) if isinstance(document, dict) else query.ilga_year
    )
    if dataframe.empty:
        return (
            pd.DataFrame(columns=["iso", "country", "dimension", "legal_score"]),
            effective_year,
        )

    groups: list[pd.DataFrame] = []
    for dimension, mapping in RADAR_DIMENSION_MAPPING.items():
        legal_mapping = mapping["ilga"]
        rows = dataframe[dataframe["category"].eq(legal_mapping["category"])].copy()
        prefixes = tuple(normalize_text_key(prefix) for prefix in legal_mapping["prefixes"])
        if prefixes:
            criterion_keys = rows["criterion"].map(normalize_text_key)
            rows = rows[criterion_keys.str.startswith(prefixes, na=False)]
        if rows.empty:
            continue
        rows["dimension"] = dimension
        groups.append(rows)
    if not groups:
        return (
            pd.DataFrame(columns=["iso", "country", "dimension", "legal_score"]),
            effective_year,
        )

    criteria = pd.concat(groups, ignore_index=True)
    criteria["criterion_value"] = pd.to_numeric(criteria["criterion_value"], errors="coerce")
    criteria["criterion_weight"] = pd.to_numeric(criteria["criterion_weight"], errors="coerce")
    criteria = criteria[
        criteria["criterion_value"].notna()
        & criteria["criterion_weight"].gt(0)
        & criteria["iso"].astype(str).str.strip().ne("")
    ]
    if criteria.empty:
        return (
            pd.DataFrame(columns=["iso", "country", "dimension", "legal_score"]),
            effective_year,
        )
    criteria["weighted_value"] = criteria["criterion_value"] * criteria["criterion_weight"]
    grouped = criteria.groupby(["iso", "dimension"], as_index=False, dropna=False).agg(
        country=("country", "first"),
        weighted_value=("weighted_value", "sum"),
        available_weight=("criterion_weight", "sum"),
    )
    grouped["legal_score"] = (100 * grouped["weighted_value"] / grouped["available_weight"]).clip(
        0, 100
    )
    return grouped[["iso", "country", "dimension", "legal_score"]], effective_year


def _effective_dataframe_year(dataframe: pd.DataFrame, fallback: int | None) -> int | None:
    years = pd.to_numeric(
        dataframe.get("fra_year", pd.Series(dtype=float)), errors="coerce"
    ).dropna()
    return int(years.max()) if not years.empty else fallback


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
    query_started_at = time.perf_counter()
    raw_rows = get_ilga_analysis_rows(query.category, query.criterion)
    query_ms = (time.perf_counter() - query_started_at) * 1000
    normalization_started_at = time.perf_counter()
    source_dataframe = ilga_analysis_rows_to_dataframe(raw_rows)
    normalization_ms = (time.perf_counter() - normalization_started_at) * 1000
    if source_dataframe.empty:
        return _status("empty", "No hay datos ILGA-Europe para el año seleccionado.")

    available_years = sorted(
        int(year) for year in source_dataframe["year"].dropna().unique().tolist()
    )
    effective_year = query.year if query.year is not None else max(available_years, default=None)
    if effective_year not in available_years:
        return _status("empty", "No hay datos ILGA-Europe para el año seleccionado.")

    grouping_started_at = time.perf_counter()
    current_year = source_dataframe[source_dataframe["year"].eq(effective_year)].copy()
    country_universe = _ilga_country_universe(current_year, countries=query.countries)
    current_selection = _ilga_selected_rows(current_year, query)
    ranking = _ilga_ranking_from_analysis(current_selection, query)
    if ranking.empty and current_selection.empty:
        return _status("empty", "No hay datos ILGA-Europe para la combinación seleccionada.")
    ranking = _complete_country_ranking(
        ranking,
        country_universe,
        countries=query.countries,
    )
    history_dataframe = _ilga_history_dataframe(
        source_dataframe,
        category=query.category,
        criterion=query.criterion,
    )
    detail_dataframe, response_diagnostics = _prepare_ilga_response_details(
        current_selection,
        country_universe,
        query,
    )
    grouping_ms = (time.perf_counter() - grouping_started_at) * 1000
    history_records = history_dataframe.to_dict("records") if include_history else []
    logger.info(
        "legal_statistics_pipeline query_ms=%.2f normalization_ms=%.2f grouping_ms=%.2f",
        query_ms,
        normalization_ms,
        grouping_ms,
        extra={
            "query_ms": round(query_ms, 2),
            "normalization_ms": round(normalization_ms, 2),
            "grouping_ms": round(grouping_ms, 2),
            "category": query.category,
            "criterion": query.criterion,
            "year": effective_year,
        },
    )
    logger.info(
        "legal_temporal_evolution countries_loaded=%d years_loaded=%d series_rendered=%d",
        int(history_dataframe["country_code"].nunique()) if not history_dataframe.empty else 0,
        int(history_dataframe["year"].nunique()) if not history_dataframe.empty else 0,
        int(history_dataframe["country_code"].nunique()) if not history_dataframe.empty else 0,
    )
    logger.info(
        "legal_response_details countries_loaded=%d responses_detected=%d rows_rendered=%d",
        response_diagnostics["countries_loaded"],
        len(response_diagnostics["responses_detected"]),
        len(detail_dataframe),
        extra=response_diagnostics,
    )
    return {
        "status": "ok",
        "message": "",
        "source": "ILGA-Europe",
        "year": effective_year,
        "category": query.category,
        "indicator": query.criterion or query.category or "Ranking total",
        "criterion": query.criterion,
        "data": current_selection.to_dict("records"),
        "detail_data": detail_dataframe.to_dict("records"),
        "legal_response_details_diagnostics": response_diagnostics,
        "country_universe": country_universe.to_dict("records"),
        "ranking": ranking.to_dict("records"),
        "available_countries": sorted(
            value
            for value in country_universe["iso"].dropna().astype(str).unique().tolist()
            if value
        ),
        "history": history_records,
        "metrics": _metrics_from_values(ranking["value"].tolist()),
        "methodology": ("ILGA-Europe Rainbow Map mide leyes, políticas y protecciones jurídicas. "),
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
    return f"ilga-statistics-v4:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


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
    dataframe = ilga_analysis_rows_to_dataframe(get_ilga_analysis_rows(category, criterion))
    history = _ilga_history_dataframe(dataframe, category=category, criterion=criterion)
    return history.to_dict("records")


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


def _ilga_country_universe(
    dataframe: pd.DataFrame,
    *,
    countries: list[str] | None = None,
) -> pd.DataFrame:
    columns = [
        "country",
        "country_name",
        "iso",
        "country_code",
        "ranking",
        "year",
        "source",
    ]
    if dataframe.empty:
        return pd.DataFrame(columns=columns)
    universe = dataframe[dataframe["category"].eq("Ranking total")][columns].copy()
    if countries:
        selected = {normalize_country_code(country) or str(country) for country in countries}
        universe = universe[universe["iso"].isin(selected) | universe["country"].isin(selected)]
    return universe.sort_values(["ranking", "country"], ascending=[False, True]).reset_index(
        drop=True
    )


def _ilga_selected_rows(dataframe: pd.DataFrame, query: IlgaStatisticsQuery) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe
    category = str(query.category or "Ranking total")
    if category == "Ranking total":
        selected_rows = dataframe[dataframe["category"].eq("Ranking total")].copy()
    else:
        selected_rows = dataframe[dataframe["category"].eq(category)].copy()
        if query.criterion:
            selected_rows = selected_rows[selected_rows["criterion"].eq(query.criterion)]
    if query.countries:
        selected = {normalize_country_code(country) or str(country) for country in query.countries}
        selected_rows = selected_rows[
            selected_rows["iso"].isin(selected) | selected_rows["country"].isin(selected)
        ]
    return selected_rows.reset_index(drop=True)


def _ilga_ranking_from_analysis(
    dataframe: pd.DataFrame,
    query: IlgaStatisticsQuery,
) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=["country", "iso", "value"])
    category = str(query.category or "Ranking total")
    if category == "Ranking total" or query.criterion:
        return dataframe[["country", "iso", "value"]].copy()
    return _ilga_category_scores(dataframe)


def _ilga_history_dataframe(
    dataframe: pd.DataFrame,
    *,
    category: str | None,
    criterion: str | None,
) -> pd.DataFrame:
    columns = [
        "country_code",
        "country_name",
        "year",
        "value",
        "indicator_id",
        "source",
        "iso",
        "country",
    ]
    if dataframe.empty:
        return pd.DataFrame(columns=columns)
    clean_category = str(category or "Ranking total")
    if clean_category == "Ranking total":
        history = dataframe[dataframe["category"].eq("Ranking total")][
            ["country_code", "country_name", "year", "value", "source", "iso", "country"]
        ].copy()
        history["indicator_id"] = "Ranking total"
    elif criterion:
        history = dataframe[
            dataframe["category"].eq(clean_category) & dataframe["criterion"].eq(criterion)
        ][["country_code", "country_name", "year", "value", "source", "iso", "country"]].copy()
        history["indicator_id"] = str(criterion)
    else:
        grouped_rows: list[pd.DataFrame] = []
        criteria = dataframe[dataframe["category"].eq(clean_category)]
        for year, year_rows in criteria.groupby("year", sort=True):
            scores = _ilga_category_scores(year_rows)
            if scores.empty:
                continue
            scores["year"] = int(year)
            scores["country_code"] = scores["iso"]
            scores["country_name"] = scores["country"]
            scores["indicator_id"] = clean_category
            scores["source"] = "ILGA-Europe"
            grouped_rows.append(scores[columns])
        history = pd.concat(grouped_rows, ignore_index=True) if grouped_rows else pd.DataFrame()
    if history.empty:
        return pd.DataFrame(columns=columns)
    history["value"] = pd.to_numeric(history["value"], errors="coerce")
    history = history[history["value"].notna()]
    return (
        history[columns].sort_values(["country_code", "year"], kind="stable").reset_index(drop=True)
    )


def _prepare_ilga_response_details(
    dataframe: pd.DataFrame,
    country_universe: pd.DataFrame,
    query: IlgaStatisticsQuery,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns = [
        "country_code",
        "country_name",
        "year",
        "value",
        "indicator_id",
        "source",
        "response",
        "response_order",
        "category",
        "criterion_weight",
        "criterion_value",
        "iso",
        "country",
    ]
    details = dataframe.copy()
    expected_indicators = details["indicator_id"].dropna().astype(str).unique().tolist()
    represented = {
        (str(row.country_code), str(row.indicator_id))
        for row in details[["country_code", "indicator_id"]].itertuples(index=False)
    }
    missing_rows: list[dict[str, Any]] = []
    for country_row in country_universe.itertuples(index=False):
        for indicator_id in expected_indicators:
            if (str(country_row.country_code), indicator_id) in represented:
                continue
            missing_rows.append(
                {
                    "country_code": country_row.country_code,
                    "country_name": country_row.country_name,
                    "year": country_row.year,
                    "value": None,
                    "indicator_id": indicator_id,
                    "source": country_row.source,
                    "response": "not_available",
                    "response_order": ILGA_RESPONSE_ORDER["not_available"],
                    "category": str(query.category or "Ranking total"),
                    "criterion_weight": None,
                    "criterion_value": None,
                    "iso": country_row.iso,
                    "country": country_row.country,
                }
            )
    if missing_rows:
        details = pd.concat([details, pd.DataFrame(missing_rows)], ignore_index=True)
    if details.empty:
        details = pd.DataFrame(columns=columns)
    else:
        details = details[columns].sort_values(
            ["country_name", "response_order", "indicator_id"], kind="stable"
        )
    responses = (
        details[["response", "response_order"]]
        .dropna(subset=["response"])
        .sort_values("response_order", kind="stable")["response"]
        .astype(str)
        .unique()
        .tolist()
    )
    countries_loaded = int(country_universe["country_code"].nunique())
    countries_with_values = int(details.loc[details["value"].notna(), "country_code"].nunique())
    diagnostics = {
        "countries_loaded": countries_loaded,
        "countries_rendered": countries_with_values,
        "countries_without_data": countries_loaded - countries_with_values,
        "responses_detected": responses,
        "rows_rendered": len(details),
    }
    return details.reset_index(drop=True), diagnostics


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
    numeric_dataframe[value_column] = pd.to_numeric(
        numeric_dataframe[value_column], errors="coerce"
    )
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

    valid_candidates = (
        candidates[candidates["percentage"].notna()] if "percentage" in candidates else candidates
    )
    if valid_candidates.empty:
        valid_candidates = candidates

    if _has_exact_filter_labels(valid_candidates, "All", "All"):
        return "All", "All"

    all_a = valid_candidates[
        valid_candidates["filter_a"].apply(lambda value: _same_filter_label(value, "All"))
    ]
    non_all_b_values = _sorted_non_all_filter_values(all_a, "filter_b")
    if non_all_b_values:
        return "All", non_all_b_values[0]

    all_b = valid_candidates[
        valid_candidates["filter_b"].apply(lambda value: _same_filter_label(value, "All"))
    ]
    non_all_a_values = _sorted_non_all_filter_values(all_b, "filter_a")
    if non_all_a_values:
        return non_all_a_values[0], "All"

    pairs = sorted(
        {
            (normalize_filter_value(row.filter_a), normalize_filter_value(row.filter_b))
            for row in valid_candidates[["filter_a", "filter_b"]].itertuples()
            if not _same_filter_label(row.filter_a, "All")
            and not _same_filter_label(row.filter_b, "All")
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
        if (
            repair_text_encoding(raw_value).strip() == filter_value
            or normalize_filter_value(raw_value) == expected_label
        ):
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
    return any(not _row_has_group_filter(filters, allowed) for filters in dataframe["filters"])


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
    return not (filter_b_type is not None and not _row_has_filter_type(filters, filter_b_type))


def _row_has_group_filter(filters: Any, allowed: tuple[str, ...]) -> bool:
    if not isinstance(filters, dict):
        return False
    allowed_keys = {
        normalize_filter_type(filter_type) for filter_type in allowed if filter_type != "All"
    }
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
    criteria["criterion_value"] = pd.to_numeric(criteria["criterion_value"], errors="coerce")
    criteria["criterion_weight"] = pd.to_numeric(criteria["criterion_weight"], errors="coerce")
    criteria = criteria[
        criteria["criterion_value"].notna()
        & criteria["criterion_weight"].notna()
        & criteria["criterion_weight"].gt(0)
    ]
    if criteria.empty:
        return pd.DataFrame(columns=["country", "iso", "value"])
    criteria["weighted_value"] = criteria["criterion_value"] * criteria["criterion_weight"]
    criteria["weight"] = criteria["criterion_weight"]
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
        selected = {normalize_country_code(country) or str(country) for country in countries}
        universe = universe[universe["iso"].isin(selected) | universe["country"].isin(selected)]

    values = (
        ranking[["iso", "value"]].copy()
        if not ranking.empty
        else pd.DataFrame(columns=["iso", "value"])
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
        completed["difference"] / european_mean * 100 if european_mean not in (None, 0) else None
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
        completed[column] = (
            completed[column]
            .astype(object)
            .where(
                pd.notna(completed[column]),
                None,
            )
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
    except TypeError, ValueError:
        return None


def _safe_float(value: Any) -> float | None:
    return coerce_percentage(value)


def _safe_unit_score(value: Any) -> float | None:
    try:
        numeric = float(value)
    except TypeError, ValueError:
        return None
    return numeric if pd.notna(numeric) and 0 <= numeric <= 1 else None


def _safe_positive_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except TypeError, ValueError:
        return None
    return numeric if pd.notna(numeric) and numeric > 0 else None


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
    return min(values.items(), key=lambda item: item[1])[0]


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


def _empty_ilga_analysis_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "document_id",
            "country_index",
            "criterion_index",
            "source",
            "year",
            "country",
            "country_name",
            "iso",
            "country_code",
            "ranking",
            "category",
            "criterion",
            "indicator_id",
            "criterion_value",
            "criterion_weight",
            "value",
            "response",
            "response_order",
        ]
    )
