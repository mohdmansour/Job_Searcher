"""Match Scorer agent (cheap model): CV JSON + job description -> honest 0-100 match.
Runs once per job BEFORE any editing. No score is ever computed after tailoring."""

from collections.abc import Callable
from dataclasses import dataclass

from jobcv.agents.base import AgentOutputError, AgentSpec, LLMCall, run_agent
from jobcv.config import Settings
from jobcv.cost.meter import CostCapExceeded, CostMeter
from jobcv.schemas import CV, Job, MatchResult

MAX_JOB_CHARS = 8_000  # long postings are mostly boilerplate; caps cost per job

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
Write reasons and gaps in the CV's language ({cv_language}).

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
    return result


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
