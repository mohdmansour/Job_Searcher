"""CV Editor agent (strong model): tailor the master CV to one job WITHOUT inventing anything."""

from jobcv.agents.base import AgentSpec, LLMCall, run_agent
from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.schemas import CV, EditResult, Job, Violation

MAX_JOB_CHARS = 8_000

SPEC = AgentSpec(
    name="editor",
    role="Faithful CV editor",
    goal="Tailor a CV to a job using only facts that exist in the candidate's own sources.",
    backstory=("You are an ethical career editor. You would rather leave a requirement unmet "
               "than write one word the candidate cannot prove."),
    strong=True,
)

RULES = """HARD RULES (breaking any one is a failure):
1. Every statement must be traceable to the MASTER CV or to USER_EXTRA_INFO. Nothing else is a valid source.
2. Never add tools, software, certifications, degrees, job titles, employers, dates, numbers, or achievements that are not in the sources.
3. Never upgrade claim strength ("helped" must not become "led"; "used" must not become "expert"). Never invent metrics.
4. Never rename a past job title. Bullets beneath it can be reworded. Keep employer names and dates exactly as written.
5. If the job requires something the sources do not support, leave it out. Do not hint or imply it.

GOAL: make this CV match the target job as closely as the candidate's real experience allows.
Moving a line is not tailoring on its own. Work through the whole CV:
- Summary: rewrite it for this role, leading with the real experience, skills and strengths the
  job asks for.
- Bullets: rewrite every bullet whose activity matches something the job asks for in the job's
  own terms, with a clear action verb and the most relevant part first. Same activity, same
  scope, same strength (rule 3).
- Order: put the most relevant bullets and skills first; cut what doesn't help for this job.
- Fix mistakes in everything you keep: spelling, grammar, punctuation, tense (past roles in the
  past tense, a current role in the present), repeated words and unclear phrasing. A correction
  must not change any fact. Skill, certification and degree names are the exception: keep them
  exactly as written and mention a misspelled one in SUGGESTIONS.

ALLOWED:
- Reword bullets using the job's terminology ONLY when the underlying activity is genuinely the same.
- Reorder sections and bullets by relevance to the job.
- Cut content that is irrelevant to the job (you may drop bullets; keep every job entry).
- Rewrite the summary honestly around real transferable strengths.
- Use the job's exact keywords only where real experience matches (for ATS).
- Skills, certifications and degrees: keep each item worded EXACTLY as in the master CV
  (you may reorder or remove items, never rename or add them).

SUMMARY: write natural, complete sentences drawn from the whole CV (work history, skills,
education). Never put dates, institution names or other copied CV fields in it. Say a degree was
completed only if the sources say so; otherwise leave it out or write "background in <field>".

LANGUAGE: write the whole CV in {cv_language} (the master CV's language), even if the job
description is in another language. Do not translate titles, employers or dates.

CHANGE LOG: for every fixed, reworded or moved item give: original (exact master text),
adapted (your text), why_faithful (why the activity is the same and nothing was added), and
kind: "fixed" (only spelling, grammar, punctuation or tense corrected), "reworded" (wording
changed for the job) or "moved" (same text, new position). Do not include unchanged items.

SUGGESTIONS: up to 8 short, specific suggestions, in {cv_language}, for what only the candidate
can fix: missing dates, results without numbers, unexplained abbreviations, a requirement of this
job the sources don't show, a misspelled skill name. Never state anything as a fact the sources
don't show: write "If you have ..., add it." Return an empty list if there is nothing useful."""

PROMPT = """{rules}

MASTER CV (JSON):
{master}

USER_EXTRA_INFO (also a valid source; may be empty):
<<<
{extra}
>>>

TARGET JOB: {title} at {company}
JOB DESCRIPTION:
<<<
{description}
>>>
{feedback_block}
Return the complete tailored CV and the change log."""

FEEDBACK = """
A strict fact-checker REJECTED your previous version. Fix EXACTLY these violations and change
nothing else (keep every other part of the previous version as it is):
{violations}

Each "Fix" is a hint, not text to paste. In the summary, rewrite or remove the rejected phrase so
every sentence still reads naturally, and never insert dates, institution names or other copied
CV fields. In the change log, list only what you changed in this round.

YOUR PREVIOUS VERSION (JSON):
{previous}
"""


def edit_cv(
    master: CV,
    job: Job,
    settings: Settings,
    meter: CostMeter,
    extra_info: str = "",
    feedback: list[Violation] | None = None,
    previous: CV | None = None,
    llm: LLMCall | None = None,
) -> EditResult:
    feedback_block = ""
    if feedback:
        lines = "\n".join(
            f"- [{v.problem}] \"{v.adapted_text}\": {v.explanation} Fix: {v.suggested_fix}"
            for v in feedback
        )
        feedback_block = FEEDBACK.format(
            violations=lines,
            previous=previous.model_dump_json(exclude={"contact"}) if previous else "{}",
        )
    prompt = PROMPT.format(
        rules=RULES.format(cv_language="Arabic" if master.language == "ar" else "English"),
        master=master.model_dump_json(exclude={"contact"}),
        extra=extra_info.strip(),
        title=job.title, company=job.company,
        description=job.description[:MAX_JOB_CHARS],
        feedback_block=feedback_block,
    )
    result, _ = run_agent(SPEC, prompt, EditResult, settings, meter, llm=llm)
    # Code, not the model, owns identity fields: contact and language never change.
    cv = result.tailored_cv.model_copy(update={"contact": master.contact,
                                               "language": master.language})
    return result.model_copy(update={"tailored_cv": cv})
