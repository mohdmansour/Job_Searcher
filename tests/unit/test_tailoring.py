"""Editor / Reviewer / loop, with fake LLMs. The live fidelity suite is in tests/live/."""

from datetime import UTC, datetime

import pytest

from jobcv.agents.base import LLMReply
from jobcv.agents.editor import edit_cv
from jobcv.agents.reviewer import code_violations, review_cv
from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.pipeline.tailor_loop import tailor_for_job
from jobcv.schemas import (
    CV,
    Contact,
    EditResult,
    Education,
    Experience,
    Job,
    ReviewResult,
    Usage,
    Violation,
)

RAW = """Sarah Thompson
Primary School Teacher — Oakfield Primary School, Manchester (Sep 2019 – Present)
- Marked and graded weekly maths and English work for a class of 28 pupils, identifying recurring errors.
- Wrote assessment criteria (rubrics) for end-of-term writing tasks, following National Curriculum standards.
- Helped organise the school's annual Ofsted inspection evidence folders.
PGCE Primary Education — University of Manchester (2018 – 2019)
Skills: Lesson planning; Report writing; Microsoft Excel"""

MASTER = CV(
    language="en",
    contact=Contact(name="Sarah Thompson", email="s@example.com"),
    summary="Primary school teacher with 7 years of experience.",
    experience=[Experience(
        title="Primary School Teacher", employer="Oakfield Primary School",
        start="Sep 2019", end="Present",
        bullets=[
            ("Marked and graded weekly maths and English work for a class of 28 pupils, "
            "identifying recurring errors."),
            ("Wrote assessment criteria (rubrics) for end-of-term writing tasks, following "
            "National Curriculum standards."),
            "Helped organise the school's annual Ofsted inspection evidence folders.",
        ])],
    education=[Education(degree="PGCE Primary Education", institution="University of Manchester")],
    skills=["Lesson planning", "Report writing", "Microsoft Excel"],
)

QA_JOB = Job(id="linkedin:1", source="linkedin", title="Jr. QA Engineer", company="Acme",
             location="Dubai", remote=False,
             description="Manual testing, Selenium, Jira, SQL, ISTQB preferred.",
             url="https://x/1", posted_at=None, fetched_at=datetime.now(UTC), language="en")


def honest() -> CV:
    cv = MASTER.model_copy(deep=True)
    cv.summary = "Detail-oriented primary school teacher with 7 years of experience."
    cv.experience[0].bullets[0] = ("Reviewed and graded weekly maths and English work for 28 "
                                   "pupils, identifying recurring errors.")
    return cv


def corrupted() -> CV:
    cv = honest()
    cv.skills.append("Selenium")  # fake tool
    cv.experience[0].bullets[0] = ("Graded weekly work for a class of 45 pupils, identifying "
                                   "recurring errors.")  # fake number
    cv.experience[0].bullets[2] = "Led the school's annual Ofsted inspection."  # upgraded verb
    cv.experience[0].title = "QA Lead"  # renamed title
    return cv


@pytest.fixture
def s(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path)


# ---------- deterministic reviewer checks ----------

def test_code_checks_pass_an_honest_rewording():
    assert code_violations(MASTER, RAW, honest()) == []


def test_code_checks_catch_fake_tool_number_and_title():
    problems = {(v.problem, v.adapted_text) for v in code_violations(MASTER, RAW, corrupted())}
    assert ("A", "Selenium") in problems
    assert any(p == "C" and "45" in t for p, t in problems)
    assert any(p == "B" and "QA Lead" in t for p, t in problems)


def test_extra_info_is_a_valid_source():
    cv = honest()
    cv.skills.append("Jira")
    assert code_violations(MASTER, RAW, cv, extra_info="") != []
    assert code_violations(MASTER, RAW, cv, extra_info="I used Jira to track tickets.") == []


def test_arabic_digits_count_as_the_same_number():
    master = MASTER.model_copy(update={"language": "ar"})
    cv = honest()
    cv.experience[0].bullets[0] = "تصحيح أعمال ٢٨ طالبا"
    assert not [v for v in code_violations(master, RAW, cv) if v.problem == "C"]


# ---------- reviewer = LLM + code ----------

