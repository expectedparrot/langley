from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


Level = Literal["low", "medium", "high", "unknown"]
Rating = Literal["consistent", "inconsistent", "neutral", "not_applicable", "not_assessed"]


class Actor(BaseModel):
    type: Literal["human", "agent", "import"] = "agent"
    name: str = "unknown"


class HypothesisInput(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    provenance: str = ""
    prior_view: str | None = None


class Source(BaseModel):
    citation: str = ""
    publisher: str = ""
    observed_at: str | None = None
    accessed_at: str | None = None


class EvidenceInput(BaseModel):
    label: str = Field(min_length=1)
    details: str = ""
    kind: Literal["observation", "argument", "assumption", "absence", "context"]
    source: Source = Field(default_factory=Source)
    credibility: Level = "unknown"
    credibility_rationale: str = ""
    importance: Level = "unknown"
    importance_rationale: str = ""
    deception_risk: Level = "unknown"
    deception_rationale: str = ""
    tags: list[str] = Field(default_factory=list)
    expected_if: list[str] = Field(default_factory=list)
    observability: Level = "unknown"
    observability_rationale: str = ""
    search_performed: str = ""

    @model_validator(mode="after")
    def validate_absence(self):
        if self.kind == "absence" and (not self.expected_if or not self.observability_rationale or not self.search_performed):
            raise ValueError("absence evidence requires expected_if, observability_rationale, and search_performed")
        return self


class CellInput(BaseModel):
    hypothesis_id: str
    rating: Rating
    strength: Literal[1, 2, 3] | None = None
    rationale: str = Field(min_length=1)
    interpretation: str = ""

    @model_validator(mode="after")
    def validate_strength(self):
        if self.rating in {"consistent", "inconsistent"} and self.strength is None:
            raise ValueError("strength is required for consistent and inconsistent ratings")
        if self.rating not in {"consistent", "inconsistent"} and self.strength is not None:
            raise ValueError("strength is only valid for consistent and inconsistent ratings")
        return self


class MatrixRowInput(BaseModel):
    assessments: list[CellInput]


class ConclusionInput(BaseModel):
    summary: str = Field(min_length=1)
    confidence: Literal["low", "moderate", "high", "unknown"] = "unknown"
    hypotheses: list[dict[str, Any]]
    critical_evidence_ids: list[str] = Field(default_factory=list)
    critical_assumptions: list[str] = Field(default_factory=list)
    residual_uncertainty: str = ""


class IndicatorInput(BaseModel):
    description: str = Field(min_length=1)
    observable_in: str = Field(min_length=1)
    supports: list[str] = Field(default_factory=list)
    weakens: list[str] = Field(default_factory=list)
    threshold: str = ""
    collection_owner: str = ""
    review_by: str | None = None


class SensitivityInput(BaseModel):
    reason: str = Field(min_length=1)
    changes: list[dict[str, Any]]
    result: dict[str, Any] = Field(default_factory=dict)
