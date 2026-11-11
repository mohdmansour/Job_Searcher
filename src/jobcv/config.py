"""All tunable settings. Values come from env vars (prefix JOBCV_) or `.env`.

Secrets use their conventional names (OPENAI_API_KEY, APIFY_TOKEN) and are SecretStr,
so they never appear in repr/logs.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class ModelPrice(BaseModel):
    """USD per 1M tokens. Update from https://developers.openai.com/api/docs/pricing"""

    input_per_1m: float
    cached_input_per_1m: float
    output_per_1m: float


DEFAULT_MODEL_PRICES = {
    # Read from OpenAI pricing page on 2026-11-08 (standard tier).
    "gpt-5.4": ModelPrice(input_per_1m=2.50, cached_input_per_1m=0.25, output_per_1m=15.00),
    "gpt-5.4-mini": ModelPrice(input_per_1m=0.75, cached_input_per_1m=0.075, output_per_1m=4.50),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JOBCV_", env_file=(".env", "web/.env.local"), env_file_encoding="utf-8",
        extra="ignore",  # web/.env.local: the one place the Clerk keys are kept locally
    )

    # --- secrets ---
    openai_api_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("OPENAI_API_KEY", "JOBCV_OPENAI_API_KEY")
    )
    apify_token: SecretStr | None = Field(
        None, validation_alias=AliasChoices("APIFY_TOKEN", "JOBCV_APIFY_TOKEN")
    )

    clerk_secret_key: SecretStr | None = Field(
        None, validation_alias=AliasChoices("CLERK_SECRET_KEY", "JOBCV_CLERK_SECRET_KEY")
    )
    # optional public key: verifies tokens without calling Clerk
    clerk_jwt_key: str | None = Field(
        None, validation_alias=AliasChoices("CLERK_JWT_KEY", "JOBCV_CLERK_JWT_KEY")
    )
    # sites allowed to use a token: comma-separated or a JSON list in the env var
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # --- LLM (provider is always OpenAI) ---
    strong_model: str = "gpt-5.4"  # CV Parser, CV Editor, CV Reviewer
    cheap_model: str = "gpt-5.4-mini"  # Match Scorer
    model_prices: dict[str, ModelPrice] = Field(default_factory=lambda: dict(DEFAULT_MODEL_PRICES))
    max_review_attempts: int = 3
    llm_timeout_secs: float = 120  # per HTTP call; a hung call was seen live (no reply >10 min)
    llm_max_retries: int = 2  # OpenAI SDK retries on timeout / connection errors
    # (input, output) tokens per call, used ONLY for pre-run estimates: ~2x the real usage
    # measured in the live tests on 2026-11-08 (parser ~1k/0.4k, edit+review round ~$0.023).
    token_estimates: dict[str, tuple[int, int]] = Field(default_factory=lambda: {
        "parser": (2500, 1000),
        "scorer": (3500, 400),
        "editor": (3000, 1500),
        "reviewer": (4000, 600),
    })

    # --- Apify ---
    apify_actor_id: str = "bebity/linkedin-jobs-scraper"
    apify_price_per_job_usd: float = 0.0015  # FREE tier, read 2026-11-08
    apify_price_per_start_usd: float = 0.00005  # charged once per GB of run memory
    apify_memory_gb: int = 2  # the Actor's default; also used in the cost estimate
    apify_timeout_secs: int = 600

    # --- jobs cache ---
    job_cache_ttl_hours: float = 4
    job_max_age_days: int | None = None  # None shows jobs of any age
    incremental_window: str = "r86400"  # smallest date filter the Actor supports (24h)

    # --- cost meter ---
    max_cost_per_run_usd: float = 1.0
    markup: float = 3.0

    # --- CV / privacy ---
    max_cv_pages: int = 15  # a page limit keeps OCR from tying up the server
    max_cv_chars: int = 40_000  # the cost cap uses a fixed size estimate, so size is capped here
    cv_ttl_hours: float = 24
    ocr_min_chars: int = 200  # below this much extracted text, fall back to OCR
    tesseract_cmd: str = "C:/Program Files/Tesseract-OCR/tesseract.exe"  # or "tesseract" on Linux
    tessdata_dir: Path = Path("tessdata")  # holds eng + ara .traineddata (tessdata_best)

    # --- accounts: free allowance and limits (SPEC-accounts) ---
    free_searches: int = 1
    free_tailors: int = 1
    free_max_results: int = 10
    daily_cv_uploads: int = 3
    daily_free_budget_usd: float = 5.0  # all free accounts together; then free use pauses
    # Clerk user ids with no limits (the owner), comma-separated in the env var
    unlimited_user_ids: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("unlimited_user_ids", "allowed_origins", mode="before")
    @classmethod
    def _split_list(cls, v):
        if not isinstance(v, str):
            return v
        if v.strip().startswith("["):
            return json.loads(v)
        return [i.strip() for i in v.split(",") if i.strip()]

    # --- storage ---
    data_dir: Path = Path("data")

    @property
    def jobs_cache_db(self) -> Path:
        return self.data_dir / "jobs_cache.db"  # public job data only

    @property
    def user_db(self) -> Path:
        return self.data_dir / "user.db"  # CVs, runs, scores (personal data)

    @property
    def accounts_db(self) -> Path:
        return self.data_dir / "accounts.db"  # Clerk user ids and counters only

    @property
    def user_files_dir(self) -> Path:
        return self.data_dir / "user"


@lru_cache
def get_settings() -> Settings:
    return Settings()
