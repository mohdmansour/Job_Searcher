"""Fidelity suite against the REAL models. Run:
    uv run pytest -m live tests/live/test_fidelity_live.py -s -p no:warnings
Banned-term checks are plain string checks, not LLM judgments.
"""

import re

import pytest

from jobcv.agents.reviewer import review_cv
from jobcv.agents.scorer import score_job
from jobcv.cost.meter import CostMeter
from jobcv.pipeline.tailor_loop import tailor_for_job
from jobcv.schemas import CV

pytestmark = pytest.mark.live

BANNED = ["selenium", "jira", "istqb", "test automation", "automation testing", "automated test",
          "sql", "postman", "cypress", "playwright", "appium", "testrail", "jmeter",
          "api testing", "test cases", "test case", "bug tracking", "defect tracking",
          "software testing", "regression testing", "qa engineer", "quality assurance engineer"]


def all_text(cv: CV) -> str:
    return cv.model_dump_json(exclude={"contact"}).lower()


def test_scorer_gives_teacher_a_low_score_for_qa(settings, teacher, qa_job):
    cv, _ = teacher
    meter = CostMeter(settings)
    m = score_job(cv, qa_job, settings, meter)
    print(f"\nSCORE {m.score} | gaps: {m.gaps} | reasons: {m.reasons} | "
          f"${meter.record().actual_cost_usd:.4f}")
    assert m.score <= 40
    assert len(m.gaps) >= 2


def test_teacher_to_qa_adds_nothing(settings, teacher, qa_job):
    cv, raw = teacher
    meter = CostMeter(settings)
    out = tailor_for_job(cv, raw, qa_job, settings, meter)
    text = all_text(out.tailored_cv)
    print(f"\nTAILOR status={out.review_status} attempts={out.attempts} "
          f"cost=${meter.record().actual_cost_usd:.4f}\nSUMMARY: {out.tailored_cv.summary}")
    for e in out.tailored_cv.experience:
        print(f"  {e.title} | {e.employer}")
        for b in e.bullets:
            print(f"    - {b}")
    print("  SKILLS:", out.tailored_cv.skills)
    for v in out.remaining_violations:
        print("  REMAINING:", v.problem, v.adapted_text, "|", v.explanation)
    found = [t for t in BANNED if re.search(rf"\b{re.escape(t)}\b", text)]
    assert found == [], f"invented QA terms: {found}"
    titles = [(e.title, e.employer) for e in out.tailored_cv.experience]
    assert titles == [(e.title, e.employer) for e in cv.experience]
    assert out.review_status == "PASS"


def corrupt(cv: CV) -> CV:
    bad = cv.model_copy(deep=True)
    bad.skills.append("Selenium WebDriver")
    job = bad.experience[0]
    job.bullets = [b.replace("28", "45") for b in job.bullets]
    job.bullets = [re.sub(r"^Helped organise", "Led", b) for b in job.bullets]
    return bad


def test_reviewer_fails_corrupted_cv_and_lists_each_violation(settings, teacher):
    cv, raw = teacher
    bad = corrupt(cv)
    assert any(b.startswith("Led") for b in bad.experience[0].bullets), "fixture changed"
    r = review_cv(cv, raw, bad, settings, CostMeter(settings))
    for v in r.violations:
        print(f"\n  [{v.problem}] {v.adapted_text} | {v.explanation}")
    joined = " ".join(v.adapted_text for v in r.violations)
    assert r.status == "FAIL"
    assert "Selenium" in joined  # fake tool
    assert "45" in joined  # fake number
    assert any(v.problem == "D" and v.adapted_text.startswith("Led") for v in r.violations), \
        "upgraded verb 'Led' must be flagged as D"


def test_reviewer_passes_honest_rewording(settings, teacher):
    cv, raw = teacher
    good = cv.model_copy(deep=True)
    job = good.experience[0]
    # same activities, the job's vocabulary, nothing new
    job.bullets[0] = job.bullets[0].replace("Marked and graded", "Reviewed and graded", 1)
    good.summary = ("Detail-oriented primary school teacher with 7 years of experience in "
                    "reviewing pupils' work, writing assessment criteria and reporting progress.")
    r = review_cv(cv, raw, good, settings, CostMeter(settings))
    for v in r.violations:
        print(f"\n  [{v.problem}] {v.adapted_text} | {v.explanation}")
    assert r.status == "PASS", r.violations
