"""The editor matches the CV to the role, fixes language mistakes and suggests what only the
user can add. Each change is labelled (fixed, reworded, moved). Fake LLMs; the real check is
the live fidelity suite."""

import pytest

from jobcv.agents.base import LLMReply
from jobcv.agents.editor import RULES
from jobcv.agents.reviewer import PROMPT as REVIEW_PROMPT
from jobcv.cost.meter import CostMeter
from jobcv.pipeline.tailor_loop import MAX_SUGGESTIONS, tailor_for_job
from jobcv.schemas import ChangeLogEntry, EditResult, ReviewResult, Usage
from tests.unit.test_tailoring import MASTER, QA_JOB, RAW, honest

BULLET = MASTER.experience[0].bullets[0]


@pytest.fixture
def s(tmp_path):
    from jobcv.config import Settings
    return Settings(_env_file=None, data_dir=tmp_path)


def run(s, change_log=(), suggestions=()):
    def llm(spec, model, prompt, out):
        if spec.name == "editor":
            return LLMReply(raw="", usage=Usage(), parsed=EditResult(
                tailored_cv=honest(), change_log=list(change_log), suggestions=list(suggestions)))
        return LLMReply(raw="", parsed=ReviewResult(status="PASS"), usage=Usage())
    return tailor_for_job(MASTER, RAW, QA_JOB, s, CostMeter(s), llm=llm)


# ---------------- what changed, and how ----------------
def test_a_line_that_only_moved_is_labelled_moved_whatever_the_model_says(s):
    out = run(s, [ChangeLogEntry(original=BULLET, adapted=BULLET, why_faithful="moved up",
                                 kind="reworded")])
    assert [e.kind for e in out.change_log] == ["moved"]


def test_fixed_and_reworded_lines_keep_their_label(s):
    fixed = ChangeLogEntry(original=BULLET, adapted=BULLET.replace("Marked", "Marked,"),
                           why_faithful="punctuation", kind="fixed")
    reworded = ChangeLogEntry(original="Helped organise the school's annual Ofsted inspection evidence folders.",
                              adapted="Helped organise inspection evidence and records.",
                              why_faithful="same activity", kind="reworded")
    assert [e.kind for e in run(s, [fixed, reworded]).change_log] == ["fixed", "reworded"]


def test_an_old_change_log_without_a_label_reads_as_reworded():
    assert ChangeLogEntry(original="a", adapted="b", why_faithful="c").kind == "reworded"


# ---------------- suggestions only the user can act on ----------------
def test_suggestions_reach_the_result(s):
    out = run(s, suggestions=["Add the dates for your first role."])
    assert out.suggestions == ["Add the dates for your first role."]


def test_suggestions_are_trimmed_deduplicated_and_capped(s):
    many = ["  Add a number to a result.  ", "Add a number to a result.", ""] + [
        f"Suggestion {i}" for i in range(20)]
    out = run(s, suggestions=many)
    assert out.suggestions[0] == "Add a number to a result."
    assert "" not in out.suggestions and len(out.suggestions) == MAX_SUGGESTIONS
    assert len(set(out.suggestions)) == len(out.suggestions)


# ---------------- the instructions keep every honesty rule ----------------
@pytest.mark.parametrize("rule", [
    "Every statement must be traceable to the MASTER CV or to USER_EXTRA_INFO",
    "Never add tools, software, certifications, degrees, job titles, employers, dates, numbers",
    "Never upgrade claim strength",
    "Never rename a past job title",
    "If the job requires something the sources do not support, leave it out",
])
def test_the_editor_keeps_every_honesty_rule(rule):
    assert rule in RULES


def test_the_editor_is_told_to_match_the_role_fix_mistakes_and_suggest():
    text = RULES.lower()
    assert "moving a line is not tailoring" in text
    assert "spelling" in text and "grammar" in text
    assert "suggestions" in text


def test_the_reviewer_accepts_language_fixes_but_still_checks_facts():
    assert "spelling, grammar" in REVIEW_PROMPT
    assert "D) exaggerated responsibility" in REVIEW_PROMPT


def test_a_changed_line_is_never_labelled_moved_even_if_the_model_says_so(s):
    # seen in the live run: a corrected line came back labelled "moved"
    out = run(s, [ChangeLogEntry(original=BULLET, adapted=BULLET.replace("Marked", "Reviewed"),
                                 why_faithful="x", kind="moved")])
    assert [e.kind for e in out.change_log] == ["reworded"]
