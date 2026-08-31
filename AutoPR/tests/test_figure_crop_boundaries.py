import unittest

import fitz
from PIL import Image

from pragent.paper_processing.figures.captions import (
    Caption,
    _caption_text_and_bbox,
    find_captions,
)
from pragent.paper_processing.figures.layout import PageLayout, detect_layout
from pragent.paper_processing.figures.locate import (
    locate_figure_content,
    locate_table_content,
)
from pragent.paper_processing.figures.quality import (
    check_body_text_contamination,
    run_quality_checks,
)
from pragent.paper_processing.figures.typography import TypographyProfile


class FigureCropBoundaryTests(unittest.TestCase):
    def _page(self):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        self.addCleanup(doc.close)
        return doc, page

    def test_full_width_heading_does_not_hide_two_column_layout(self):
        _, page = self._page()
        page.insert_textbox(fitz.Rect(80, 45, 532, 80), "A FULL WIDTH PAPER TITLE", fontsize=14)
        left = "Left column body text repeated for layout detection. " * 7
        right = "Right column body text repeated for layout detection. " * 7
        page.insert_textbox(fitz.Rect(70, 120, 285, 430), left, fontsize=9)
        page.insert_textbox(fitz.Rect(325, 120, 540, 430), right, fontsize=9)

        layout = detect_layout(page)
        self.assertEqual(layout.kind, "dual")
        self.assertIsNotNone(layout.column_boundary)
        self.assertGreater(layout.column_boundary, 285)
        self.assertLess(layout.column_boundary, 325)

    def test_body_reference_is_not_mistaken_for_a_caption(self):
        doc, page = self._page()
        page.insert_textbox(
            fitz.Rect(70, 100, 540, 150),
            "Figure 11 shows that the model improves after training and this sentence is body prose.",
            fontsize=10,
        )
        page.insert_textbox(
            fitz.Rect(70, 400, 540, 450),
            "Figure 11: Robustness results across model sizes.",
            fontsize=9,
        )

        captions = [c for c in find_captions(doc) if c.kind == "figure" and c.number == 11]
        self.assertEqual(len(captions), 1)
        self.assertGreater(captions[0].bbox.y0, 350)

    def test_caption_can_be_found_inside_a_larger_text_block(self):
        doc, page = self._page()
        page.insert_textbox(
            fitz.Rect(330, 250, 540, 430),
            "metric A   metric B\n81.9       95.1\n75.1       94.1\nTable 13: Fairness evaluation by demographic group.\ncontinued caption text.",
            fontsize=9,
        )

        captions = [c for c in find_captions(doc) if c.kind == "table" and c.number == 13]
        self.assertEqual(len(captions), 1)
        self.assertIn("continued caption text", captions[0].text)
        self.assertGreater(captions[0].bbox.y0, 250)

    def test_short_punctuated_table_reference_is_not_a_caption(self):
        doc, page = self._page()
        page.insert_textbox(
            fitz.Rect(70, 100, 540, 160),
            "Some examples of these prompts can be seen in\nTable 2.",
            fontsize=10,
        )
        self.assertEqual(
            [c for c in find_captions(doc) if c.kind == "table" and c.number == 2],
            [],
        )

    def test_label_only_colon_can_start_multiline_caption(self):
        doc, page = self._page()
        page.insert_textbox(
            fitz.Rect(90, 300, 520, 360),
            "Figure 24:\nOff-distribution samples from the model after safety training.",
            fontsize=10,
        )
        captions = [c for c in find_captions(doc) if c.kind == "figure" and c.number == 24]
        self.assertEqual(len(captions), 1)
        self.assertIn("Off-distribution samples", captions[0].text)

    def test_figure_prefers_near_visual_cluster_over_remote_page_art(self):
        _, page = self._page()
        page.draw_rect(fitz.Rect(100, 80, 500, 140), width=1)
        page.draw_rect(fitz.Rect(120, 300, 490, 450), width=1)
        page.draw_rect(fitz.Rect(150, 330, 250, 400), width=1)
        cap = Caption(
            kind="figure", number=1, label="Figure 1",
            text="Figure 1: nearby diagram", bbox=fitz.Rect(100, 480, 500, 510), page_num=0,
        )
        layout = detect_layout(page)
        bbox, confidence = locate_figure_content(page, cap, layout, [cap])

        self.assertIsNotNone(bbox)
        self.assertGreater(bbox.y0, 250)
        self.assertLess(bbox.y1, cap.bbox.y0)
        self.assertGreaterEqual(confidence, 0.8)

    def test_table_uses_nearest_rule_cluster_not_all_rules_above_caption(self):
        _, page = self._page()
        # Unrelated earlier figure rules.
        page.draw_line((110, 120), (500, 120), width=1)
        page.draw_line((110, 210), (500, 210), width=1)
        figure_cap = Caption(
            kind="figure", number=9, label="Figure 9",
            text="Figure 9: unrelated", bbox=fitz.Rect(110, 230, 500, 255), page_num=0,
        )
        # Actual table immediately before its caption.
        for y in (400, 430, 465, 510):
            page.draw_line((110, y), (500, y), width=1)
        page.insert_textbox(fitz.Rect(120, 405, 490, 505), "A B C\n1 2 3\n4 5 6\n7 8 9", fontsize=9)
        table_cap = Caption(
            kind="table", number=1, label="Table 1",
            text="Table 1: benchmark results", bbox=fitz.Rect(110, 525, 500, 550), page_num=0,
        )
        layout = detect_layout(page)
        bbox, confidence = locate_table_content(page, table_cap, layout, [figure_cap, table_cap])

        self.assertIsNotNone(bbox)
        self.assertGreater(bbox.y0, 380)
        self.assertGreater(bbox.y1, 500)
        self.assertLess(bbox.y1, table_cap.bbox.y0)
        self.assertGreaterEqual(confidence, 0.8)

    def test_borderless_table_uses_nearest_tabular_text_block(self):
        _, page = self._page()
        page.insert_textbox(
            fitz.Rect(110, 180, 540, 300),
            "CWE-20    Improper Input Validation\n"
            "CWE-22    Path Traversal\n"
            "CWE-78    OS Command Injection\n"
            "CWE-79    Cross-site Scripting\n"
            "CWE-89    SQL Injection\n"
            "CWE-502   Deserialization of Untrusted Data\n"
            "CWE-732   Incorrect Permission Assignment\n"
            "CWE-798   Hard-coded Credentials",
            fontsize=9,
        )
        cap = Caption(
            kind="table", number=3, label="Table 3",
            text="Table 3: Common weakness enumerations.",
            bbox=fitz.Rect(110, 315, 520, 340), page_num=0,
        )
        bbox, confidence = locate_table_content(page, cap, detect_layout(page), [cap])
        self.assertIsNotNone(bbox)
        self.assertGreater(bbox.y0, 160)
        self.assertLess(bbox.y1, cap.bbox.y0)
        self.assertGreaterEqual(confidence, 0.8)

    def test_tall_text_table_can_pair_far_top_and_bottom_rules(self):
        _, page = self._page()
        page.draw_line((110, 100), (500, 100), width=1)
        page.draw_line((110, 115), (500, 115), width=1)
        page.insert_textbox(
            fitz.Rect(120, 125, 490, 490),
            ("Human: prompt text\nAssistant: long response text\n" * 10),
            fontsize=8,
        )
        page.draw_line((110, 510), (500, 510), width=1)
        cap = Caption(
            kind="table", number=4, label="Table 4",
            text="Table 4: Example prompt.", bbox=fitz.Rect(140, 525, 470, 550), page_num=0,
        )
        bbox, confidence = locate_table_content(page, cap, detect_layout(page), [cap])
        self.assertIsNotNone(bbox)
        self.assertLess(bbox.y0, 120)
        self.assertGreater(bbox.y1, 500)
        self.assertGreaterEqual(confidence, 0.9)

    def test_adjacent_tables_are_separated_by_the_second_caption(self):
        _, page = self._page()
        table7_cap = Caption(
            kind="table", number=7, label="Table 7",
            text="Table 7: First experiment results.",
            bbox=fitz.Rect(108, 80, 504, 145), page_num=0,
        )
        table8_cap = Caption(
            kind="table", number=8, label="Table 8",
            text="Table 8: Second experiment results.",
            bbox=fitz.Rect(108, 310, 504, 330), page_num=0,
        )
        for y in (159, 175, 254, 264, 279, 289):
            page.draw_line((108, y), (504, y), width=1)
        for y in (330, 339, 366, 375):
            page.draw_line((108, y), (504, y), width=1)

        layout = detect_layout(page)
        captions = [table7_cap, table8_cap]
        bbox7, conf7 = locate_table_content(page, table7_cap, layout, captions)
        bbox8, conf8 = locate_table_content(page, table8_cap, layout, captions)

        self.assertIsNotNone(bbox7)
        self.assertIsNotNone(bbox8)
        self.assertLess(bbox7.y1, table8_cap.bbox.y0)
        self.assertGreater(bbox8.y0, table8_cap.bbox.y1 - 2)
        self.assertLess(bbox7.y1, bbox8.y0)
        self.assertGreaterEqual(conf7, 0.9)
        self.assertGreaterEqual(conf8, 0.9)

    def test_ruled_header_does_not_collapse_unruled_table_rows(self):
        _, page = self._page()
        cap = Caption(
            kind="table", number=14, label="Table 14",
            text="Table 14: Interactive benchmark results.",
            bbox=fitz.Rect(70, 148, 540, 180), page_num=0,
        )
        page.insert_text(
            (150, 82),
            "Method        input type        AUC        score",
            fontsize=8,
        )
        page.draw_line((150, 87), (462, 87), width=1)
        page.insert_text(
            (150, 98),
            "MiVOS        scribbles        0.87        0.88",
            fontsize=8,
        )
        page.draw_line((150, 103), (462, 103), width=1)
        page.insert_text(
            (150, 113),
            "MiVOS   clicks   0.75",
            fontsize=8,
        )
        page.insert_text(
            (150, 124),
            "CiVOS   clicks   0.83",
            fontsize=8,
        )
        page.insert_text(
            (150, 135),
            "SAM 2   clicks   0.90",
            fontsize=8,
        )

        layout = PageLayout(
            kind="single", page_width=612, page_height=792,
            text_left=70, text_right=540,
        )
        bbox, confidence = locate_table_content(page, cap, layout, [cap])
        self.assertIsNotNone(bbox)
        self.assertLess(bbox.y0, 80)
        self.assertGreater(bbox.y1, 130)
        self.assertLess(bbox.y1, cap.bbox.y0)
        self.assertGreaterEqual(confidence, 0.9)

    def test_body_text_contamination_is_detected_and_forces_review(self):
        _, page = self._page()
        prose = (
            "This is ordinary academic body prose that should never be swallowed by a figure crop. "
            "It continues for several sentences so the PDF text block clearly resembles a paragraph. "
        ) * 3
        page.insert_textbox(fitz.Rect(70, 100, 290, 300), prose, fontsize=9)
        page.draw_rect(fitz.Rect(330, 120, 520, 300), width=1)
        bad_bbox = fitz.Rect(60, 90, 530, 310)
        contaminated, chars = check_body_text_contamination(page, bad_bbox)
        self.assertTrue(contaminated)
        self.assertGreater(chars, 100)

        qr = run_quality_checks(
            Image.new("RGB", (800, 400), "white"), bad_bbox, page.mediabox, 0.9,
            page=page,
        )
        self.assertTrue(qr.has_body_text_contamination)
        self.assertTrue(qr.needs_review)
        self.assertTrue(any(x.startswith("body_text_contamination_") for x in qr.issues))


    def test_table_body_prose_with_normal_line_length_forces_review(self):
        _, page = self._page()
        prose = (
            "This is ordinary academic body prose with normal two-column line lengths. "
            "It contains complete sentences and should be rejected when a table crop swallows it. "
        ) * 4
        page.insert_textbox(fitz.Rect(70, 100, 350, 260), prose, fontsize=9)
        cap = Caption(
            kind="table", number=20, label="Table 20",
            text="Table 20: results", bbox=fitz.Rect(70, 300, 350, 325), page_num=0,
        )
        bad_bbox = fitz.Rect(65, 95, 355, 270)
        contaminated, chars = check_body_text_contamination(page, bad_bbox, cap)
        self.assertTrue(contaminated)
        self.assertGreater(chars, 110)

        qr = run_quality_checks(
            Image.new("RGB", (600, 320), "gray"), bad_bbox, page.mediabox, 0.9,
            page=page, caption=cap,
        )
        self.assertTrue(qr.has_body_text_contamination)
        self.assertTrue(qr.needs_review)

    def test_near_full_page_table_is_always_abnormal_size(self):
        _, page = self._page()
        cap = Caption(
            kind="table", number=21, label="Table 21",
            text="Table 21: bad near-page crop", bbox=fitz.Rect(80, 700, 530, 725), page_num=0,
        )
        qr = run_quality_checks(
            Image.new("RGB", (1600, 2100), "gray"),
            fitz.Rect(20, 20, 590, 770), page.mediabox, 0.9,
            page_width_px=1700, page_height_px=2200, caption=cap,
        )
        self.assertTrue(qr.is_abnormal_size)
        self.assertTrue(qr.needs_review)
        self.assertIn("abnormal_size", qr.issues)

    def test_caption_continuation_stops_when_body_typography_resumes(self):
        def line(text, y0, y1, size, font="Times-Roman"):
            return {
                "bbox": (70, y0, 520, y1),
                "spans": [{"text": text, "size": size, "font": font, "flags": 0}],
            }

        lines = [
            line("Figure 5: A complete caption sentence.", 100, 110, 8),
            line("This is ordinary body prose that starts immediately after the caption.", 111, 123, 10),
            line("The paragraph continues and must not enlarge the caption bounding box.", 124, 136, 10),
        ]
        profile = TypographyProfile(
            body_font="times", body_size=10.0, body_line_gap=2.0, body_line_height=12.0,
            caption_size=8.0, body_char_count=1000, confidence=0.9,
        )
        text, bbox = _caption_text_and_bbox(lines, 0, profile)
        self.assertEqual(text, "Figure 5: A complete caption sentence.")
        self.assertLessEqual(bbox.y1, 110)

    def test_compact_wide_table_is_not_abnormal_size(self):
        _, page = self._page()
        cap = Caption(
            kind="table", number=6, label="Table 6",
            text="Table 6: compact confusion matrix", bbox=fitz.Rect(80, 300, 530, 330), page_num=0,
        )
        qr = run_quality_checks(
            Image.new("RGB", (820, 80), "white"),
            fitz.Rect(80, 220, 530, 290), page.mediabox, 0.9,
            page=page, caption=cap,
        )
        self.assertFalse(qr.is_abnormal_size)
        self.assertNotIn("abnormal_size", qr.issues)


if __name__ == "__main__":
    unittest.main()
