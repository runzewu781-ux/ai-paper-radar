import tempfile
import unittest
from pathlib import Path

from pragent.backend.ai_tone_detector import (
    analyze_text,
    critical_hit_count,
    flagged_paragraph_indexes,
)


class AIToneDetectorTests(unittest.TestCase):
    def test_explainable_rules_flag_obvious_ai_tells(self):
        text = (
            "# 测试\n\n"
            "这不是一个工具的问题，而是一个思维方式的问题。\n\n"
            "我盯着这组结果看了好一会儿，心里确实咯噔了一下。\n\n"
            "此外，这意味着整个行业正在发生深刻的变化。"
        )
        report = analyze_text(text)
        ids = {hit["rule_id"] for hit in report["hits"]}
        self.assertIn("flip_rhetoric", ids)
        self.assertIn("performative_emotion", ids)
        self.assertIn("this_means_restatement", ids)
        self.assertIn("grand_conclusion", ids)
        self.assertGreater(report["risk_score"], 20)
        self.assertTrue(flagged_paragraph_indexes(report))

    def test_length_variance_is_telemetry_only(self):
        text = "短句。\n\n这是一个明显更长但仍然只是普通陈述的段落，它没有任何需要被判定为人工智能写作痕迹的固定模式。"
        report = analyze_text(text)
        self.assertFalse(report["telemetry"]["scored"])
        self.assertEqual(report["hit_count"], 0)
        self.assertEqual(report["risk_score"], 0.0)

    def test_performative_emotion_is_a_critical_hit_even_in_short_text(self):
        report = analyze_text("我心里其实咯噔了一下。就是单纯的，想看看现在到底做到哪一步了。")
        self.assertGreaterEqual(critical_hit_count(report), 1)
        self.assertIn("performative_emotion", {h["rule_id"] for h in report["hits"]})

    def test_empty_reaction_shell_is_critical(self):
        report = analyze_text("这种感觉不难理解。想看看现在到底做到哪一步了。")
        self.assertGreaterEqual(critical_hit_count(report), 1)
        self.assertIn("empty_reaction_shell", {h["rule_id"] for h in report["hits"]})

    def test_performative_emotion_variants_cannot_evade_with_inserted_words(self):
        report = analyze_text(
            "读到那张表的时候，我坐在屏幕前愣了好一会儿。"
            "我非常理解那种科研人员不得不做宣发的疲惫感，心里还是难免咯噔了一下。"
        )
        self.assertGreaterEqual(critical_hit_count(report), 1)
        self.assertIn("performative_emotion", {h["rule_id"] for h in report["hits"]})

    def test_local_human_corpus_calibrates_score_without_claiming_probability(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            samples = [
                "研究人员记录了实验结果。数据见论文附表。",
                "这项工作比较了两种方法，结果给出了具体数值。",
                "文章介绍了实验流程，也说明了研究限制。",
                "团队分析了样本，并报告测量结果。",
                "论文讨论了方法设计和实验设置。",
                "结果部分列出主要指标，附录提供更多细节。",
                "研究采用公开数据集进行比较。",
                "作者在讨论部分说明了局限性。",
                "实验重复进行，结果保持一致。",
                "表格给出了不同模型的评分。",
                "图中比较了两个条件下的结果。",
                "文章最后总结了研究发现。",
            ]
            for i, sample in enumerate(samples):
                (root / f"h{i}.md").write_text(sample, encoding="utf-8")

            suspicious = "不是模型不够强，而是思路错了。说到底，这背后其实连着更大的时代议题。"
            report = analyze_text(suspicious, corpus_dir=root)
            self.assertEqual(report["calibration"]["documents"], len(samples))
            self.assertGreaterEqual(report["risk_score"], 60)
            self.assertIn(report["verdict"], {"medium", "high"})
            self.assertIn("not an authorship probability", report["meaning"])


if __name__ == "__main__":
    unittest.main()
