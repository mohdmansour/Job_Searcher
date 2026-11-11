"""Match Scorer agent (cheap model): CV JSON + job description -> honest 0-100 match.
Runs once per job BEFORE any editing. No score is ever computed after tailoring."""

from collections.abc import Callable
from dataclasses import dataclass

from jobcv.agents.base import AgentOutputError, AgentSpec, LLMCall, run_agent
from jobcv.config import Settings
from jobcv.cost.meter import CostCapExceeded, CostMeter
from jobcv.schemas import CV, Job, MatchResult

MAX_JOB_CHARS = 8_000  # long postings are mostly boilerplate; caps cost per job
MAX_MISSING = 10
MAX_MISSING_CHARS = 60

SPEC = AgentSpec(
    name="scorer",
    role="Honest recruiter",
    goal="Judge how well a candidate's real experience matches a job, without flattery.",
    backstory="You screen CVs for hiring managers who punish inflated matches.",
    strong=False,
)

PROMPT = """Score how well this candidate's CV matches the job. Be honest and strict.

SCORING:
- 80-100: already does this job or a very close one; meets nearly all hard requirements.
- 50-79: related role; meets several core requirements; some real gaps.
- 20-49: only transferable skills; most core requirements missing.
- 0-19: different profession; hard requirements (tools, degrees, certifications, years) missing.
Transferable skills (attention to detail, report writing) never make up for missing core
requirements. Count only what the CV actually states.

Return:
- score (0-100)
- reasons: 2-4 short sentences explaining the score
- matched_skills: requirements of the job that the CV clearly shows (CV wording)
- gaps: important job requirements the CV does not show. Be specific and complete.
- missing_skills: up to 10 skills, tools, methods or qualifications this job asks for that the
  CV does not show, ONE per item in 1-4 words (e.g. "Python", "VLANs", "Firewall management",
  "ISTQB certification"), most important first. Never several in one item. Empty if none.
Write reasons, gaps and missing_skills in the CV's language ({cv_language}).

CV (JSON):
{cv_json}

JOB: {title} at {company} ({location})
DESCRIPTION:
<<<
{description}
>>>"""


@dataclass
class RankedJob:
    job: Job
    match: MatchResult | None
    error: str | None = None


def score_job(cv: CV, job: Job, settings: Settings, meter: CostMeter,
              llm: LLMCall | None = None) -> MatchResult:
    prompt = PROMPT.format(
        cv_language="Arabic" if cv.language == "ar" else "English",
        cv_json=cv.model_dump_json(exclude={"contact"}),  # contact details are not needed
        title=job.title, company=job.company, location=job.location,
        description=job.description[:MAX_JOB_CHARS],
    )
    result, _ = run_agent(SPEC, prompt, MatchResult, settings, meter, llm=llm)
    return result.model_copy(update={"missing_skills": _clean_missing(result.missing_skills)})


def _clean_missing(items: list[str]) -> list[str]:
    """Model output: trimmed, without blanks or repeats, short, and at most MAX_MISSING."""
    out: list[str] = []
    for item in items:
        text = " ".join(item.split())[:MAX_MISSING_CHARS].strip()
        if text and text.casefold() not in {o.casefold() for o in out}:
            out.append(text)
    return out[:MAX_MISSING]


def rank_jobs(cv: CV, jobs: list[Job], settings: Settings, meter: CostMeter,
              llm: LLMCall | None = None,
              check: Callable[[], None] = lambda: None) -> list[RankedJob]:
    """Score every job, best first. A job whose scoring failed is kept, last, with an error.
    CostCapExceeded is not caught: the run must stop. `check` runs before each job and may
    raise to stop the run."""
    ranked = []
    for job in jobs:
        check()
        try:
            ranked.append(RankedJob(job, score_job(cv, job, settings, meter, llm=llm)))
        except CostCapExceeded:
            raise
        except Exception as e:  # noqa: BLE001 - one bad job (timeout, bad JSON) must not sink the run
            msg = str(e) if isinstance(e, AgentOutputError) else type(e).__name__
            ranked.append(RankedJob(job, None, msg))
    return sorted(ranked, key=lambda r: r.match.score if r.match else -1, reverse=True)
