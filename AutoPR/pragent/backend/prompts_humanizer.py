# prompts_humanizer.py
# Humanizer-zh 的「只读质检门禁」接入（方案 C）。
# 来源：op7418/Humanizer-zh（译自 blader/humanizer + hardikpandya/stop-slop，
#       底层 Wikipedia:Signs of AI writing）。
# 定位：只评估、只出定点建议、绝不整篇重写。命中词清单逐条取自 SKILL.md 中文原文。
# 与卡兹克 wechat prompt 的分工：emoji / hashtag / 全角冒号 / 破折号 已由前置正则清理，
# 本质检不重复劳动，只补「语义层 / 结构层」的 AI 腔（卡兹克未覆盖的增量）。

import re
import json

# ------------------------------------------------------------------------------
# 质检 system prompt。强约束：只输出一个 JSON 代码块；quote 必须逐字摘自输入。
# ------------------------------------------------------------------------------
HUMANIZER_QC_SYSTEM_ZH = """你是一位资深文字编辑，专门识别中文文本里的 AI 生成痕迹。你的工作是【只读质检】：扫描下面给出的【待检正文】，找出仍残留的 AI 腔，给每条问题一个可定点修改的建议，并打一个 5 维分数。

# 你的铁律（违反任何一条都算失败）

1. 你【只评估，不重写全文】。绝对不要输出整篇改写后的文章。你只输出一个 JSON 代码块。
2. 你的全部回复【必须且仅是一个 ```json 代码块】，代码块之外不要有任何文字——不要前言、不要"以下是报告"、不要结尾总结、不要解释。
3. 每条命中的 quote 字段，必须是【待检正文】里【逐字复制】的一段连续原文，不得改写、不得增删字、不得调换顺序、不得自己编造。如果你判断某模式存在，但找不到一段能逐字对应到正文的片段，就【不要】把它列入 hits。
4. 前置清理已经把 emoji、话题标签、全角冒号"："、破折号"——" 处理掉了，所以你【不需要】重复报告这些；除非你在正文里确实又发现了漏网的，才报。
5. 只报真正命中的，不要凑数。正文若已经很自然，hits 可以是空数组，这是合格的结果，不是失败。

# 重点扫描的 AI 腔模式（命中词摘自权威清单，逐条对照正文）

[1] 夸大意义与象征：作为/充当/标志着/见证了/是……的体现/证明/提醒、极其重要/至关重要/核心的/关键性的、凸显/强调/彰显了其重要性、反映了更广泛的、象征着、为……做出贡献/奠定基础、关键转折点、不断演变的格局、不可磨灭的印记、深深植根于。
[2] 夸大知名度：独立报道、由知名专家撰写、活跃的社交媒体账号、被……广泛引用（只罗列来源不给上下文）。
[3] 句末肤浅分析：句子末尾挂一个现在分词式的伪深度短语，如"……，突出了/确保了/反映了/象征着/培养了/展示了……"。
[4] 宣传广告腔：充满活力的、深刻的、增强其、致力于、坐落于、位于……的中心、开创性的、令人叹为观止、必游之地、迷人的、无缝、直观而强大。
[5] 模糊归因：行业报告显示、观察者指出、专家认为、一些批评者认为、多个来源/出版物（却无具体出处）。
[6] 套路化"挑战与展望"：尽管其……面临若干挑战、尽管存在这些挑战、挑战与遗产、未来展望。
[7] 高频 AI 词汇：此外、与……保持一致、深入探讨、持久的、增强、培养、获得、突出(作动词)、相互作用、复杂性、格局(抽象名词)、织锦(抽象名词)、宝贵的、充满活力的。
[8] 回避系动词"是/有"：用"作为/代表/标志着/充当/设有/提供/拥有"绕开简单的"是/有"。
[9] 否定式排比：不仅……而且……、这不仅仅是……而是……、不只是……更是……。
[10] 三段式凑数：把想法强行分成三项以显得全面（两项或四项往往更自然）。
[11] 同义词循环：为避免重复而机械换词，如"主人公→主要角色→中心人物→英雄"指同一对象。
[12] 虚假范围：用"从 X 到 Y"结构，但 X 与 Y 并不在同一有意义的尺度上。
[13] 粗体过度：机械地用 **粗体** 强调一堆短语。
[14] 内联标题竖列表：列表项以"粗体标题＋冒号"开头的垂直罗列。
[15] 协作交流痕迹：希望这对您有帮助、当然！、请告诉我、这是一个……（聊天口吻混进正文）。
[16] 知识截止免责：截至[日期]、根据我最后的训练更新、虽然具体细节有限、基于可用信息。
[17] 谄媚语气：好问题！、您说得完全正确、这是一个很好的观点。
[18] 填充短语：值得注意的是、在这个时间点、为了实现这一目标、由于……的事实、系统具有……的能力。
[19] 过度限定：可以潜在地可能被认为……可能会……一些影响（层层弱化）。
[20] 通用积极结尾：未来看起来光明、激动人心的时代即将到来、向正确方向迈出的重要一步、继续追求卓越的旅程。

# 评分（5 维，每维 0-10，总 50；对照正文如实打分）

directness 直接性：直截了当陈述，还是绕圈宣告、铺垫一堆？
rhythm 节奏：句子长短是否交错，还是机械等长？
trust 信任度：是否尊重读者智慧、简洁明了，还是过度解释、手把手？
authenticity 真实性：听起来像真人在说话，还是机械生硬、无菌中立？
concision 精炼度：还有无可删的冗余废话？

verdict 取值：total 在 45-50 为 "excellent"，35-44 为 "good"，低于 35 为 "needs_revision"。

# 输出 JSON 结构（严格照此，字段名不要改）

```json
{
  "scores": {"directness": 0, "rhythm": 0, "trust": 0, "authenticity": 0, "concision": 0, "total": 0},
  "hits": [
    {"id": 7, "name": "高频 AI 词汇", "quote": "从正文逐字复制的片段", "fix": "一句具体的改法建议"}
  ],
  "verdict": "good"
}
```

只输出这一个 JSON 代码块，块外无任何文字。
"""


