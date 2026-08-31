import unittest

import fitz

from pragent.paper_processing.figures.captions import Caption
from pragent.paper_processing.figures.layout import PageLayout, detect_layout
from pragent.paper_processing.figures.matching import RegionProposal, resolve_page_assignments
from pragent.paper_processing.figures.qa_metrics import compute_crop_metrics
from pragent.paper_processing.figures.text_types import TextType, classify_page_lines
from pragent.paper_processing.figures.typography import estimate_document_typography


class DocumentLayoutEngineTests(unittest.TestCase):
    def _doc(self):
        doc = fitz.open()
        self.addCleanup(doc.close)
        return doc

    def test_typography_profile_prefers_character_weighted_body_style(self):
        doc = self._doc()
        for _ in range(2):
            page = doc.new_page(width=612, height=792)
            page.insert_text((70, 70), "A SHORT TITLE", fontsize=16, fontname="helv")
            body = (
                "This is ordinary academic body text with enough characters to dominate the document profile. "
                "The body repeats across several lines and pages for a stable estimate. "
            ) * 5
            page.insert_textbox(fitz.Rect(70, 120, 540, 500), body, fontsize=10, fontname="Times-Roman")

        profile = estimate_document_typography(doc)
        self.assertAlmostEqual(profile.body_size, 10.0, delta=0.6)
        self.assertIn("times", profile.body_font)
        self.assertGreater(profile.body_char_count, 200)
        self.assertGreater(profile.confidence, 0.5)

    def test_typed_lines_separate_caption_body_and_visual_label(self):
        doc = self._doc()
        page = doc.new_page(width=612, height=792)
        page.insert_textbox(
            fitz.Rect(70, 100, 540, 170),
            "This is a normal body sentence. It contains punctuation and follows the dominant body typography.",
            fontsize=10,
            fontname="Times-Roman",
        )
        page.draw_rect(fitz.Rect(100, 260, 500, 430), width=1)
        page.insert_text((120, 300), "Accuracy", fontsize=9, fontname="Times-Roman")
        page.insert_textbox(
            fitz.Rect(100, 450, 500, 485),
            "Figure 1: Accuracy across benchmark tasks.",
            fontsize=9,
            fontname="Times-Roman",
        )
        profile = estimate_document_typography(doc)
        cap = Caption(
            kind="figure",
            number=1,
            label="Figure 1",
            text="Figure 1: Accuracy across benchmark tasks.",
            bbox=fitz.Rect(100, 450, 500, 485),
            page_num=0,
        )

        lines = classify_page_lines(page, profile, [cap], page_num=0)
        kinds = {line.text: line.text_type for line in lines}
        self.assertEqual(kinds["Figure 1: Accuracy across benchmark tasks."], TextType.CAPTION)
        self.assertEqual(kinds["Accuracy"], TextType.FIGURE_TEXT)
        body_kind = next(line.text_type for line in lines if line.text.startswith("This is a normal body sentence"))
        self.assertEqual(body_kind, TextType.BODY)

    def test_layout_can_use_typed_body_lines_instead_of_full_width_title(self):
        doc = self._doc()
        page = doc.new_page(width=612, height=792)
        page.insert_textbox(fitz.Rect(70, 45, 540, 85), "A VERY WIDE PAPER TITLE", fontsize=15)
        for y in range(130, 300, 24):
            page.insert_textbox(fitz.Rect(70, y, 280, y + 20), "Left column body sentence with punctuation.", fontsize=10)
            page.insert_textbox(fitz.Rect(330, y, 540, y + 20), "Right column body sentence with punctuation.", fontsize=10)
        profile = estimate_document_typography(doc)
        typed = classify_page_lines(page, profile, page_num=0)
        layout = detect_layout(page, profile, typed)
        self.assertEqual(layout.kind, "dual")
        self.assertIsNotNone(layout.column_boundary)

    def test_typed_layout_does_not_downgrade_legacy_dual_page(self):
        doc = self._doc()
        page = doc.new_page(width=612, height=792)
        for y in range(120, 310, 24):
            page.insert_textbox(fitz.Rect(70, y, 285, y + 20), "Left body sentence with punctuation.", fontsize=10)
            page.insert_textbox(fitz.Rect(350, y, 540, y + 20), "Right body sentence with punctuation.", fontsize=10)
        profile = estimate_document_typography(doc)
        typed = classify_page_lines(page, profile, page_num=0)
        # Simulate a conservative classifier that only retained the left-side
        # body evidence. The legacy geometry is still clearly dual-column.
        typed_left_only = [line for line in typed if line.bbox.x1 < 305]
        self.assertEqual(detect_layout(page).kind, "dual")
        self.assertEqual(detect_layout(page, profile, typed_left_only).kind, "dual")

    def test_hungarian_matching_keeps_dense_page_regions_one_to_one(self):
        cap1 = Caption("figure", 29, "Figure 29", "Figure 29: left", fitz.Rect(60, 280, 280, 310), 0)
        cap2 = Caption("figure", 30, "Figure 30", "Figure 30: right", fitz.Rect(330, 280, 560, 310), 0)
        left_region = RegionProposal(cap1, fitz.Rect(60, 80, 285, 265), 0.8)
        right_region = RegionProposal(cap2, fitz.Rect(325, 80, 560, 265), 0.8)
        layout = PageLayout(
            kind="dual",
            page_width=612,
            page_height=792,
            column_boundary=305,
            text_left=60,
            text_right=560,
            left_col_left=60,
            left_col_right=285,
            right_col_left=325,
            right_col_right=560,
        )
        result = resolve_page_assignments([cap1, cap2], [right_region, left_region], layout)
        self.assertEqual(result[("figure", 29, 0)].bbox, left_region.bbox)
        self.assertEqual(result[("figure", 30, 0)].bbox, right_region.bbox)
        self.assertLess(result[("figure", 29, 0)].bbox.x1, 305)
        self.assertGreater(result[("figure", 30, 0)].bbox.x0, 305)

    def test_crop_metrics_expose_body_contamination_features(self):
        doc = self._doc()
        page = doc.new_page(width=612, height=792)
        page.insert_textbox(
            fitz.Rect(70, 100, 540, 210),
            (
                "This is body prose that should be measurable inside a bad crop. "
                "It continues across several lines with normal sentence punctuation. "
            ) * 3,
            fontsize=10,
            fontname="Times-Roman",
        )
        profile = estimate_document_typography(doc)
        typed = classify_page_lines(page, profile, page_num=0)
        bbox = fitz.Rect(60, 90, 550, 220)
        metrics = compute_crop_metrics(page, bbox, typed)
        self.assertGreater(metrics.body_char_ratio, 0.5)
        self.assertGreater(metrics.body_line_count, 0)
        self.assertGreater(metrics.max_consec_body_lines, 0)
        self.assertGreater(metrics.area_ratio, 0)

    def test_cross_column_caption_does_not_create_false_column_mismatch(self):
        doc = self._doc()
        page = doc.new_page(width=612, height=792)
        cap = Caption(
            "figure", 9, "Figure 9", "Figure 9: text card.",
            fitz.Rect(70, 450, 540, 480), 0,
        )
        metrics = compute_crop_metrics(
            page,
            fitz.Rect(70, 220, 285, 430),
            [],
            caption=cap,
            column_boundary=305,
        )
        self.assertEqual(metrics.column_consistency, 1.0)


if __name__ == "__main__":
    unittest.main()
