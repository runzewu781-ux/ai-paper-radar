import tempfile
import unittest
from pathlib import Path

from pragent.layout.chart_rebuild import render_lieflat_payload
from pragent.layout.render_final import render_final_html
from pragent.layout.structure_rebuild import render_structure_svg


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
        self.assertIn("数据图 · 中文重构", html)
        self.assertIn("性能连续提升", html)
        self.assertIn("data-chart-id=&quot;F2&quot;", html)
        self.assertIn("查看 Figure 1 的论文英文题注", html)

    def test_structure_svg_is_chinese_primary_visual(self):
        svg = self.tmp / "figure3.svg"
        path = render_structure_svg(
            {
                "role": "三阶段流程",
                "stages": ["内容提取", "多智能体内容合成", "平台适配"],
                "flow": "论文先被拆成文本和图表，再由多个智能体协作生成草稿，最后按平台要求调整。",
                "keep": ["PyMuPDF", "DocLayout-YOLO", "PRAgent"],
            },
            svg,
            title="Figure 3 · 中文流程重绘",
            number=3,
        )
        self.assertEqual(path, str(svg))
        source = svg.read_text(encoding="utf-8")
        self.assertIn("内容提取", source)
        self.assertIn("多智能体内容合成", source)
        self.assertIn("平台适配", source)

        final = self.tmp / "structure-final.html"
        manifest = {
            "items": [{
                "kind": "figure",
                "number": 3,
                "file": "unused.png",
                "caption": "Figure 3: original English workflow",
            }]
        }
        render_final_html(
            "正文引用 Figure 3。",
            manifest,
            str(self.tmp),
            str(final),
            reconstructed={
                "figure_3": {
                    "type": "structure_svg",
                    "path": str(svg),
                    "badge": "流程图 · 中文重绘",
                    "explanation_zh": "论文经过内容提取、协同写作和平台适配三个阶段。",
                }
            },
            title="测试",
        )
        html = final.read_text(encoding="utf-8")
        self.assertIn("流程图 · 中文重绘", html)
        self.assertIn("data:image/svg+xml;base64,", html)
        self.assertIn("查看 Figure 3 的论文英文题注", html)

    def test_original_reference_is_collapsed_behind_chinese_explanation(self):
        image = self.tmp / "source.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        final = self.tmp / "reference-only.html"
        manifest = {
            "items": [{
                "kind": "figure",
                "number": 8,
                "file": "source.png",
                "caption": "Figure 8: dense English source screenshot",
            }]
        }
        render_final_html(
            "正文引用 Figure 8。",
            manifest,
            str(self.tmp),
            str(final),
            reconstructed={
                "figure_8": {
                    "type": "image",
                    "path": str(image),
                    "badge": "论文原图 · 供核对",
                    "explanation_zh": "这是面向中文读者的主要解读。",
                    "original_as_reference": True,
                }
            },
            title="测试",
        )
        html = final.read_text(encoding="utf-8")
        self.assertIn("这是面向中文读者的主要解读。", html)
        self.assertIn("查看 Figure 8 论文原图（英文，供核对）", html)
        self.assertIn("<details class=\"source-details\">", html)

    def test_original_image_can_be_primary_visual(self):
        image = self.tmp / "paper-original.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        final = self.tmp / "original-primary.html"
        manifest = {
            "items": [{
                "kind": "figure",
                "number": 5,
                "file": "paper-original.png",
                "caption": "Figure 5: original English chart",
            }]
        }
        render_final_html(
            "正文引用 Figure 5。",
            manifest,
            str(self.tmp),
            str(final),
            reconstructed={
                "figure_5": {
                    "type": "image",
                    "path": str(image),
                    "badge": "论文原图",
                    "visual_mode": "original",
                }
            },
            title="测试",
        )
        html = final.read_text(encoding="utf-8")
        self.assertIn("论文原图", html)
        self.assertIn("data:image/png;base64,", html)
        self.assertNotIn("数据图 · 中文重构", html)
        self.assertNotIn("流程图 · 中文重绘", html)
        self.assertNotIn("查看 Figure 5 论文原图（英文，供核对）", html)
        self.assertIn("查看 Figure 5 的论文英文题注", html)

    def test_verified_skill_html_can_be_embedded_directly(self):
        skill_html = self.tmp / "figure5-skill.html"
        skill_html.write_text(
            '<!doctype html><html><body><div data-template-id="F12">Skill chart</div></body></html>',
            encoding="utf-8",
        )
        final = self.tmp / "skill-primary.html"
        manifest = {
            "items": [{
                "kind": "figure",
                "number": 5,
                "file": "unused.png",
                "caption": "Figure 5: original source",
            }]
        }
        render_final_html(
            "正文引用 Figure 5。",
            manifest,
            str(self.tmp),
            str(final),
            reconstructed={
                "figure_5": {
                    "type": "skill_html",
                    "html_path": str(skill_html),
                    "height": 560,
                    "badge": "Lieflat Skill · 原版模板",
                }
            },
            title="测试",
        )
        html = final.read_text(encoding="utf-8")
        self.assertIn("Lieflat Skill · 原版模板", html)
        self.assertIn("data-template-id=&quot;F12&quot;", html)
        self.assertNotIn("数据图 · 中文重构", html)

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