def test_reviewer_adds_code_violations_even_if_llm_passes(s):
    def llm(spec, model, prompt, out):
        return LLMReply(raw="", parsed=ReviewResult(status="PASS"), usage=Usage())

    r = review_cv(MASTER, RAW, corrupted(), s, CostMeter(s), llm=llm)
    assert r.status == "FAIL" and {v.problem for v in r.violations} >= {"A", "B", "C"}


def test_reviewer_keeps_llm_violations_for_meaning_and_seniority(s):
    d = Violation(adapted_text="Led the school's annual Ofsted inspection.", problem="D",
                  explanation="helped -> led", suggested_fix="Helped organise ...")

    def llm(spec, model, prompt, out):
        assert "MASTER CV RAW TEXT" in prompt and "Ofsted" in prompt
        return LLMReply(raw="", parsed=ReviewResult(status="FAIL", violations=[d]), usage=Usage())

    r = review_cv(MASTER, RAW, corrupted(), s, CostMeter(s), llm=llm)
    assert d in r.violations


# ---------- editor ----------

def test_editor_prompt_has_rules_job_and_feedback(s):
    seen = {}

    def llm(spec, model, prompt, out):
        seen["p"], seen["m"] = prompt, model
        return LLMReply(raw="", parsed=EditResult(tailored_cv=honest()), usage=Usage())

    fb = [Violation(adapted_text="Selenium", problem="A", explanation="x", suggested_fix="remove")]
    edit_cv(MASTER, QA_JOB, s, CostMeter(s), feedback=fb, previous=corrupted(), llm=llm)
    p = seen["p"]
    assert seen["m"] == "gpt-5.4"
    assert "Never rename a past job title" in p and '"helped" must not become "led"' in p
    assert "Selenium, Jira, SQL" in p  # job description
    assert "Fix EXACTLY these violations" in p and "[A] \"Selenium\"" in p
    assert "s@example.com" not in p  # contact details are not sent


def test_editor_cannot_change_contact_or_language(s):
    def llm(spec, model, prompt, out):
        cv = honest().model_copy(update={"contact": Contact(name="Someone Else"), "language": "ar"})
        return LLMReply(raw="", parsed=EditResult(tailored_cv=cv), usage=Usage())

    r = edit_cv(MASTER, QA_JOB, s, CostMeter(s), llm=llm)
    assert r.tailored_cv.contact.name == "Sarah Thompson" and r.tailored_cv.language == "en"


# ---------- loop ----------

def scripted(edits: list[CV], reviews: list[ReviewResult]):
    edits, reviews, log = list(edits), list(reviews), []

    def llm(spec, model, prompt, out):
        log.append(spec.name)
        if spec.name == "editor":
            return LLMReply(raw="", parsed=EditResult(tailored_cv=edits.pop(0)), usage=Usage())
        return LLMReply(raw="", parsed=reviews.pop(0), usage=Usage())
    return llm, log


def test_loop_passes_first_time(s):
    llm, log = scripted([honest()], [ReviewResult(status="PASS")])
    out = tailor_for_job(MASTER, RAW, QA_JOB, s, CostMeter(s), llm=llm)
    assert out.review_status == "PASS" and out.attempts == 1 and not out.warning
    assert log == ["editor", "reviewer"]


def test_loop_fixes_after_feedback(s):
    llm, log = scripted([corrupted(), honest()],
                        [ReviewResult(status="PASS"), ReviewResult(status="PASS")])
    out = tailor_for_job(MASTER, RAW, QA_JOB, s, CostMeter(s), llm=llm)
    # first version fails on the code checks even though the LLM said PASS
    assert out.review_status == "PASS" and out.attempts == 2
    assert log == ["editor", "reviewer", "editor", "reviewer"]


def test_loop_stops_after_max_attempts_with_warning(s):
    llm, log = scripted([corrupted()] * 3, [ReviewResult(status="PASS")] * 3)
    out = tailor_for_job(MASTER, RAW, QA_JOB, s, CostMeter(s), llm=llm)
    assert out.review_status == "FAIL" and out.warning and out.attempts == 3
    assert out.remaining_violations and log.count("editor") == 3
