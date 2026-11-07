"""Structured CV and the input/output contracts of the four LLM steps."""

from typing import Literal

from pydantic import BaseModel, Field


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


class EditResult(BaseModel):
    tailored_cv: CV
    change_log: list[ChangeLogEntry] = Field(default_factory=list)


class Violation(BaseModel):
    adapted_text: str
    problem: Literal["A", "B", "C", "D", "E"]
    explanation: str
    suggested_fix: str


class ReviewResult(BaseModel):
    status: Literal["PASS", "FAIL"]
    violations: list[Violation] = Field(default_factory=list)
