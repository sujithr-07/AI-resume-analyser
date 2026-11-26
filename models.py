"""
Pydantic models for resume extraction (Task: Validation and Retry).

Replaces the jsonschema check from Task 2 with typed, constrained models:
  - years_of_experience must be between 0 and 50 (null allowed)
  - skills must be a non-empty list of non-blank strings
  - unknown keys are forbidden -> they become validation errors -> retry
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EducationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree: str | None = None
    institution: str | None = None
    year: str | None = None

    @field_validator("degree", "institution", "year", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        """Treat "" / "   " as null instead of failing."""
        if isinstance(v, str) and not v.strip():
            return None
        return v


class ResumeData(BaseModel):
    model_config = ConfigDict(extra="forbid")   # unexpected keys -> ValidationError -> retry

    candidate_name: str | None = None
    skills: list[str] = Field(min_length=1)                       # constraint: not empty
    years_of_experience: float | None = Field(default=None, ge=0, le=50)  # 0..50, null ok
    education: list[EducationItem] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    @field_validator("candidate_name", mode="before")
    @classmethod
    def _blank_name_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("skills", "strengths", "gaps", mode="before")
    @classmethod
    def _strip_items(cls, v):
        """Strip whitespace and drop blank items before constraints are checked."""
        if isinstance(v, list):
            return [s.strip() for s in v if isinstance(s, str) and s.strip()]
        return v