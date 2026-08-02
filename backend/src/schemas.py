"""Typed Pydantic models for the Requirements Intelligence Agent API.

These models define the canonical (target) response contract for the analysis
report, validate the payload structure, and enforce ISO 26262 ASIL
normalization on ``suggested_asil`` values.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .db import AnalysisStatus
from .utils.normalization import normalize_asil, ASIL_VALUES


# ─── REQUEST / LIGHTWEIGHT RESPONSE MODELS ───────────────────────────────────
class AnalyzeRequest(BaseModel):
    document: str = Field(..., min_length=1, description="Raw requirements document content")
    document_name: str = Field(default="Untitled Requirements Document", min_length=1)


class AnalyzeResponse(BaseModel):
    analysis_id: int
    status: AnalysisStatus


class StatusResponse(BaseModel):
    analysis_id: int
    status: AnalysisStatus
    error_message: str | None = None


class AnalysisSummaryResponse(BaseModel):
    id: int
    document_name: str
    status: AnalysisStatus
    created_at: Any


# ─── ANALYSIS PAYLOAD MODELS (TARGET SCHEMA) ─────────────────────────────────
class MetaOutput(BaseModel):
    agent_version: str = "1.0.0"
    model: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    human_review_required: bool = True


class DocumentOutput(BaseModel):
    id: int = 0
    name: str = ""
    version: str = "1.0.0"
    classification: str = "Internal"


class SummaryOutput(BaseModel):
    total_requirements: int = 0
    safety_relevant_count: int = 0
    inconsistencies_count: int = 0
    gaps_count: int = 0
    domain_breakdown: Dict[str, int] = Field(default_factory=dict)


class SafetyAssessment(BaseModel):
    exposure: str = "E0"
    severity: str = "S0"
    controllability: str = "C0"
    suggested_asil: str = "QM"
    rationale: str = "Not assessed"

    @field_validator("suggested_asil", mode="before")
    @classmethod
    def _normalize_asil(cls, value: Any) -> str:
        return normalize_asil(value)


class RetrievedRequirement(BaseModel):
    """A knowledge-base requirement most similar to a safety requirement."""

    req_id: str = ""
    req_text: str = ""
    domain: str = "UNKNOWN"
    asil: str = "QM"
    reasoning: Optional[str] = None
    score: Optional[float] = None

    @field_validator("asil", mode="before")
    @classmethod
    def _normalize_asil(cls, value: Any) -> str:
        return normalize_asil(value)


class RequirementSafety(BaseModel):
    is_relevant: bool = False
    reason: Optional[str] = None
    assessment: Optional[SafetyAssessment] = None
    # Top-N most similar knowledge-base requirements with metadata (ASIL etc).
    retrieved_requirements: List[RetrievedRequirement] = Field(default_factory=list)


class RequirementOutput(BaseModel):
    id: str = ""
    text: str = ""
    domain: str = "SYSTEM"
    safety: RequirementSafety = Field(default_factory=RequirementSafety)


class InconsistencyOutput(BaseModel):
    id: str = ""
    type: str = "conflict"
    severity: str = "MEDIUM"
    description: str = ""
    affected_ids: List[str] = Field(default_factory=list)
    suggested_action: str = ""


class GapOutput(BaseModel):
    id: str = ""
    type: str = "missing_traceability"
    priority: str = "MEDIUM"
    affected_id: str = ""
    description: str = ""
    suggested_action: str = ""


class FindingsOutput(BaseModel):
    inconsistencies: List[InconsistencyOutput] = Field(default_factory=list)
    gaps: List[GapOutput] = Field(default_factory=list)


class AnalysisPayloadResponse(BaseModel):
    """Canonical payload returned by GET /analyses/{analysis_id}."""

    model_config = ConfigDict(extra="allow")

    id: int
    status: AnalysisStatus
    error_message: Optional[str] = None
    meta: MetaOutput = Field(default_factory=MetaOutput)
    document: DocumentOutput = Field(default_factory=DocumentOutput)
    summary: SummaryOutput = Field(default_factory=SummaryOutput)
    requirements: List[RequirementOutput] = Field(default_factory=list)
    findings: FindingsOutput = Field(default_factory=FindingsOutput)
    # Optional debug trace; only populated when include_trace=True
    node_trace: Optional[Dict[str, Any]] = None

