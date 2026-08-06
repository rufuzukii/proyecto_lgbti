from types import SimpleNamespace
from unittest.mock import MagicMock

from app.import_to_db.fra.backfill_year import backfill_fra_survey_year


def _evidence_csv(year: int) -> str:
    return f'''topic,question,question_code,Location,country,Yes
Discrimination,Area > Question,D1_1,Spain,ES,42
Source:,"EU LGBTIQ Survey III, {year}",,,,
'''


def test_backfill_is_a_dry_run_by_default(tmp_path) -> None:
    evidence = tmp_path / "fra.csv"
    evidence.write_text(_evidence_csv(2023), encoding="utf-8")
    collection = MagicMock()
    collection.find.side_effect = [
        [{"_id": "one", "code": "D1_1", "answers": [{"percentage": 42}]}],
        [],
    ]

    report = backfill_fra_survey_year([evidence], collection=collection)

    assert report.survey_year == 2023
    assert report.matched_documents == 1
    assert report.matched_answers == 1
    assert report.updated_documents == 0
    collection.update_one.assert_not_called()


def test_backfill_applies_year_without_overwriting_assigned_answer_year(tmp_path) -> None:
    evidence = tmp_path / "fra.csv"
    evidence.write_text(_evidence_csv(2023), encoding="utf-8")
    collection = MagicMock()
    collection.find.side_effect = [
        [
            {
                "_id": "one",
                "code": "D1_1",
                "answers": [
                    {"percentage": 42},
                    {"percentage": 43, "survey_year": 2023},
                ],
            }
        ],
        [],
    ]
    collection.update_one.return_value = SimpleNamespace(modified_count=1)

    report = backfill_fra_survey_year([evidence], apply=True, collection=collection)

    assert report.updated_documents == 1
    assert report.updated_answers == 1
    update = collection.update_one.call_args.args[1]["$set"]
    assert update["survey_year"] == 2023
    assert [answer["survey_year"] for answer in update["answers"]] == [2023, 2023]


def test_backfill_reports_a_conflicting_existing_edition(tmp_path) -> None:
    evidence = tmp_path / "fra.csv"
    evidence.write_text(_evidence_csv(2023), encoding="utf-8")
    collection = MagicMock()
    collection.find.side_effect = [
        [
            {
                "_id": "one",
                "code": "D1_1",
                "answers": [{"percentage": 42, "survey_year": 2019}],
            }
        ],
        [],
    ]

    report = backfill_fra_survey_year([evidence], apply=True, collection=collection)

    assert report.matched_documents == 0
    assert report.unresolved_codes == ("D1_1",)
    collection.update_one.assert_not_called()