_FENCED = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _extract_json(raw: str):
    """从模型回复里抠出 JSON 对象。先试 fenced 代码块，再试首尾大括号兜底。"""
    if not raw:
        return None
    m = _FENCED.search(raw)
    candidates = []
    if m:
        candidates.append(m.group(1).strip())
    # 兜底：第一个 { 到最后一个 }
    first = raw.find("{")
    last = raw.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidates.append(raw[first:last + 1].strip())
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def build_humanizer_report(raw: str, text: str, model: str = "qwen3.8-max-preview"):
    """纯函数：解析质检模型回复，做 quote 对齐校验，返回 (parsed, report_md)。

    parsed 为解析出的 dict（解析失败时为 None）。report_md 为可读报告字符串。
    本函数不读写任何文件，落盘由调用方负责。
    """
    parsed = _extract_json(raw)
    lines = []
    lines.append("# Humanizer-zh 质检报告（只读门禁 · 未改动正文）")
    lines.append("")
    lines.append(f"- 质检模型：{model}")
    lines.append("- 被检文本：post_output/post.md 的 clean 版")
    lines.append("- 性质：只评估、只给定点建议；正文是否据此修改，由人工/后续定点 edit 决定")
    lines.append("")

    if parsed is None:
        lines.append("## ⚠ 解析失败")
        lines.append("")
        lines.append("质检模型未按约定输出可解析的 JSON，以下为原始回复，需人工判读。")
        lines.append("")
        lines.append("```")
        lines.append((raw or "").strip())
        lines.append("```")
        return None, "\n".join(lines)

    scores = parsed.get("scores") or {}
    dims = [("directness", "直接性"), ("rhythm", "节奏"), ("trust", "信任度"),
            ("authenticity", "真实性"), ("concision", "精炼度")]
    lines.append("## 评分（5 维 / 50）")
    lines.append("")
    lines.append("| 维度 | 得分 |")
    lines.append("|------|------|")
    for key, zh in dims:
        lines.append(f"| {zh} | {scores.get(key, '?')} |")
    lines.append(f"| **总分** | **{scores.get('total', '?')}** |")
    lines.append("")
    lines.append(f"**verdict**：{parsed.get('verdict', '?')}")
    lines.append("")

    hits = parsed.get("hits") or []
    aligned_n = 0
    lines.append(f"## 命中清单（{len(hits)} 条）")
    lines.append("")
    if not hits:
        lines.append("（无命中：正文在该质检视角下已较干净。）")
        lines.append("")
    for i, h in enumerate(hits, 1):
        quote = h.get("quote", "")
        aligned = bool(quote) and (quote in text)
        if aligned:
            aligned_n += 1
        tag = "可定点 patch" if aligned else "quote 未对齐·需人工"
        lines.append(f"### {i}. [{h.get('id', '?')}] {h.get('name', '?')}　（{tag}）")
        lines.append("")
        lines.append(f"> {quote}")
        lines.append("")
        lines.append(f"建议：{h.get('fix', '—')}")
        lines.append("")
    if hits:
        lines.append(f"_对齐统计：{aligned_n}/{len(hits)} 条 quote 可在正文逐字定位，其余需人工判读。_")
        lines.append("")

    lines.append("<details><summary>原始模型 JSON（参考）</summary>")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(parsed, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("</details>")

    return parsed, "\n".join(lines)
