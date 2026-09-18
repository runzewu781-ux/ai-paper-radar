import json
import unittest
from unittest.mock import AsyncMock, patch

from pragent.paper_processing.research_brief.models import (
    BoundingBox,
    DocumentMetadata,
    EvidenceItem,
    EvidenceLocation,
    ResearchBrief,
    SectionEvidence,
    VisualEvidence,
)
from pragent.paper_processing.research_brief.semantic import (
    MetricDraft,
    SemanticBriefDraft,
    SemanticClaimDraft,
    build_semantic_candidate_packet,
    extract_semantic_brief,
    merge_semantic_draft,
    validate_semantic_draft,
)


class ResearchBriefSemanticTests(unittest.IsolatedAsyncioTestCase):
    def _location(self, page: int, top: float) -> EvidenceLocation:
        return EvidenceLocation(
            page_index=page,
            bbox=BoundingBox(left=50, top=top, right=550, bottom=top + 20),
            page_width=612,
            page_height=792,
            block_index=0,
        )

    def _item(self, item_id: str, text: str, source_type: str, section_id, page: int, top: float):
        return EvidenceItem(
            id=item_id,
            source_type=source_type,
            text=text,
            text_hash="a" * 64,
            section_id=section_id,
            location=self._location(page, top),
        )

    def _brief(self) -> ResearchBrief:
        title = self._item(
            "text:p0000:b0000",
            "Evidence Paper",
            "title",
            None,
            0,
            50,
        )
        intro_h = self._item(
            "text:p0000:b0001",
            "1. Introduction",
            "section_heading",
            "section:001",
            0,
            100,
        )
        result = self._item(
            "text:p0000:b0002",
            "On DemoSet, Method A improves accuracy by +10% over Baseline B.",
            "paragraph",
            "section:001",
            0,
            130,
        )
        visual_noise = self._item(
            "text:p0000:b0003",
            "0 20 40 60 80 100",
            "visual_text",
            "section:001",
            0,
            300,
        )
        refs_h = self._item(
            "text:p0001:b0000",
            "References",
            "section_heading",
            "section:002",
            1,
            100,
        )
        ref = self._item(
            "text:p0001:b0001",
            "Smith et al. 2025. A referenced paper reports 99% accuracy.",
            "paragraph",
            "section:002",
            1,
            130,
        )
        return ResearchBrief(
            document=DocumentMetadata(
                source_pdf="paper.pdf",
                pdf_sha256="b" * 64,
                page_count=2,
                title="Evidence Paper",
            ),
            evidence=[title, intro_h, result, visual_noise, refs_h, ref],
            sections=[
                SectionEvidence(
                    id="section:001",
                    heading="1. Introduction",
                    normalized_heading="introduction",
                    heading_evidence_id=intro_h.id,
                    evidence_ids=[intro_h.id, result.id, visual_noise.id],
                ),
                SectionEvidence(
                    id="section:002",
                    heading="References",
                    normalized_heading="references",
                    heading_evidence_id=refs_h.id,
                    evidence_ids=[refs_h.id, ref.id],
                ),
            ],
            figures=[
                VisualEvidence(
                    id="visual:figure:1:p0000",
                    kind="figure",
                    number=1,
                    page_index=0,
                    page_width=612,
                    page_height=792,
                    caption="Figure 1: Method A improves accuracy by +10% on DemoSet.",
                    bbox=BoundingBox(left=100, top=260, right=500, bottom=400),
                    confidence=0.9,
                )
            ],
        )

    def _valid_draft(self) -> SemanticBriefDraft:
        return SemanticBriefDraft(
            main_results=[
                SemanticClaimDraft(
                    statement="On DemoSet, Method A improves accuracy by +10% over Baseline B.",
                    evidence_ids=["text:p0000:b0002"],
                    qualifiers=[],
                    confidence=0.95,
                )
            ],
            key_metrics=[
                MetricDraft(
                    metric="accuracy improvement",
                    value_exact="+10%",
                    dataset="DemoSet",
                    method="Method A",
                    baseline="Baseline B",
                    comparison="improves over",
                    evidence_ids=["text:p0000:b0002"],
                )
            ],
        )

    def test_candidate_packet_excludes_references_and_visual_text(self):
        packet = build_semantic_candidate_packet(self._brief())
        self.assertIn("text:p0000:b0002", packet.allowed_ids)
        self.assertIn("visual:figure:1:p0000", packet.allowed_ids)
        self.assertIn("E0003", packet.allowed_aliases)
        self.assertNotIn("text:p0000:b0002", packet.text)
        self.assertNotIn("text:p0000:b0003", packet.allowed_ids)
        self.assertNotIn("text:p0001:b0001", packet.allowed_ids)
        self.assertNotIn("99% accuracy", packet.text)
        self.assertNotIn("0 20 40 60 80 100", packet.text)

    def test_unknown_evidence_id_is_rejected(self):
        packet = build_semantic_candidate_packet(self._brief())
        draft = SemanticBriefDraft(
            main_results=[
                SemanticClaimDraft(
                    statement="Method A improves accuracy.",
                    evidence_ids=["text:missing"],
                )
            ]
        )
        with self.assertRaisesRegex(ValueError, "unavailable evidence IDs"):
            validate_semantic_draft(draft, packet)

    def test_invented_metric_value_is_rejected(self):
        packet = build_semantic_candidate_packet(self._brief())
        draft = SemanticBriefDraft(
            key_metrics=[
                MetricDraft(
                    metric="accuracy improvement",
                    value_exact="+25%",
                    evidence_ids=["text:p0000:b0002"],
                )
            ]
        )
        with self.assertRaisesRegex(ValueError, "value_exact"):
            validate_semantic_draft(draft, packet)

    def test_numeric_claim_must_be_grounded_in_its_cited_evidence(self):
        packet = build_semantic_candidate_packet(self._brief())
        draft = SemanticBriefDraft(
            main_results=[
                SemanticClaimDraft(
                    statement="Method A improves accuracy by +25%.",
                    evidence_ids=["text:p0000:b0002"],
                )
            ]
        )
        with self.assertRaisesRegex(ValueError, "numeric token"):
            validate_semantic_draft(draft, packet)

    def test_evaluated_model_weakness_cannot_be_mislabeled_as_paper_limitation(self):
        packet = build_semantic_candidate_packet(self._brief())
        draft = SemanticBriefDraft(
            limitations=[
                SemanticClaimDraft(
                    statement="Baseline B has weak accuracy.",
                    evidence_ids=["text:p0000:b0002"],
                )
            ]
        )
        with self.assertRaisesRegex(ValueError, "explicit limitation"):
            validate_semantic_draft(draft, packet)

    def test_merge_assigns_stable_ids_and_semantic_provenance(self):
        brief = self._brief()
        packet = build_semantic_candidate_packet(brief)
        merged = merge_semantic_draft(brief, self._valid_draft(), packet, "gemini-3-flash")
        self.assertEqual(merged.main_results[0].id, "claim:main_results:001")
        self.assertEqual(merged.key_metrics[0].id, "metric:001")
        self.assertEqual(merged.key_metrics[0].value_exact, "+10%")
        self.assertEqual(merged.semantic_extraction.model, "gemini-3-flash")
        self.assertEqual(merged.semantic_extraction.validation, "passed")

    async def test_async_extractor_accepts_only_validated_json(self):
        brief = self._brief()
        packet = build_semantic_candidate_packet(brief)
        alias = next(
            key for key, value in packet.alias_to_id.items() if value == "text:p0000:b0002"
        )
        draft = self._valid_draft().model_dump(exclude_none=True)
        draft["main_results"][0]["evidence_ids"] = [alias]
        draft["key_metrics"][0]["evidence_ids"] = [alias]
        with patch(
            "pragent.paper_processing.research_brief.semantic.call_text_llm_api",
            new=AsyncMock(return_value=json.dumps(draft)),
        ) as mocked:
            merged, raw = await extract_semantic_brief(
                brief,
                client=object(),
                model="gemini-3-flash",
                retry_invalid_once=False,
            )
        self.assertEqual(mocked.await_count, 1)
        self.assertEqual(merged.key_metrics[0].value_exact, "+10%")
        self.assertIn("main_results", raw)


if __name__ == "__main__":
    unittest.main()
