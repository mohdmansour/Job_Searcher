"""Edit -> review loop for ONE job. Plain code decides the flow; agents only transform data.

FAIL -> violations go back to the Editor as reviewer_feedback (fix exactly those) -> review
again. At most `max_review_attempts` reviews. If still FAIL, the latest version is delivered
with warning=True and the remaining violations.
"""

import logging
import re
from collections.abc import Callable

from pydantic import BaseModel, Field

from jobcv.agents.base import LLMCall
from jobcv.agents.editor import edit_cv
from jobcv.agents.reviewer import _cv_text, _squash, review_cv
from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.schemas import CV, ChangeLogEntry, Job, Suggestion, Suggestions, Violation

log = logging.getLogger(__name__)

MAX_SUGGESTIONS = 8
MAX_SUGGESTION_CHARS = 300


class TailorOutcome(BaseModel):
    job_id: str
    tailored_cv: CV
    change_log: list[ChangeLogEntry] = Field(default_factory=list)
    review_status: str  # PASS | FAIL
    attempts: int
    warning: bool
    remaining_violations: list[Violation] = Field(default_factory=list)
    suggestions: Suggestions = Field(default_factory=list)


def label_moves(change_log: list[ChangeLogEntry]) -> list[ChangeLogEntry]:
    """The code, not the model, decides what "moved" means: the text is unchanged (only spacing
    ignored, so a fix of one comma or letter is still a fix). A changed line the model called
    "moved" counts as reworded."""
    def kind(e: ChangeLogEntry) -> str:
        if " ".join(e.original.split()) == " ".join(e.adapted.split()):
            return "moved"
        return "reworded" if e.kind == "moved" else e.kind

    return [e.model_copy(update={"kind": kind(e)}) for e in change_log]


MAX_LABEL_CHARS = 80


def clean_suggestions(items: list[Suggestion]) -> list[Suggestion]:
    """Model output: trimmed, without blanks or repeats, short, and at most MAX_SUGGESTIONS."""
    out: list[Suggestion] = []
    seen: set[str] = set()
    for item in items:
        text = " ".join(item.text.split())[:MAX_SUGGESTION_CHARS]
        label = " ".join(item.label.split())[:MAX_LABEL_CHARS] or text[:MAX_LABEL_CHARS]
        if text and label.casefold() not in seen:
            seen.add(label.casefold())
            out.append(Suggestion(label=label, text=text, kind=item.kind))
    return out[:MAX_SUGGESTIONS]


def merge_change_log(
    earlier: list[ChangeLogEntry], latest: list[ChangeLogEntry], master_text: str
) -> list[ChangeLogEntry]:
    """Combine a fix round's log with the log so far. A fix round only lists what it changed,
    and its "original" is often the previous round's wording, not the user's CV: chain those
    back so every entry still starts from the user's real text."""
    log = list(earlier)
    for entry in latest:
        old = _squash(entry.original)
        whole = next((i for i, e in enumerate(log) if old and _squash(e.adapted) == old), None)
        # a phrase found in several entries can't be attributed to one of them
        parts = [i for i, e in enumerate(log) if old and entry.original in e.adapted]
        part = parts[0] if len(parts) == 1 else None
        same = next((i for i, e in enumerate(log) if old and _squash(e.original) == old), None)
        if whole is not None:  # the previous rewrite was rewritten
            log[whole] = entry.model_copy(update={"original": log[whole].original})
        elif part is not None:  # only a phrase of the previous rewrite changed
            log[part] = log[part].model_copy(update={
                "adapted": log[part].adapted.replace(entry.original, entry.adapted),
                "why_faithful": entry.why_faithful})
        elif same is not None:
            log[same] = entry
        elif not old or old in master_text:
            log.append(entry)
    return log


_SENTENCE_END = re.compile(r"(?<=[.!?؟])\s+")


def drop_flagged_summary_sentences(
    master: CV, adapted: CV, violations: list[Violation], change_log: list[ChangeLogEntry]
) -> tuple[CV, list[Violation], list[ChangeLogEntry]]:
    """Last resort after the final review round. Removing sentences can't add a claim, and the
    reviewer accepted the others, so what remains is safe. Falls back to the user's own summary
    if nothing remains. Violations outside the summary are left for the user to see."""
    sentences = [s for s in _SENTENCE_END.split(adapted.summary.strip()) if s]

    def overlaps(sentence: str, phrase: str) -> bool:
        a, b = _squash(sentence), _squash(phrase)
        return bool(a and b) and (b in a or a in b)

    # A problem that also exists outside the summary isn't fixed by removing a sentence.
    elsewhere = _squash(" ".join(_cv_text(adapted.model_copy(update={"summary": ""}))))
    in_summary = [v for v in violations
                  if any(overlaps(s, v.adapted_text) for s in sentences)
                  and _squash(v.adapted_text) not in elsewhere]
    if not in_summary:
        return adapted, violations, change_log
    kept = [s for s in sentences if not any(overlaps(s, v.adapted_text) for v in in_summary)]
    summary = " ".join(kept) or master.summary
    old = _squash(adapted.summary)
    new_log = [e.model_copy(update={"adapted": summary}) if _squash(e.adapted) == old else e
               for e in change_log]
    if not kept:  # back to the user's own text, so that's no longer a change
        new_log = [e for e in new_log if _squash(e.adapted) != _squash(master.summary)]
    remaining = [v for v in violations if v not in in_summary]
    return adapted.model_copy(update={"summary": summary}), remaining, new_log


def tailor_for_job(
    master: CV,
    raw_text: str,
    job: Job,
    settings: Settings,
    meter: CostMeter,
    extra_info: str = "",
    llm: LLMCall | None = None,
    check: Callable[[], None] = lambda: None,  # runs before each LLM step; may raise to stop
) -> TailorOutcome:
    feedback: list[Violation] | None = None
    previous: CV | None = None
    change_log: list[ChangeLogEntry] = []
    suggestions: list[Suggestion] = []  # a fix round may return none: keep the earlier ones
    master_text = _squash(raw_text) + _squash(" ".join(_cv_text(master)))
    for attempt in range(1, settings.max_review_attempts + 1):
        check()
        edit = edit_cv(master, job, settings, meter, extra_info=extra_info,
                       feedback=feedback, previous=previous, llm=llm)
        change_log = merge_change_log(change_log, edit.change_log, master_text)
        check()
        review = review_cv(master, raw_text, edit.tailored_cv, settings, meter,
                           extra_info=extra_info, llm=llm)
        log.info("job %s attempt %d review=%s violations=%d", job.id, attempt, review.status,
                 len(review.violations))
        suggestions = clean_suggestions(edit.suggestions) or suggestions
        if review.status == "PASS":
            return TailorOutcome(job_id=job.id, tailored_cv=edit.tailored_cv,
                                 change_log=label_moves(change_log), review_status="PASS",
                                 attempts=attempt, warning=False, suggestions=suggestions)
        feedback, previous = review.violations, edit.tailored_cv
    final, remaining, change_log = drop_flagged_summary_sentences(
        master, edit.tailored_cv, review.violations, change_log)
    return TailorOutcome(job_id=job.id, tailored_cv=final, change_log=label_moves(change_log),
                         review_status="FAIL" if remaining else "PASS",
                         attempts=settings.max_review_attempts,
                         warning=bool(remaining), remaining_violations=remaining,
                         suggestions=suggestions)
