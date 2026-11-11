"""Structured CV and the input/output contracts of the four LLM steps."""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field


class Contact(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    title: str = ""  # never renamed by the editor
    employer: str = ""
    location: str = ""
    start: str = ""  # kept verbatim as written in the CV
    end: str = ""
    bullets: list[str] = Field(default_factory=list)


class Education(BaseModel):
    degree: str = ""
    institution: str = ""
    start: str = ""
    end: str = ""
    details: list[str] = Field(default_factory=list)


class LanguageSkill(BaseModel):
    language: str
    level: str = ""


class CV(BaseModel):
    language: Literal["en", "ar"] = "en"
    contact: Contact = Field(default_factory=Contact)
    summary: str = ""
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[LanguageSkill] = Field(default_factory=list)
    other: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    score: int = Field(ge=0, le=100)
    reasons: list[str]
    matched_skills: list[str]
    gaps: list[str]


class ChangeLogEntry(BaseModel):
    original: str
    adapted: str
    why_faithful: str
    # fixed: language corrected only; reworded: wording changed for the job; moved: same text,
    # new place (set by code when the text is unchanged)
    kind: Literal["fixed", "reworded", "moved"] = "reworded"


class Suggestion(BaseModel):
    """One thing only the candidate can confirm. "add": they can tick it and the CV is made again
    with it; "tip": advice about the master CV itself (e.g. a typo in a skill name)."""

    label: str  # the thing itself, e.g. "Python" or "Completed the Bachelor of Cyber Security"
    text: str  # the full suggestion, e.g. "If you use Python at work, add it with examples."
    kind: Literal["add", "tip"] = "add"

    @staticmethod
    def from_any(value: "Suggestion | dict | str") -> "Suggestion":
        """Results made before suggestions had labels stored plain text."""
        if isinstance(value, str):
            return Suggestion(label=value, text=value)
        return Suggestion.model_validate(value)


Suggestions = Annotated[
    list[Suggestion],
    BeforeValidator(lambda items: [Suggestion.from_any(i) for i in items or []]),
]


class EditResult(BaseModel):
    tailored_cv: CV
    change_log: list[ChangeLogEntry] = Field(default_factory=list)
    # what only the candidate can add or fix (missing dates, results without numbers, ...)
    suggestions: Suggestions = Field(default_factory=list)


class Violation(BaseModel):
    adapted_text: str
    problem: Literal["A", "B", "C", "D", "E"]
    explanation: str
    suggested_fix: str


class ReviewResult(BaseModel):
    status: Literal["PASS", "FAIL"]
    violations: list[Violation] = Field(default_factory=list)
