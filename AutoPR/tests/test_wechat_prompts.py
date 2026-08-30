import unittest

from pragent.writing.prompts_wechat import (
    WECHAT_DRAFT_PROMPT_CHINESE,
    WECHAT_RICH_PROMPT_CHINESE,
    WECHAT_TEXT_ONLY_PROMPT_CHINESE,
)


class WeChatPromptSafetyTests(unittest.TestCase):
    def test_prompts_do_not_require_performative_humanization(self):
        old_directives = (
            "要有真实的阅读体感",
            "把这种真实的阅读体感写进去",
            "至少一处文化升维",
            "全文至少有三处让一个极短的句子",
            "讲观点前先站到读者的处境里",
        )
        for prompt in (
            WECHAT_DRAFT_PROMPT_CHINESE,
            WECHAT_RICH_PROMPT_CHINESE,
            WECHAT_TEXT_ONLY_PROMPT_CHINESE,
        ):
            for directive in old_directives:
                self.assertNotIn(directive, prompt)

    def test_prompts_explicitly_forbid_fabricated_first_person_reaction(self):
        self.assertIn("不虚构自己读论文时的现场、动作或情绪", WECHAT_DRAFT_PROMPT_CHINESE)
        self.assertIn("禁止虚构第一人称阅读体感", WECHAT_RICH_PROMPT_CHINESE)
        self.assertIn("不虚构个人阅读经历或情绪反应", WECHAT_TEXT_ONLY_PROMPT_CHINESE)


if __name__ == "__main__":
    unittest.main()
