from jobcv.agents.base import LLMReply
from jobcv.agents.parser import parse_cv, unsupported_by_text
from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.schemas import CV, Education, Experience, Usage

RAW = """Sarah Thompson
Primary School Teacher — Oakfield Primary School (Sep 2019 – Present)
- Marked weekly work.
PGCE Primary Education — University of Manchester
Skills: Lesson planning; Microsoft Excel"""


def test_parser_sends_text_and_forces_detected_language(tmp_path):
    s = Settings(_env_file=None, data_dir=tmp_path)
    seen = {}

    def llm(spec, model, prompt, out):
        seen["prompt"], seen["model"] = prompt, model
        return LLMReply(raw="", parsed=CV(language="en", summary="x"), usage=Usage())

    cv = parse_cv(RAW, "ar", s, CostMeter(s), llm=llm)
    assert "Oakfield Primary School" in seen["prompt"] and "Do not add" in seen["prompt"]
    assert seen["model"] == "gpt-5.4"
    assert cv.language == "ar"


def test_unsupported_by_text_catches_added_facts():
    cv = CV(
        experience=[Experience(title="Primary School Teacher", employer="Oakfield Primary School")],
        education=[Education(degree="PGCE Primary Education", institution="University of Manchester")],
        skills=["Lesson planning", "Microsoft Excel", "Selenium"],
        certifications=["ISTQB Foundation"],
    )
    assert unsupported_by_text(cv, RAW) == ["Selenium", "ISTQB Foundation"]


def test_unsupported_by_text_ignores_case_spacing_and_punctuation():
    cv = CV(skills=["lesson  planning", "MICROSOFT EXCEL."])
    assert unsupported_by_text(cv, RAW) == []
