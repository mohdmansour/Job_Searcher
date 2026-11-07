"""Shared live-test inputs. The teacher CV is parsed by the REAL parser once and saved, so
later runs do not pay for parsing again (delete the json to re-parse)."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jobcv.agents.parser import parse_cv
from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.cv.ingest import extract_cv_text
from jobcv.schemas import CV
from jobcv.sources.linkedin_apify import map_item

FX = Path(__file__).parents[1] / "fixtures"


@pytest.fixture(scope="session")
def settings():
    return Settings()


@pytest.fixture(scope="session")
def teacher(settings) -> tuple[CV, str]:
    raw = extract_cv_text((FX / "cv_teacher_en.pdf").read_bytes(), settings).text
    cached = FX / "parsed_teacher_en.json"
    if cached.exists():
        return CV.model_validate_json(cached.read_text(encoding="utf-8")), raw
    cv = parse_cv(raw, "en", settings, CostMeter(settings))
    cached.write_text(cv.model_dump_json(indent=2), encoding="utf-8")
    return cv, raw


@pytest.fixture(scope="session")
def qa_job():
    items = json.loads((FX / "apify_bebity_5jobs.json").read_text(encoding="utf-8"))["items"]
    item = next(i for i in items if i["title"].startswith("Jr. Quality Assurance"))
    return map_item(item, datetime.now(UTC))
