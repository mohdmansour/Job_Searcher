from jobcv.pipeline.tailor_loop import drop_flagged_summary_sentences as clean
from jobcv.schemas import CV, ChangeLogEntry, Violation

MASTER_SUMMARY = "I am a tester."
SUMMARY = "Tester with manual experience. Skilled at Selenium daily. Detail-oriented and careful."


def cv(summary: str) -> CV:
    return CV.model_validate({"language": "en", "summary": summary})


def flag(text: str) -> Violation:
    return Violation(adapted_text=text, problem="E", explanation="x", suggested_fix="remove")


def log() -> list[ChangeLogEntry]:
    return [ChangeLogEntry(original=MASTER_SUMMARY, adapted=SUMMARY, why_faithful="same")]


def run(*violations):
    return clean(cv(MASTER_SUMMARY), cv(SUMMARY), list(violations), log())


def test_only_the_flagged_sentence_goes():
    final, left, _ = run(flag("Selenium daily"))
    assert final.summary == "Tester with manual experience. Detail-oriented and careful."
    assert left == []


def test_the_change_log_follows_the_new_summary():
    final, _, new_log = run(flag("Selenium daily"))
    assert new_log[0].adapted == final.summary and new_log[0].original == MASTER_SUMMARY


def test_violations_elsewhere_still_warn_the_user():
    bullet = flag("Led a team of ten")
    final, left, _ = run(flag("Selenium daily"), bullet)
    assert "Selenium" not in final.summary
    assert left == [bullet]


def test_no_summary_problem_changes_nothing():
    bullet = flag("Led a team of ten")
    final, left, new_log = run(bullet)
    assert final.summary == SUMMARY and left == [bullet] and new_log == log()


def test_a_whole_summary_flagged_with_a_label_falls_back_to_the_users_own():
    # seen live: adapted_text was 'summary: "<the entire summary>"'
    final, left, new_log = run(flag(f'summary: "{SUMMARY}"'))
    assert final.summary == MASTER_SUMMARY and left == []
    assert new_log == []


def test_arabic_sentences_are_split():
    arabic = "محاسب بخبرة عملية. هل تجيد SAP؟ دقيق في العمل."
    final, left, _ = clean(cv("نص"), cv(arabic), [flag("تجيد SAP")], [])
    assert final.summary == "محاسب بخبرة عملية. دقيق في العمل." and left == []
