import unittest

from pragent.ai_denoise.less_ai_tone import (
    publication_fingerprint,
    resolve_skill_path,
    validate_rewrite,
)


class LessAIToneInvariantTests(unittest.TestCase):
    def test_external_skill_is_discovered_from_workspace(self):
        path = resolve_skill_path()
        self.assertIsNotNone(path)
        self.assertEqual(path.name, "SKILL.md")
        self.assertEqual(path.parent.name, "lieflat-less-ai-tone")

    def test_safe_style_only_rewrite_preserves_scientific_invariants(self):
        original = (
            "这不是 GPT-5 的数字问题，而是表达问题。Figure 5 显示 PRAgent 的浏览量从 "
            "1178 增到 5059，提升约 329%。"
        )
        rewritten = (
            "表达方式才是问题。GPT-5 的数字没有变化。Figure 5 显示 PRAgent 的浏览量从 "
            "1178 增到 5059，提升约 329%。"
        )
        ok, reasons = validate_rewrite(original, rewritten)
        self.assertTrue(ok, reasons)
        self.assertEqual(publication_fingerprint(original), publication_fingerprint(rewritten))

    def test_rewrite_is_rejected_when_number_changes(self):
        ok, reasons = validate_rewrite(
            "Table 6 中 PRAgent 获胜 64.8%。",
            "Table 6 中 PRAgent 获胜 65%。",
        )
        self.assertFalse(ok)
        self.assertIn("numbers changed", reasons)

    def test_rewrite_is_rejected_when_figure_reference_disappears(self):
        ok, reasons = validate_rewrite(
            "结果见 Figure 5，PRAgent 使用 GPT-5。",
            "结果见图中，PRAgent 使用 GPT-5。",
        )
        self.assertFalse(ok)
        self.assertIn("refs changed", reasons)

    def test_rewrite_is_rejected_when_model_name_or_qualifier_changes(self):
        ok, reasons = validate_rewrite(
            "GPT-5 的结果可能与 Qwen3-32B 不同。",
            "GPT-5 的结果与 Qwen3 不同。",
        )
        self.assertFalse(ok)
        self.assertIn("tech_tokens changed", reasons)
        self.assertIn("qualifiers changed", reasons)

    def test_rewrite_cannot_split_one_paragraph_into_two(self):
        ok, reasons = validate_rewrite("这不是终点，而是开始。", "这是开始。\n\n后面继续。")
        self.assertFalse(ok)
        self.assertIn("rewrite introduced a new paragraph boundary", reasons)

    def test_chinese_quantity_scale_is_protected(self):
        ok, reasons = validate_rewrite(
            "NeurIPS 每年录用数千篇论文。",
            "NeurIPS 每年录用数百篇论文。",
        )
        self.assertFalse(ok)
        self.assertIn("chinese_quantifiers changed", reasons)

    def test_markdown_image_reference_is_protected(self):
        ok, reasons = validate_rewrite(
            "结果如下。![Figure 5](figures/figure_5.png)",
            "结果如下。![Figure 5](figures/figure_6.png)",
        )
        self.assertFalse(ok)
        self.assertIn("image_tags changed", reasons)


if __name__ == "__main__":
    unittest.main()
