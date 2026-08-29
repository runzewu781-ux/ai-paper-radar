import tempfile
import unittest
from pathlib import Path

from pragent.backend.figure_extractor.chart_rebuild import render_lieflat_payload
from pragent.backend.figure_extractor.render_final import render_final_html


class ChartRouterBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="autopr-lieflat-test-"))

    def test_payload_without_chart_id_routes_to_f5(self):
        payload = {
            "title_zh": "模型性能排名",
            "data_zh": [["模型A", 81], ["模型B", 93], ["模型C", 87]],
            "semantics": {
                "relation": "ranking",
                "value_kind": "score",
                "unit": "%",
                "ordered": False,
            },
            "explanation_zh": "模型B表现最好。",
        }
        out = self.tmp / "ranking.html"
        path, msg, meta = render_lieflat_payload(payload, out)
        self.assertIsNotNone(path, msg)
        self.assertNotIn("chart_id", payload)
        self.assertEqual(meta["chart_id"], "F5")
        self.assertEqual(meta["relation"], "ranking")
        html = out.read_text(encoding="utf-8")
        self.assertIn('data-chart-id="F5"', html)
        self.assertNotIn("https://", html)

    def test_original_large_values_are_not_scaled(self):
        payload = {
            "title_zh": "样本量排名",
            "data_zh": [["A", 500], ["B", 250]],
            "semantics": {"relation": "ranking", "value_kind": "count", "unit": "个"},
        }
        out = self.tmp / "values.html"
        path, msg, _meta = render_lieflat_payload(payload, out)
        self.assertIsNotNone(path, msg)
        html = out.read_text(encoding="utf-8")
        self.assertIn(">500</text>", html)
        self.assertNotIn(">38</text>", html)

    def test_over_capacity_fails_instead_of_truncating(self):
        payload = {
            "title_zh": "过多类别",
            "data_zh": [[f"C{i}", i + 1] for i in range(9)],
            "semantics": {"relation": "ranking", "value_kind": "count"},
        }
        out = self.tmp / "overflow.html"
        path, msg, _meta = render_lieflat_payload(payload, out)
        self.assertIsNone(path)
        self.assertIn("at most 8 rows", msg)
        self.assertFalse(out.exists())

    def test_invalid_row_fails_without_dropping_it(self):
        payload = {
            "title_zh": "坏数据",
            "data_zh": [["A", 1], ["B", "not-a-number"], ["C", 3]],
            "semantics": {"relation": "comparison"},
        }
        out = self.tmp / "invalid.html"
        path, msg, _meta = render_lieflat_payload(payload, out)
        self.assertIsNone(path)
        self.assertIn("invalid or incomplete", msg)
        self.assertFalse(out.exists())

    def test_reconstructed_chart_is_inserted_into_final_article(self):
        payload = {
            "title_zh": "性能随年份提升",
            "data_zh": [["2024", 70], ["2025", 82], ["2026", 91]],
            "semantics": {"relation": "time_series", "value_kind": "score", "ordered": True},
            "explanation_zh": "性能连续提升。",
        }
        chart = self.tmp / "figure1.html"
        path, msg, meta = render_lieflat_payload(payload, chart)
        self.assertIsNotNone(path, msg)
        manifest = {
            "items": [{
                "kind": "figure",
                "number": 1,
                "file": "unused.png",
                "caption": "Figure 1: benchmark over time",
            }]
        }
        final = self.tmp / "final.html"
        recon = {
            "figure_1": {
                "type": "lieflat",
                "html_path": str(chart),
                "height": 520,
                "explanation_zh": meta["explanation_zh"],
            }
        }
        render_final_html(
            "测试文章\n\n正文引用 Figure 1 展示变化。",
            manifest,
            str(self.tmp),
            str(final),
            reconstructed=recon,
        )
        html = final.read_text(encoding="utf-8")
        self.assertIn("数据图 · lieflat 重构", html)
        self.assertIn("性能连续提升", html)
        self.assertIn("data-chart-id=&quot;F2&quot;", html)

    def test_explicit_title_does_not_drop_first_paragraph(self):
        final = self.tmp / "title.html"
        render_final_html(
            "第一段必须保留。\n\n第二段也要保留。",
            {"items": []},
            str(self.tmp),
            str(final),
            title="独立标题",
        )
        html = final.read_text(encoding="utf-8")
        self.assertIn("<h1>独立标题</h1>", html)
        self.assertIn("<p>第一段必须保留。</p>", html)
        self.assertIn("<p>第二段也要保留。</p>", html)

    def test_title_equal_to_first_block_is_not_duplicated(self):
        final = self.tmp / "dedupe-title.html"
        render_final_html(
            "同一个标题\n\n正文只出现一次。",
            {"items": []},
            str(self.tmp),
            str(final),
            title="同一个标题",
        )
        html = final.read_text(encoding="utf-8")
        self.assertEqual(html.count("同一个标题"), 2)  # <title> + <h1>, no paragraph duplicate
        self.assertNotIn("<p>同一个标题</p>", html)

    def test_fallback_crop_badge_is_not_labeled_as_redraw(self):
        image = self.tmp / "crop.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        final = self.tmp / "fallback.html"
        manifest = {
            "items": [{
                "kind": "figure",
                "number": 1,
                "file": "crop.png",
                "caption": "Figure 1: source crop",
            }]
        }
        render_final_html(
            "正文引用 Figure 1。",
            manifest,
            str(self.tmp),
            str(final),
            reconstructed={
                "figure_1": {
                    "type": "image",
                    "path": str(image),
                    "badge": "原图 · 裁剪",
                }
            },
            title="测试",
        )
        html = final.read_text(encoding="utf-8")
        self.assertIn("原图 · 裁剪", html)
        self.assertNotIn("流程图 · 结构重绘", html)


if __name__ == "__main__":
    unittest.main()
