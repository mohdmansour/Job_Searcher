from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class Country(StrEnum):
    """Fixed country list (dropdown). Values are the English names LinkedIn understands.
    No regions, no 'worldwide' — one country per search by design."""

    # Gulf
    UAE = "United Arab Emirates"
    SAUDI_ARABIA = "Saudi Arabia"
    QATAR = "Qatar"
    KUWAIT = "Kuwait"
    BAHRAIN = "Bahrain"
    OMAN = "Oman"
    # Levant + Egypt
    JORDAN = "Jordan"
    LEBANON = "Lebanon"
    IRAQ = "Iraq"
    EGYPT = "Egypt"
    # Western Europe + UK
    GERMANY = "Germany"
    FRANCE = "France"
    NETHERLANDS = "Netherlands"
    BELGIUM = "Belgium"
    SPAIN = "Spain"
    ITALY = "Italy"
    PORTUGAL = "Portugal"
    SWITZERLAND = "Switzerland"
    AUSTRIA = "Austria"
    IRELAND = "Ireland"
    SWEDEN = "Sweden"
    DENMARK = "Denmark"
    NORWAY = "Norway"
    FINLAND = "Finland"
    UNITED_KINGDOM = "United Kingdom"
    # North America
    UNITED_STATES = "United States"
    CANADA = "Canada"


class SearchQuery(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    country: Country
    cities: list[str] = Field(default_factory=list, max_length=10)
    remote: bool = False
    max_results: int = Field(default=25, ge=1, le=200)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title is empty")
        return v

    @field_validator("cities")
    @classmethod
    def _clean_cities(cls, v: list[str]) -> list[str]:
        return [c.strip() for c in v if c and c.strip()]


class Job(BaseModel):
    """Unified job schema. Every source maps to this; nothing downstream reads raw source data."""

    id: str
    source: str
    title: str
    company: str
    location: str
    remote: bool
    description: str
    url: str
    posted_at: AwareDatetime | None
    fetched_at: AwareDatetime
    language: Literal["en", "ar", "other"] = "en"


class SearchResult(BaseModel):
    jobs: list[Job]
    last_updated: datetime
    from_cache: bool
    apify_cost_usd: float = 0.0
