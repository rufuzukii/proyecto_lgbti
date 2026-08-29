from app.shared.data.legal_criteria import (
    ILGA_CRITERION_SOURCE_ALIASES,
    get_criterion_id,
    get_criterion_metadata,
    get_criterion_score_label,
    get_criterion_status,
    stable_criterion_id,
)


def test_get_criterion_metadata_returns_translated_summary_for_source_label() -> None:
    criterion = {
        "category": "Equality & non-discrimination",
        "indicator": "Constitution (sexual orientation)",
    }

    metadata_es = get_criterion_metadata(criterion, "es")
    metadata_en = get_criterion_metadata(criterion, "en")

    assert metadata_es["id"] == "constitution_sexual_orientation"
    assert metadata_es["title"] == "Protección constitucional por orientación sexual"
    assert "discriminación por orientación sexual" in metadata_es["summary"]
    assert metadata_en["title"] == "Constitutional protection based on sexual orientation"
    assert "sexual orientation" in metadata_en["summary"]


def test_get_criterion_id_accepts_common_ilga_abbreviation_aliases() -> None:
    assert (
        get_criterion_id("Hate crime law (GI)", "Hate crime & hate speech")
        == "hate_crime_law_gender_identity"
    )
    assert get_criterion_id("Asylum law - SC", "Asylum") == "asylum_law_sex_characteristics"


def test_stable_criterion_id_falls_back_without_using_visible_text_only_when_known() -> None:
    assert stable_criterion_id("Marriage equality", "Family") == "marriage_equality"
    assert (
        stable_criterion_id("Dataset-specific criterion", "Custom category")
        == "custom_category_dataset_specific_criterion"
    )


def test_get_criterion_status_uses_maximum_value_for_full_completion() -> None:
    assert get_criterion_status(0.05882352941, 0.05882352941, "es")["id"] == "fully_met"
    assert get_criterion_status(0.02, 0.05882352941, "en")["label"] == "Partially met"
    assert get_criterion_status(0, 0.05882352941, "es")["label"] == "No reconocido"
    assert get_criterion_status(None, 0.05882352941, "en")["label"] == "Information unavailable"


def test_get_criterion_status_without_maximum_treats_one_as_full() -> None:
    assert get_criterion_status(1, None, "en")["id"] == "fully_met"
    assert get_criterion_status(0.5, None, "en")["id"] == "partially_met"


def test_get_criterion_score_label_is_readable_and_translated() -> None:
    assert get_criterion_score_label(0.5, 1, "es") == "Puntuación: 0.5 / 1"
    assert get_criterion_score_label(0.5, 1, "en") == "Score: 0.5 / 1"
    assert get_criterion_score_label(None, 1, "es") == ""


def test_current_ilga_source_aliases_all_resolve_to_specific_bilingual_copy() -> None:
    assert len(ILGA_CRITERION_SOURCE_ALIASES) == 26
    for category, source_label, expected_id in ILGA_CRITERION_SOURCE_ALIASES:
        criterion = {"category": category, "indicator": source_label}
        spanish = get_criterion_metadata(criterion, "es")
        english = get_criterion_metadata(criterion, "en")

        assert spanish["id"] == expected_id
        assert spanish["known"] == "true"
        assert english["known"] == "true"
        assert spanish["summary"] != "Consulta el grado de cumplimiento de este indicador en el país seleccionado."
        assert english["summary"] != "View this indicator's compliance level for the selected country."
