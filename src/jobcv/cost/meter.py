"""Cost meter: estimate before a run, enforce the hard cap before each billable call,
and record what was actually spent. The base for billing later (no payment code here)."""

from pydantic import BaseModel, Field

from jobcv.config import Settings
from jobcv.schemas import Usage


class CostCapExceeded(RuntimeError):
    pass


def llm_cost(s: Settings, model: str, u: Usage) -> float:
    if model not in s.model_prices:
        raise KeyError(f"no price configured for model {model!r} (JOBCV_MODEL_PRICES)")
    p = s.model_prices[model]
    uncached = max(u.input_tokens - u.cached_input_tokens, 0)  # cached are part of input
    return (
        uncached * p.input_per_1m
        + u.cached_input_tokens * p.cached_input_per_1m
        + u.output_tokens * p.output_per_1m
    ) / 1_000_000


class Estimate(BaseModel):
    apify_usd: float
    llm_usd: float
    total_usd: float
    cap_usd: float
    within_cap: bool


class CostRecord(BaseModel):
    apify_usd: float = 0.0
    llm_usd_by_agent: dict[str, float] = Field(default_factory=dict)
    tokens_by_agent: dict[str, Usage] = Field(default_factory=dict)
    actual_cost_usd: float = 0.0  # what we paid
    markup: float = 1.0
    price_to_user_usd: float = 0.0  # what the user is charged; profit = difference


class CostMeter:
    def __init__(self, settings: Settings):
        self.s = settings
        self._apify = 0.0
        self._llm: dict[str, float] = {}
        self._tokens: dict[str, Usage] = {}

    # ---------- estimates ----------
    def _call_estimate(self, agent: str, model: str) -> float:
        tin, tout = self.s.token_estimates[agent]
        return llm_cost(self.s, model, Usage(input_tokens=tin, output_tokens=tout))

    def _estimate(self, apify_usd: float, llm_usd: float) -> Estimate:
        total = apify_usd + llm_usd
        cap = self.s.max_cost_per_run_usd
        return Estimate(apify_usd=apify_usd, llm_usd=llm_usd, total_usd=total, cap_usd=cap,
                        within_cap=total <= cap)

    def estimate_search(self, n_jobs: int, apify_usd: float) -> Estimate:
        """Worst case: cache miss for all jobs + one scorer call per job."""
        return self._estimate(apify_usd, n_jobs * self._call_estimate("scorer", self.s.cheap_model))

    def estimate_tailor(self, n_jobs: int) -> Estimate:
        """Worst case: every job uses all review attempts (edit + review each time)."""
        per_attempt = (self._call_estimate("editor", self.s.strong_model)
                       + self._call_estimate("reviewer", self.s.strong_model))
        return self._estimate(0.0, n_jobs * self.s.max_review_attempts * per_attempt)

    # ---------- enforcement ----------
    @property
    def spent(self) -> float:
        return self._apify + sum(self._llm.values())

    def check(self, usd: float) -> None:
        cap = self.s.max_cost_per_run_usd
        if self.spent + usd > cap + 1e-12:
            raise CostCapExceeded(
                f"run would cost ${self.spent + usd:.4f}, cap is ${cap:.2f}"
            )

    def check_llm(self, agent: str, model: str) -> None:
        self.check(self._call_estimate(agent, model))

    # ---------- actuals ----------
    def add_apify(self, usd: float) -> None:
        self._apify += usd

    def add_llm(self, agent: str, model: str, usage: Usage) -> None:
        self._llm[agent] = self._llm.get(agent, 0.0) + llm_cost(self.s, model, usage)
        self._tokens[agent] = self._tokens.get(agent, Usage()) + usage

    def record(self) -> CostRecord:
        actual = self.spent
        return CostRecord(
            apify_usd=self._apify,
            llm_usd_by_agent=dict(self._llm),
            tokens_by_agent=dict(self._tokens),
            actual_cost_usd=actual,
            markup=self.s.markup,
            price_to_user_usd=actual * self.s.markup,
        )
