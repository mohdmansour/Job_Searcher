"""CV Reviewer: strict fact-checker. LLM review (strong model) + deterministic code checks.

The code checks cannot be argued with:
  A - skills/certifications/degrees not found in the sources
  B - job titles, employers or dates that differ from the master CV, or job entries that
      do not exist in it
  C - numbers that do not appear in the sources
The LLM covers what code cannot judge: D (exaggeration) and E (changed meaning), plus A-C
in free text.
"""

import re

from jobcv.agents.base import AgentSpec, LLMCall, run_agent
from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.schemas import CV, ReviewResult, Violation
from jobcv.text import normalize

SPEC = AgentSpec(
    name="reviewer",
    role="Strict CV fact-checker",
    goal="Find every statement in an adapted CV that is not supported by the candidate's sources.",
    backstory=("You audit CVs for fraud. You do not improve writing. You only compare facts. "
               "When in doubt, you flag."),
    strong=True,
)

PROMPT = """Compare the ADAPTED CV against the SOURCES and report every violation.
You are a fact-checker, not an editor: do not suggest style improvements.

VIOLATION TYPES:
A) new tools, technologies, methods, certifications or degrees not in the sources
B) new or changed job titles, employers, dates or durations
C) invented or changed numbers
D) exaggerated responsibility or seniority (e.g. "helped" -> "led", "used" -> "expert")
E) reworded bullets whose meaning no longer matches the original activity

NOT VIOLATIONS (the editor is allowed to do these):
- Rewording when the underlying activity is the same, including using the job's vocabulary.
- Reordering sections, bullets or skills; cutting or omitting content.
- Rewriting the summary around strengths the sources show (e.g. "careful marker of pupils'
  work" -> "detail-oriented"). A different focus or emphasis is NOT a violation; only a claim
  the sources do not support is.
E applies only when a bullet now describes a DIFFERENT activity than the original.
Check the summary, every bullet, skills, certifications and education, field by field.
When in doubt, flag it. Each violation: adapted_text (exact text from the adapted CV), problem
(A-E), explanation, suggested_fix (a faithful replacement or "remove").
status = "PASS" only if there are no violations; otherwise "FAIL".

SOURCES
1) MASTER CV (JSON):
{master}
2) MASTER CV RAW TEXT (the original document; use it to double-check):
<<<
{raw}
>>>
3) USER_EXTRA_INFO:
<<<
{extra}
>>>

ADAPTED CV (JSON) TO CHECK:
{adapted}"""


def review_cv(master: CV, raw_text: str, adapted: CV, settings: Settings, meter: CostMeter,
              extra_info: str = "", llm: LLMCall | None = None) -> ReviewResult:
    prompt = PROMPT.format(
        master=master.model_dump_json(exclude={"contact"}), raw=raw_text,
        extra=extra_info.strip(), adapted=adapted.model_dump_json(exclude={"contact"}),
    )
    llm_review, _ = run_agent(SPEC, prompt, ReviewResult, settings, meter, llm=llm)
    violations = list(llm_review.violations)
    seen = {normalize(v.adapted_text) for v in violations}
    for v in code_violations(master, raw_text, adapted, extra_info):
        if normalize(v.adapted_text) not in seen:
            violations.append(v)
    return ReviewResult(status="FAIL" if violations else "PASS", violations=violations)


# ---------------- deterministic checks ----------------

def _squash(text: str) -> str:
    return normalize(text).replace(" ", "")


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text.translate(_ARABIC_DIGITS)))


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _cv_text(cv: CV) -> list[str]:
    texts = [cv.summary, *cv.skills, *cv.certifications, *cv.other]
    for e in cv.experience:
        texts += [e.title, e.employer, e.location, e.start, e.end, *e.bullets]
    for d in cv.education:
        texts += [d.degree, d.institution, d.start, d.end, *d.details]
    texts += [f"{lang.language} {lang.level}" for lang in cv.languages]
    return [t for t in texts if t]


def code_violations(master: CV, raw_text: str, adapted: CV, extra_info: str = "") -> list[Violation]:
    sources = raw_text + "\n" + extra_info + "\n" + master.model_dump_json()
    hay = _squash(sources)
    out: list[Violation] = []

    # B: every job entry must be an unchanged master entry
    master_jobs = {(_squash(e.title), _squash(e.employer), _squash(e.start), _squash(e.end))
                   for e in master.experience}
    for e in adapted.experience:
        if (_squash(e.title), _squash(e.employer), _squash(e.start), _squash(e.end)) not in master_jobs:
            out.append(Violation(
                adapted_text=f"{e.title} — {e.employer} ({e.start} – {e.end})", problem="B",
                explanation="Job title, employer or dates differ from the master CV.",
                suggested_fix="Use the exact title, employer and dates from the master CV."))

    # A: listed skills / certifications / degrees must exist in the sources
    claimed = adapted.skills + adapted.certifications + [d.degree for d in adapted.education]
    for item in claimed:
        if item and _squash(item) not in hay:
            out.append(Violation(
                adapted_text=item, problem="A",
                explanation="Not found anywhere in the master CV or the user's extra info.",
                suggested_fix="remove"))

    # C: every number must appear in the sources
    source_numbers = _numbers(sources)
    for text in _cv_text(adapted):
        new = _numbers(text) - source_numbers
        if new:
            out.append(Violation(
                adapted_text=text, problem="C",
                explanation=f"Number(s) {', '.join(sorted(new))} do not appear in the sources.",
                suggested_fix="Use only numbers from the master CV, or remove the number."))
    return out
