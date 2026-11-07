import argparse
from pathlib import Path

import pytest

from jobcv.cli import _country, main
from jobcv.config import Settings
from jobcv.pipeline.engine import Engine
from jobcv.schemas import Country
from tests.unit.test_engine import FixtureSource, fake_llm, fake_render

FX = Path(__file__).parents[1] / "fixtures"
ROOT = Path(__file__).parents[2]


def test_country_accepts_name_or_value_case_insensitive():
    assert _country("united arab emirates") is Country.UAE
    assert _country("uae") is Country.UAE
    with pytest.raises(argparse.ArgumentTypeError):
        _country("Middle East")


def test_countries_lists_all(capsys):
    main(["countries"])
    assert "Germany" in capsys.readouterr().out


def test_run_all_end_to_end_offline(tmp_path, capsys):
    s = Settings(_env_file=None, data_dir=tmp_path / "data", tessdata_dir=ROOT / "tessdata")
    engine = Engine(s, source=FixtureSource(), llm=fake_llm, renderer=fake_render,
                    synchronous=True)
    out = tmp_path / "out"
    main(["run-all", str(FX / "cv_teacher_en.pdf"), "--title", "QA Engineer", "--country",
          "UAE", "--max", "4", "--pick", "2", "--out", str(out), "--yes"], engine=engine)
    text = capsys.readouterr().out
    assert "Estimated cost" in text and "Actual cost" in text and "price to user" in text
    assert text.count("review PASS") == 2
    assert len(list(out.glob("*.pdf"))) == 2
