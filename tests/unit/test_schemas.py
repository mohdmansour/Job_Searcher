from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jobcv.schemas import (
    CV,
    Country,
    EditResult,
    Job,
    MatchResult,
    ReviewResult,
    SearchQuery,
    Usage,
)


def test_job_has_exactly_the_unified_fields():
    assert set(Job.model_fields) == {
        "id", "source", "title", "company", "location", "remote", "description",
        "url", "posted_at", "fetched_at", "language",
    }


def test_search_query_requires_known_country():
    with pytest.raises(ValidationError):
        SearchQuery(title="QA", country="Middle East")
    with pytest.raises(ValidationError):
        SearchQuery(title="QA", country="Worldwide")


def test_search_query_cleans_cities_and_title():
    q = SearchQuery(title="  QA Engineer ", country=Country.GERMANY, cities=[" Berlin ", "", "Munich"])
    assert q.title == "QA Engineer"
    assert q.cities == ["Berlin", "Munich"]


def test_search_query_rejects_bad_max_results():
    with pytest.raises(ValidationError):
        SearchQuery(title="QA", country=Country.UAE, max_results=0)


def test_match_score_must_be_0_to_100():
    with pytest.raises(ValidationError):
        MatchResult(score=101, reasons=[], matched_skills=[], gaps=[])
    assert MatchResult(score=0, reasons=["x"], matched_skills=[], gaps=["y"]).score == 0


def test_review_problem_codes_are_a_to_e():
    ok = ReviewResult.model_validate(
        {"status": "FAIL", "violations": [
            {"adapted_text": "Led QA", "problem": "D", "explanation": "upgraded", "suggested_fix": "Helped"}
        ]}
    )
    assert ok.violations[0].problem == "D"
    with pytest.raises(ValidationError):
        ReviewResult.model_validate({"status": "FAIL", "violations": [
            {"adapted_text": "x", "problem": "Z", "explanation": "", "suggested_fix": ""}]})


def test_cv_defaults_to_empty_sections():
    cv = CV()
    assert cv.experience == [] and cv.skills == [] and cv.other == []


def test_edit_result_holds_cv_and_change_log():
    r = EditResult.model_validate({
        "tailored_cv": {"summary": "Teacher"},
        "change_log": [{"original": "a", "adapted": "b", "why_faithful": "same activity"}],
    })
    assert r.tailored_cv.summary == "Teacher"


def test_usage_adds_up():
    total = Usage(input_tokens=10, output_tokens=5) + Usage(input_tokens=1, cached_input_tokens=2)
    assert (total.input_tokens, total.cached_input_tokens, total.output_tokens) == (11, 2, 5)


def test_job_dates_are_timezone_aware():
    j = Job(id="1", source="linkedin", title="t", company="c", location="Berlin, Germany",
            remote=False, description="d", url="https://x", posted_at=None,
            fetched_at=datetime.now(UTC), language="en")
    assert j.fetched_at.tzinfo is not None


def test_website_lists_every_backend_country():
    """web/lib/countries.ts must stay in step with the Country enum."""
    from pathlib import Path

    from jobcv.schemas import Country

    source = (Path(__file__).parents[2] / "web" / "lib" / "countries.ts").read_text(encoding="utf-8")
    missing = [c.value for c in Country if f"value: '{c.value}'" not in source]
    assert missing == []
    assert source.count("{ value: ") == len(Country)
