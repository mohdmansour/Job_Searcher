"""Real OpenAI calls (small). Run: uv run pytest -m live tests/live/test_parser_live.py -s"""

from pathlib import Path

import pytest

from jobcv.agents.parser import parse_cv, unsupported_by_text
from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.cv.ingest import extract_cv_text

pytestmark = pytest.mark.live
FX = Path(__file__).parents[1] / "fixtures"


@pytest.mark.parametrize("name", ["cv_teacher_en.pdf", "cv_accountant_ar.pdf"])
def test_parser_extracts_without_adding(name):
    s = Settings()
    meter = CostMeter(s)
    ex = extract_cv_text((FX / name).read_bytes(), s)
    cv = parse_cv(ex.text, ex.language, s, meter)
    r = meter.record()
    print(f"\n{name}: lang={cv.language} method={ex.method} jobs={len(cv.experience)} "
          f"skills={len(cv.skills)} cost=${r.actual_cost_usd:.4f} tokens={r.tokens_by_agent['parser']}")
    assert len(cv.experience) == 2
    assert len(cv.education) >= 1
    assert unsupported_by_text(cv, ex.text) == []
    if cv.language == "en":
        assert cv.experience[0].title == "Primary School Teacher"
        assert cv.experience[0].start.startswith("Sep 2019")
        assert not {"selenium", "jira", "sql"} & {k.lower() for k in cv.skills}
    else:
        assert "محاسب" in cv.experience[0].title
