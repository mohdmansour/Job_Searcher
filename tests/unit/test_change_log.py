from jobcv.agents.editor import FEEDBACK, RULES
from jobcv.agents.reviewer import PROMPT
from jobcv.pipeline.tailor_loop import _squash, merge_change_log
from jobcv.schemas import ChangeLogEntry

MASTER = _squash("I tested the billing app. I wrote weekly reports. Holds nothing else.")


def entry(original, adapted, why="same work"):
    return ChangeLogEntry(original=original, adapted=adapted, why_faithful=why)


def test_first_round_is_kept_as_is():
    log = [entry("I tested the billing app.", "Tested the billing app.")]
    assert merge_change_log([], log, MASTER) == log


def test_a_fix_round_does_not_erase_earlier_changes():
    first = [entry("I tested the billing app.", "Tested the billing app."),
             entry("I wrote weekly reports.", "Wrote weekly reports.")]
    fix = [entry("Wrote weekly reports.", "Prepared weekly reports.", "fixed")]
    merged = merge_change_log(first, fix, MASTER)
    assert len(merged) == 2
    assert merged[0] == first[0]


def test_a_rewritten_rewrite_still_starts_from_the_users_text():
    first = [entry("I wrote weekly reports.", "Wrote weekly reports.")]
    fix = [entry("Wrote weekly reports.", "Prepared weekly reports.", "fixed")]
    assert merge_change_log(first, fix, MASTER) == [
        entry("I wrote weekly reports.", "Prepared weekly reports.", "fixed")]


def test_a_changed_phrase_updates_the_whole_entry():
    first = [entry("I wrote weekly reports.", "Wrote weekly reports and led the team.")]
    fix = [entry(" and led the team", "", "removed the claim")]
    assert merge_change_log(first, fix, MASTER) == [
        entry("I wrote weekly reports.", "Wrote weekly reports.", "removed the claim")]


def test_a_new_change_to_real_cv_text_is_added():
    first = [entry("I tested the billing app.", "Tested the billing app.")]
    fix = [entry("I wrote weekly reports.", "Wrote weekly reports.")]
    assert len(merge_change_log(first, fix, MASTER)) == 2


def test_text_that_was_never_in_the_cv_is_not_shown_as_the_original():
    # seen live: "Original: Holds a degree in Computer Science", a phrase the model wrote itself
    fix = [entry("Holds a degree in Computer Science", "Background in Computer Science")]
    assert merge_change_log([], fix, MASTER) == []


def test_editor_is_told_how_to_handle_the_summary():
    assert "Never put dates, institution names" in RULES
    assert 'Each "Fix" is a hint, not text to paste' in FEEDBACK


def test_reviewer_gives_usable_fixes_and_counts_all_evidence():
    assert "never copied CV fields or dates" in PROMPT
    assert "Work history and education count" in PROMPT
    assert "only listed supports saying the candidate has that skill" in PROMPT
    assert "no field label" in PROMPT
