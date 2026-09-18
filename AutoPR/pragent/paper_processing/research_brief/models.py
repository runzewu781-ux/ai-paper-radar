from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BriefModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BoundingBox(BriefModel):
    left: float
    top: float
    right: float
    bottom: float
    origin: Literal["top-left"] = "top-left"


class EvidenceLocation(BriefModel):
    """Pointer back to an exact region of the source PDF."""

    page_index: int = Field(ge=0, description="Zero-based PDF page index")
    bbox: BoundingBox
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    block_index: Optional[int] = Field(default=None, ge=0)


class EvidenceItem(BriefModel):
    id: str = Field(min_length=1)
    source_type: Literal[
        "title",
        "section_heading",
        "figure_caption",
        "table_caption",
        "visual_text",
        "paragraph",
        "list",
        "formula",
        "other_text",
    ]
    text: str = Field(min_length=1)
    text_hash: str = Field(min_length=12)
    section_id: Optional[str] = None
    location: EvidenceLocation


class SectionEvidence(BriefModel):
    id: str = Field(min_length=1)
    heading: str = Field(min_length=1)
    normalized_heading: str = Field(min_length=1)
    heading_evidence_id: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class VisualEvidence(BriefModel):
    id: str = Field(min_length=1)
    kind: Literal["figure", "table"]
    number: int = Field(ge=0)
    page_index: int = Field(ge=0)
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    caption: str
    bbox: BoundingBox
    file: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    needs_review: bool = False
    issues: list[str] = Field(default_factory=list)


class ClaimEvidence(BriefModel):
    """Semantic statement that is invalid unless it cites source evidence."""

    id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    qualifiers: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class MetricResult(BriefModel):
    id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    value_exact: str = Field(min_length=1)
    unit: Optional[str] = None
    dataset: Optional[str] = None
    method: Optional[str] = None
    baseline: Optional[str] = None
    comparison: Optional[str] = None
    evidence_ids: list[str] = Field(min_length=1)


class DocumentMetadata(BriefModel):
    source_pdf: str
    pdf_sha256: str = Field(min_length=64, max_length=64)
    page_count: int = Field(ge=1)
    title: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[int] = None
    parser: str = "pymupdf-native"
    coordinate_origin: Literal["top-left"] = "top-left"


class SemanticExtractionMetadata(BriefModel):
    model: str = Field(min_length=1)
    candidate_evidence_count: int = Field(ge=0)
    candidate_visual_count: int = Field(ge=0)
    candidate_ids_sha256: str = Field(min_length=64, max_length=64)
    validation: Literal["passed"] = "passed"


class ResearchBrief(BriefModel):
    schema_version: str = "0.1.0"
    document: DocumentMetadata
    evidence: list[EvidenceItem] = Field(default_factory=list)
    sections: list[SectionEvidence] = Field(default_factory=list)
    figures: list[VisualEvidence] = Field(default_factory=list)
    tables: list[VisualEvidence] = Field(default_factory=list)

    problem: list[ClaimEvidence] = Field(default_factory=list)
    motivation: list[ClaimEvidence] = Field(default_factory=list)
    method: list[ClaimEvidence] = Field(default_factory=list)
    architecture: list[ClaimEvidence] = Field(default_factory=list)
    datasets: list[ClaimEvidence] = Field(default_factory=list)
    baselines: list[ClaimEvidence] = Field(default_factory=list)
    main_results: list[ClaimEvidence] = Field(default_factory=list)
    ablations: list[ClaimEvidence] = Field(default_factory=list)
    limitations: list[ClaimEvidence] = Field(default_factory=list)
    key_metrics: list[MetricResult] = Field(default_factory=list)
    semantic_extraction: Optional[SemanticExtractionMetadata] = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_provenance_links(self) -> "ResearchBrief":
        evidence_ids = {item.id for item in self.evidence}
        visual_ids = {item.id for item in self.figures + self.tables}
        available = evidence_ids | visual_ids

        duplicates = len(available) != len(self.evidence) + len(self.figures) + len(self.tables)
        if duplicates:
            raise ValueError("evidence and visual IDs must be globally unique")

        for section in self.sections:
            if section.heading_evidence_id not in evidence_ids:
                raise ValueError(
                    f"section {section.id} references unknown heading evidence "
                    f"{section.heading_evidence_id}"
                )
            missing = set(section.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(f"section {section.id} references unknown evidence IDs: {sorted(missing)}")

        claim_groups = (
            self.problem,
            self.motivation,
            self.method,
            self.architecture,
            self.datasets,
            self.baselines,
            self.main_results,
            self.ablations,
            self.limitations,
        )
        for group in claim_groups:
            for claim in group:
                missing = set(claim.evidence_ids) - available
                if missing:
                    raise ValueError(f"claim {claim.id} references unknown evidence IDs: {sorted(missing)}")

        for metric in self.key_metrics:
            missing = set(metric.evidence_ids) - available
            if missing:
                raise ValueError(f"metric {metric.id} references unknown evidence IDs: {sorted(missing)}")

        return self
