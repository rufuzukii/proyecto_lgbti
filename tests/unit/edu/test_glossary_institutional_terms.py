from __future__ import annotations

from collections import Counter

from app.modules.didactics.components import glossary_card
from app.modules.didactics.game_service import new_game_state
from app.modules.didactics.glossary_service import (
    UNAM_SOURCE_URL,
    get_glossary_term,
    list_glossary_terms,
    normalized_term_key,
    search_glossary,
)
from app.modules.didactics.word_search_service import select_word_search_terms
from app.shared.data.legal_criteria import get_criterion_metadata

REQUESTED_IDS = {
    "sexual_diversity",
    "gender_diversity",
    "bodily_diversity",
    "trans_rights",
    "intersex",
    "lgtbiphobia",
    "conversion_practices",
    "hate_crimes",
    "hate_speech",
    "legal_gender_recognition",
    "depathologisation",
    "intersex_bodily_integrity",
    "informed_consent",
    "non_consensual_medical_interventions",
    "lgbtiq_asylum",
    "civil_society_space",
    "marriage_equality",
    "registered_partnership",
    "cohabitation_recognition",
    "joint_adoption",
    "second_parent_adoption",
    "co_parenthood",
    "assisted_reproduction",
    "trans_parenthood",
    "families_with_lgbtiq_parents",
    "non_discriminatory_blood_donation",
    "living_openly_lgbtiq",
    "social_acceptance",
    "diversity_and_inclusion",
    "visibility_and_safety",
    "violence_and_harassment",
    "physical_violence",
    "sexual_violence",
}

PRIORITY_SOURCE = {
    "lgtbiphobia": "Boletín Oficial del Estado (BOE)",
    "conversion_practices": "Council of Europe",
    "marriage_equality": "ILGA-Europe",
    "legal_gender_recognition": "ILGA-Europe",
    "hate_crimes": "ECRI / Council of Europe",
    "hate_speech": "ECRI / Council of Europe",
    "intersex_bodily_integrity": "Council of Europe",
    "sexual_diversity": "World Health Organization (WHO)",
    "gender_diversity": "World Health Organization (WHO)",
    "bodily_diversity": "Council of Europe",
    "trans_parenthood": "ILGA-Europe",
}


def _walk(component):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for item in component:
            yield from _walk(item)
        return
    yield component
    yield from _walk(getattr(component, "children", None))


def test_all_requested_terms_are_bilingual_categorised_and_sourced() -> None:
    requested = [term for term in list_glossary_terms() if term.id in REQUESTED_IDS]

    assert len(requested) == len(REQUESTED_IDS) == 33
    assert {term.id for term in requested} == REQUESTED_IDS
    assert all(term.term and term.definition for term in requested)
    assert all(term.term_en and term.definition_en for term in requested)
    assert all(term.attribution == "based_on" for term in requested)
    assert all(term.sources for term in requested)
    assert all(
        source.title
        for term in requested
        for source in term.sources
        if source.name not in {"UNAM", "FundéuRAE"}
    )
    assert all(source.url.startswith("https://") for term in requested for source in term.sources)
    assert Counter(term.category for term in requested) == {
        "diversity_inclusion": 3,
        "sex_characteristics_intersex": 5,
        "discrimination_social": 9,
        "rights_legal_protection": 7,
        "families_rights": 9,
    }


def test_priority_terms_use_the_requested_institutional_sources() -> None:
    for term_id, expected_source in PRIORITY_SOURCE.items():
        term = get_glossary_term(term_id)
        assert term is not None
        assert expected_source in {source.name for source in term.sources}


def test_catalog_ids_and_normalised_spanish_names_are_unique() -> None:
    terms = list_glossary_terms()
    ids = [term.id for term in terms]
    names = [normalized_term_key(term.term) for term in terms]

    assert len(ids) == len(set(ids))
    assert len(names) == len(set(names))
    assert sum(term.id == "intersex" for term in terms) == 1
    intersex = get_glossary_term("intersex")
    assert intersex is not None
    assert intersex.term == "Intersexualidad"


def test_endosex_uses_the_unam_definition_and_intersex_context() -> None:
    term = get_glossary_term("endosex")

    assert term is not None
    assert term.term == term.term_en == "Endosex"
    assert term.category == "sex_characteristics_intersex"
    assert "norma genital dimórfica" in term.definition
    assert "intersex" in term.definition.casefold()
    assert {source.name for source in term.sources} == {"UNAM"}
    assert {source.url for source in term.sources} == {UNAM_SOURCE_URL}


