"""Shared runner for the four CrewAI LLM steps.

Each step is a plain function: input model -> prompt -> one CrewAI Agent call -> output model.
Agents get NO tools: they cannot call Apify or decide the workflow; code does.

Privacy: CrewAI telemetry/tracing are switched off before CrewAI is imported, and CrewAI's
console panels are silenced, so CV content only ever goes to OpenAI and never to logs.
"""

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from jobcv.config import Settings
from jobcv.cost.meter import CostMeter
from jobcv.schemas import Usage

for _var in ("CREWAI_DISABLE_TELEMETRY", "CREWAI_DISABLE_TRACKING", "OTEL_SDK_DISABLED"):
    os.environ[_var] = "true"
os.environ["CREWAI_TRACING_ENABLED"] = "false"

log = logging.getLogger(__name__)


class AgentOutputError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentSpec:
    name: str  # parser | scorer | editor | reviewer (also the cost-meter key)
    role: str
    goal: str
    backstory: str
    strong: bool  # True -> settings.strong_model, False -> settings.cheap_model


@dataclass
class LLMReply:
    raw: str
    parsed: BaseModel | None
    usage: Usage


LLMCall = Callable[[AgentSpec, str, str, type[BaseModel]], LLMReply]


def crewai_call(settings: Settings) -> LLMCall:
    """The real LLM call: one CrewAI Agent, no tools, structured output."""

    def call(spec: AgentSpec, model: str, prompt: str, out: type[BaseModel]) -> LLMReply:
        from crewai import LLM, Agent
        from crewai.events.event_listener import event_listener

        event_listener.formatter.verbose = False  # CrewAI forces console panels on
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        llm = LLM(model=f"openai/{model}", api_key=settings.openai_api_key.get_secret_value(),
                  timeout=settings.llm_timeout_secs, max_retries=settings.llm_max_retries)
        agent = Agent(role=spec.role, goal=spec.goal, backstory=spec.backstory, llm=llm,
                      tools=[], verbose=False, allow_delegation=False)
        result = agent.kickoff(prompt, response_format=out)
        m = result.usage_metrics or {}
        usage = Usage(
            input_tokens=int(m.get("prompt_tokens", 0)),
            cached_input_tokens=int(m.get("cached_prompt_tokens", 0)),
            output_tokens=int(m.get("completion_tokens", 0)),
        )
        return LLMReply(raw=result.raw or "", parsed=result.pydantic, usage=usage)

    return call


def run_agent[T: BaseModel](
    spec: AgentSpec,
    prompt: str,
    out: type[T],
    settings: Settings,
    meter: CostMeter,
    llm: LLMCall | None = None,
) -> tuple[T, Usage]:
    """Call the agent; validate its JSON; retry once on invalid output. Checks the cost cap
    before each call and bills every call (including failed ones) to the meter."""
    llm = llm or crewai_call(settings)
    model = settings.strong_model if spec.strong else settings.cheap_model
    total = Usage()
    for attempt in (1, 2):
        meter.check_llm(spec.name, model)
        reply = llm(spec, model, prompt, out)
        meter.add_llm(spec.name, model, reply.usage)
        total = total + reply.usage
        try:
            if isinstance(reply.parsed, out):
                result = reply.parsed
            else:
                result = out.model_validate_json(_strip_fences(reply.raw))
        except ValidationError:
            log.warning("agent %s returned invalid JSON (attempt %d)", spec.name, attempt)
            continue
        log.info("agent %s ok: in=%d out=%d tokens", spec.name, total.input_tokens,
                 total.output_tokens)
        return result, total
    raise AgentOutputError(f"agent {spec.name} returned invalid output twice")


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()
