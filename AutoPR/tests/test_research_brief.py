import json
import tempfile
import unittest
from pathlib import Path

import fitz
from pydantic import ValidationError

from pragent.paper_processing.research_brief import (
    ResearchBrief,
    build_research_brief,
    write_research_brief,
)


class ResearchBriefTests(unittest.TestCase):
    def _paper(self, root: Path) -> Path:
        pdf_path = root / "paper.pdf"
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 18), "REPEATED HEADER", fontsize=7)
        page.insert_textbox(
            fitz.Rect(70, 55, 540, 105),
            "Evidence-Aware Academic Writing",
            fontsize=18,
            fontname="helv",
            align=1,
        )
        page.insert_textbox(
            fitz.Rect(70, 130, 540, 155),
            "Abstract",
            fontsize=13,
            fontname="helv",
        )
        page.insert_textbox(
            fitz.Rect(70, 160, 540, 235),
            "We study a provenance-aware pipeline. Accuracy reaches exactly 81.9% on DemoSet under the reported setting.",
            fontsize=10,
            fontname="Times-Roman",
        )
        page.insert_textbox(
            fitz.Rect(70, 260, 540, 285),
            "1 Introduction",
            fontsize=13,
            fontname="helv",
        )
        page.insert_textbox(
            fitz.Rect(70, 295, 540, 385),
            "The system keeps every factual statement tied to its source page and bounding box. This paragraph is ordinary body evidence.",
            fontsize=10,
            fontname="Times-Roman",
        )
        page.draw_rect(fitz.Rect(120, 430, 490, 550), width=1)
        page.insert_textbox(
            fitz.Rect(120, 565, 490, 590),
            "Figure 1: Provenance architecture overview.",
            fontsize=9,
            fontname="Times-Roman",
        )
        page.insert_text((280, 786), "1", fontsize=7)
        doc.save(pdf_path)
        doc.close()
        return pdf_path

    def _manifest(self, root: Path) -> Path:
        path = root / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "pdf": "paper.pdf",
                    "pages": 1,
                    "items": [
                        {
                            "file": "figures/figure_1.png",
                            "kind": "figure",
                            "number": "1",
                            "page": 0,
                            "caption": "Figure 1: Provenance architecture overview.",
                            "bbox": [120.0, 430.0, 490.0, 550.0],
                            "confidence": 0.9,
                            "needs_review": False,
                            "issues": [],
                        }
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def _paper_with_numbered_question_and_visual_label(self, root: Path) -> Path:
        pdf_path = root / "numbered-question.pdf"
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_textbox(
            fitz.Rect(70, 55, 540, 105),
            "Question Heading Paper",
            fontsize=18,
            fontname="helv",
            align=1,
        )
        page.insert_textbox(
            fitz.Rect(70, 140, 540, 165),
            "5.2. What are the limitations of the model?",
            fontsize=11,
            fontname="hebo",
        )
        page.insert_textbox(
            fitz.Rect(70, 175, 540, 230),
            "This numbered question is a real document section heading followed by ordinary body evidence.",
            fontsize=10,
            fontname="Times-Roman",
        )
        page.draw_rect(fitz.Rect(120, 300, 500, 430), width=1)
        page.insert_textbox(
            fitz.Rect(150, 330, 420, 355),
            "Model Series Version/Sizes (B)",
            fontsize=12,
            fontname="hebo",
        )
        page.insert_textbox(
            fitz.Rect(120, 450, 500, 475),
            "Table 1: Model family comparison.",
            fontsize=9,
            fontname="Times-Roman",
        )
        doc.save(pdf_path)
        doc.close()
        return pdf_path

    def _table_manifest(self, root: Path) -> Path:
        path = root / "table-manifest.json"
        path.write_text(
            json.dumps(
                {
                    "pdf": "numbered-question.pdf",
                    "pages": 1,
                    "items": [
                        {
                            "file": "tables/table_1.png",
                            "kind": "table",
                            "number": "1",
                            "page": 0,
                            "caption": "Table 1: Model family comparison.",
                            "bbox": [120.0, 300.0, 500.0, 430.0],
                            "confidence": 0.9,
                            "needs_review": False,
                            "issues": [],
                        }
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def test_text_evidence_retains_page_bbox_and_exact_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = build_research_brief(self._paper(root), self._manifest(root))

            numeric = next(item for item in brief.evidence if "81.9%" in item.text)
            self.assertEqual(numeric.location.page_index, 0)
            self.assertGreater(numeric.location.bbox.right, numeric.location.bbox.left)
            self.assertGreater(numeric.location.bbox.bottom, numeric.location.bbox.top)
            self.assertEqual(numeric.location.page_width, 612)
            self.assertEqual(numeric.location.page_height, 792)
            self.assertIn("exactly 81.9%", numeric.text)
            self.assertEqual(len(numeric.text_hash), 64)

    def test_title_sections_and_header_footer_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = build_research_brief(self._paper(root), self._manifest(root))

            self.assertEqual(brief.document.title, "Evidence-Aware Academic Writing")
            headings = [section.normalized_heading for section in brief.sections]
            self.assertIn("abstract", headings)
            self.assertIn("introduction", headings)
            all_text = "\n".join(item.text for item in brief.evidence)
            self.assertNotIn("REPEATED HEADER", all_text)
            self.assertNotIn("\n1\n", "\n" + all_text + "\n")
            for section in brief.sections:
                self.assertIn(section.heading_evidence_id, section.evidence_ids)

    def test_figure_manifest_is_linked_without_reinterpreting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = build_research_brief(self._paper(root), self._manifest(root))

            self.assertEqual(len(brief.figures), 1)
            figure = brief.figures[0]
            self.assertEqual(figure.id, "visual:figure:1:p0000")
            self.assertEqual(figure.page_index, 0)
            self.assertEqual(figure.caption, "Figure 1: Provenance architecture overview.")
            self.assertEqual(figure.file, "figures/figure_1.png")
            self.assertEqual(figure.bbox.left, 120.0)
            self.assertFalse(figure.needs_review)

    def test_semantic_claim_cannot_reference_unknown_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = build_research_brief(self._paper(root), self._manifest(root))
            payload = brief.model_dump()
            payload["main_results"] = [
                {
                    "id": "claim:result:001",
                    "statement": "Accuracy reaches 81.9%.",
                    "evidence_ids": ["missing:evidence"],
                    "qualifiers": [],
                }
            ]
            with self.assertRaises(ValidationError):
                ResearchBrief.model_validate(payload)

    def test_sidecar_json_roundtrip_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = self._paper(root)
            manifest = self._manifest(root)
            first = build_research_brief(pdf, manifest)
            second = build_research_brief(pdf, manifest)
            first_path = write_research_brief(first, root / "first.json")
            second_path = write_research_brief(second, root / "second.json")

            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
            restored = ResearchBrief.model_validate_json(first_path.read_text(encoding="utf-8"))
            self.assertEqual(restored.document.pdf_sha256, first.document.pdf_sha256)
            self.assertEqual(len(restored.evidence), len(first.evidence))

    def test_numbered_question_heading_is_kept_but_visual_label_is_not_a_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief = build_research_brief(
                self._paper_with_numbered_question_and_visual_label(root),
                self._table_manifest(root),
            )

            headings = [section.heading for section in brief.sections]
            self.assertIn("5.2. What are the limitations of the model?", headings)
            self.assertNotIn("Model Series Version/Sizes (B)", headings)
            visual_text = next(
                item for item in brief.evidence if item.text == "Model Series Version/Sizes (B)"
            )
            self.assertEqual(visual_text.source_type, "visual_text")


if __name__ == "__main__":
    unittest.main()
