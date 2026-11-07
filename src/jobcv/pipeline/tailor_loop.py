"""Edit -> review loop for ONE job. Plain code decides the flow; agents only transform data.

FAIL -> violations go back to the Editor as reviewer_feedback (fix exactly those) -> review
again. At most `max_review_attempts` reviews. If still FAIL, the latest version is delivered
with warning=True and the remaining violations.
"""

import logging

from pydantic import BaseModel, Field

from jobcv.agents.base import LLMCall
from jobcv.agents.editor import edit_cv
from jobcv.agents.reviewer import review_cv
from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.schemas import CV, ChangeLogEntry, Job, Violation

log = logging.getLogger(__name__)


class TailorOutcome(BaseModel):
    job_id: str
    tailored_cv: CV
    change_log: list[ChangeLogEntry] = Field(default_factory=list)
    review_status: str  # PASS | FAIL
    attempts: int
    warning: bool
    remaining_violations: list[Violation] = Field(default_factory=list)


def tailor_for_job(
    master: CV,
    raw_text: str,
    job: Job,
    settings: Settings,
    meter: CostMeter,
    extra_info: str = "",
    llm: LLMCall | None = None,
) -> TailorOutcome:
    feedback: list[Violation] | None = None
    previous: CV | None = None
    for attempt in range(1, settings.max_review_attempts + 1):
        edit = edit_cv(master, job, settings, meter, extra_info=extra_info,
                       feedback=feedback, previous=previous, llm=llm)
        review = review_cv(master, raw_text, edit.tailored_cv, settings, meter,
                           extra_info=extra_info, llm=llm)
        log.info("job %s attempt %d review=%s violations=%d", job.id, attempt, review.status,
                 len(review.violations))
        if review.status == "PASS":
            return TailorOutcome(job_id=job.id, tailored_cv=edit.tailored_cv,
                                 change_log=edit.change_log, review_status="PASS",
                                 attempts=attempt, warning=False)
        feedback, previous = review.violations, edit.tailored_cv
    return TailorOutcome(job_id=job.id, tailored_cv=edit.tailored_cv, change_log=edit.change_log,
                         review_status="FAIL", attempts=settings.max_review_attempts,
                         warning=True, remaining_violations=review.violations)
