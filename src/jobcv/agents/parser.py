"""CV Parser agent: raw CV text -> structured CV JSON. Strong model. Adds nothing."""

from jobcv.agents.base import AgentSpec, LLMCall, run_agent
from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.schemas import CV
from jobcv.text import normalize

SPEC = AgentSpec(
    name="parser",
    role="CV data extractor",
    goal="Convert CV text into structured JSON with perfect fidelity to the source text.",
    backstory="You transcribe documents into data. You never add, infer, improve or translate.",
    strong=True,
)

PROMPT = """Convert the CV text below into the JSON structure you are given.

RULES (all mandatory):
1. Use ONLY information written in the CV text. Do not add, infer, guess, complete or improve anything.
2. Copy text as written. Keep the original language (Arabic stays Arabic, English stays English).
   Do not translate. Do not fix wording. Do not merge or split bullets.
3. Copy job titles, employer names, dates and numbers EXACTLY as written (e.g. "Sep 2019 – Present").
4. If a field is not in the text, leave it empty ("" or []). Never invent a placeholder.
5. Put each section where it belongs: work history -> experience (title, employer, location, start,
   end, bullets); degrees -> education; listed skills/tools -> skills; certificates -> certifications;
   spoken languages -> languages; anything else (awards, volunteering, interests) -> other.
6. The text may contain OCR noise (stray symbols). Copy readable text; skip pure noise characters.
   Never guess what a garbled word was meant to be.

CV TEXT:
<<<
{cv_text}
>>>"""


def parse_cv(
    raw_text: str, language: str, settings: Settings, meter: CostMeter, llm: LLMCall | None = None
) -> CV:
    cv, _ = run_agent(SPEC, PROMPT.format(cv_text=raw_text), CV, settings, meter, llm=llm)
    return cv.model_copy(update={"language": language})  # code decides language, not the LLM


def unsupported_by_text(cv: CV, raw_text: str) -> list[str]:
    """Fact fields (titles, employers, degrees, institutions, skills, certifications) that do
    not appear in the raw text. Should be empty; anything here means the parser added it."""
    haystack = normalize(raw_text).replace(" ", "")
    facts = (
        [e.title for e in cv.experience] + [e.employer for e in cv.experience]
        + [d.degree for d in cv.education] + [d.institution for d in cv.education]
        + cv.skills + cv.certifications
    )
    return [f for f in facts if f and normalize(f).replace(" ", "") not in haystack]
