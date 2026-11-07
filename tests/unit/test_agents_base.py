import os

import pytest
from pydantic import BaseModel

from jobcv.agents.base import AgentOutputError, AgentSpec, LLMReply, run_agent
from jobcv.config import Settings
from jobcv.cost.meter import CostCapExceeded, CostMeter
from jobcv.schemas import Usage


class Out(BaseModel):
    word: str


SPEC = AgentSpec(name="scorer", role="r", goal="g", backstory="b", strong=False)


@pytest.fixture
def s(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path)


def test_crewai_telemetry_and_tracing_are_disabled():
    import jobcv.agents.base  # noqa: F401

    for var in ("CREWAI_DISABLE_TELEMETRY", "CREWAI_DISABLE_TRACKING", "OTEL_SDK_DISABLED"):
        assert os.environ[var] == "true"
    assert os.environ["CREWAI_TRACING_ENABLED"] == "false"


def test_returns_parsed_output_and_records_usage(s):
    meter = CostMeter(s)
    calls = []

    def llm(spec, model, prompt, out):
        calls.append(model)
        return LLMReply(raw='{"word":"hi"}', parsed=Out(word="hi"),
                        usage=Usage(input_tokens=100, output_tokens=10))

    result, usage = run_agent(SPEC, "prompt", Out, s, meter, llm=llm)
    assert result.word == "hi" and usage.input_tokens == 100
    assert calls == ["gpt-5.4-mini"]  # scorer uses the cheap model
    assert meter.record().tokens_by_agent["scorer"].output_tokens == 10


def test_strong_agent_uses_strong_model(s):
    seen = []

    def llm(spec, model, prompt, out):
        seen.append(model)
        return LLMReply(raw='{"word":"x"}', parsed=None, usage=Usage())

    run_agent(AgentSpec("editor", "r", "g", "b", strong=True), "p", Out, s, CostMeter(s), llm=llm)
    assert seen == ["gpt-5.4"]


def test_invalid_json_is_retried_once_then_fails(s):
    meter, n = CostMeter(s), []

    def llm(spec, model, prompt, out):
        n.append(1)
        return LLMReply(raw="not json", parsed=None, usage=Usage(input_tokens=5))

    with pytest.raises(AgentOutputError):
        run_agent(SPEC, "p", Out, s, meter, llm=llm)
    assert len(n) == 2
    assert meter.record().tokens_by_agent["scorer"].input_tokens == 10  # both calls billed


def test_cap_is_checked_before_calling(s):
    tight = s.model_copy(update={"max_cost_per_run_usd": 0.0})

    def llm(*a):
        raise AssertionError("must not be called")

    with pytest.raises(CostCapExceeded):
        run_agent(SPEC, "p", Out, tight, CostMeter(tight), llm=llm)


def test_agent_output_is_never_logged(s, caplog):
    secret = "Sarah Thompson secret CV line"

    def llm(spec, model, prompt, out):
        return LLMReply(raw=f'{{"word":"{secret}"}}', parsed=None, usage=Usage())

    caplog.set_level("DEBUG")
    run_agent(SPEC, f"prompt with {secret}", Out, s, CostMeter(s), llm=llm)
    assert secret not in caplog.text