def test_search_indexes_spanish_english_and_aliases_without_accents() -> None:
    assert {term.id for term in search_glossary("PRACTICAS DE CONVERSION")} >= {
        "conversion_practices"
    }
    assert {term.id for term in search_glossary("legal gender recognition", language="en")} >= {
        "legal_gender_recognition"
    }
    assert {term.id for term in search_glossary("LGR", language="en")} >= {
        "legal_gender_recognition"
    }
    assert {
        term.id for term in search_glossary("Recognition of trans parenthood", language="en")
    } >= {"trans_parenthood"}


def test_informed_consent_is_contextualised_for_intersex_people_without_conflating_asexuality() -> (
    None
):
    term = get_glossary_term("informed_consent")

    assert term is not None
    assert term.term == "Consentimiento informado"
    assert term.term_en == "Informed consent"
    assert "personas intersex" in term.definition
    assert "intersex people" in term.definition_en
    assert "asexual" not in f"{term.definition} {term.definition_en}".casefold()
    assert {source.name for source in term.sources} == {"Council of Europe"}


def test_international_protection_is_removed_only_from_the_educational_catalog() -> None:
    assert get_glossary_term("international_protection") is None
    assert not search_glossary("Protección internacional")
    legal = get_criterion_metadata("Asylum law (sexual orientation)", language="es")
    assert legal["known"] == "true"
    assert "protección internacional" in legal["summary"]


def test_card_localises_content_and_exposes_secure_accessible_source_links() -> None:
    term = get_glossary_term("lgtbiphobia")
    assert term is not None

    card = glossary_card(term, "en")
    nodes = list(_walk(card))
    links = [node for node in nodes if getattr(node, "href", None)]

    assert any(getattr(node, "children", None) == term.term_en for node in nodes)
    assert any(getattr(node, "children", None) == term.definition_en for node in nodes)
    assert links
    assert all(link.target == "_blank" for link in links)
    assert all(link.rel == "noopener noreferrer" for link in links)
    assert all(link.href.startswith("https://") for link in links)
    assert all(getattr(link, "aria-label", "").startswith("View source:") for link in links)


def test_game_metadata_excludes_unsuitable_terms_without_hiding_them() -> None:
    long_term = get_glossary_term("families_with_lgbtiq_parents")
    playable_term = get_glossary_term("trans_parenthood")
    word_search_term = get_glossary_term("intersex")
    assert long_term is not None
    assert playable_term is not None
    assert word_search_term is not None
    assert long_term.guess_game is False
    assert long_term.word_search_enabled("es") is False

    state = new_game_state(
        "guess_term",
        rounds=2,
        term_ids=[long_term.id, playable_term.id],
        shuffle=False,
    )
    assert state["order"] == [playable_term.id]
    selected = select_word_search_terms(
        [long_term, word_search_term],
        language="en",
        count=2,
        max_length=40,
        seed=7,
    )
    assert selected == (word_search_term,)


def test_every_active_card_is_fully_bilingual_and_uses_a_visible_category() -> None:
    terms = list_glossary_terms()

    assert len(terms) == 63
    assert all(term.term and term.term_en for term in terms)
    assert all(term.definition and term.definition_en for term in terms)
    assert {term.category for term in terms} == {
        "sexual_orientation",
        "gender_identity_expression",
        "sex_characteristics_intersex",
        "discrimination_social",
        "rights_legal_protection",
        "families_rights",
        "diversity_inclusion",
    }


def test_scope_audit_removes_specialised_redundant_and_legacy_cards() -> None:
    removed = {
        "abrosexual",
        "androsexual",
        "anthrosexual",
        "bigender",
        "cisheteropatriarchy",
        "sexed_body",
        "demigender",
        "gender_dysphoria",
        "drag_king",
        "drag_queen",
        "graysexual",
        "cis_man",
        "homoparentality",
        "cis_woman",
        "omnisexual",
        "pangender",
        "polysexual",
        "serophobia",
        "transgender",
        "gender_diverse_people",
        "trans_realities",
        "lgbtiq_human_rights_defenders",
        "same_sex_couples",
        "lgbtiq_youth",
        "international_protection",
    }

    assert removed.isdisjoint({term.id for term in list_glossary_terms()})


def test_ilga_family_cards_use_exact_criteria_and_methodology_source() -> None:
    family = {term.id: term for term in list_glossary_terms() if term.category == "families_rights"}
    assert family["co_parenthood"].term == "Reconocimiento automático de la coparentalidad"
    assert family["co_parenthood"].term_en == "Automatic co-parent recognition"
    assert "desde el nacimiento" in family["co_parenthood"].definition
    assert "from birth" in family["co_parenthood"].definition_en
    for identifier in {
        "marriage_equality",
        "registered_partnership",
        "cohabitation_recognition",
        "joint_adoption",
        "second_parent_adoption",
        "co_parenthood",
        "assisted_reproduction",
        "trans_parenthood",
    }:
        assert family[identifier].sources[0].url == "https://rainbowmap.ilga-europe.org/about/"
