"""Deterministic Chinese AI-tone QA for AutoPR.

This is a *risk detector*, not an AI-authorship classifier.  It intentionally
uses local, explainable writing-pattern rules and can calibrate against a human
reference corpus.  Several rules and regex ideas are derived from the MIT
licensed `lieflat-less-ai-tone` project and its reproducible measurement
scripts; AutoPR adds publication-specific checks for performative first-person
emotion and empty grand conclusions observed in its own regression articles.

Sentence/paragraph length variation is reported as telemetry only.  The
less-ai-tone corpus study found those features non-discriminative for Chinese,
so they do not contribute to the score and must not be used to force artificial
"burstiness".
"""
from __future__ import annotations

import math
import re
import statistics
from pathlib import Path
from typing import Iterable

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SENT_SPLIT_RE = re.compile(r"[。！？!?]+")

# Whitelist-style, explainable signals.  The weights are severity weights, not
# probabilities.  Corpus calibration decides whether the aggregate density is
# unusual relative to real target-style writing.
_REGEX_RULES = [
    {
        "id": "flip_rhetoric",
        "name": "翻案腔",
        "weight": 2.5,
        "pattern": re.compile(
            r"(?:不是|并非|不在于)[^，。！？\n]{1,28}[，,]?(?:而是|而在于)|"
            r"你以为[^。！？\n]{1,35}(?:其实|实际)|看似[^。！？\n]{1,35}(?:实则|实际)|"
            r"(?:与其说)[^。！？\n]{1,35}(?:不如说)|答案恰恰相反|说到底"
        ),
    },
    {
        "id": "dense_enumeration",
        "name": "顿号罗列过密",
        "weight": 1.2,
        "pattern": re.compile(r"[^，。！？；：、\n]{1,18}、[^，。！？；：、\n]{1,18}、[^，。！？；：、\n]{1,18}"),
    },
    {
        "id": "em_dash_reveal",
        "name": "破折号揭晓/补充",
        "weight": 1.0,
        "pattern": re.compile(r"——"),
    },
    {
        "id": "prompt_colon",
        "name": "提示性冒号",
        "weight": 1.8,
        "pattern": re.compile(
            r"(?:一句话(?:总结|说|概括)|简单说|说白了|总结|小结|结论|"
            r"核心(?:是|在于|观点)?|关键(?:是|在于)?|重点(?:是)?|"
            r"原因(?:如下|有|在于)?|问题(?:是|在于)?|答案(?:是)?|"
            r"本质(?:是|上)?|定义(?:是)?|换句话说|也就是说)[：:]"
        ),
    },
    {
        "id": "idealized_personification",
        "name": "理想化职业拟人",
        "weight": 2.0,
        "pattern": re.compile(
            r"(?:像|就像|好比|仿佛|如同|相当于)(?:给[^，。]{0,12})?(?:一个|一位)"
            r"[^，。]{0,18}(?:导师|秘书|助手|顾问|管家|审查员|实习生|老师|专家)"
        ),
    },
    {
        "id": "banned_starter",
        "name": "套路起手式",
        "weight": 2.0,
        "pattern": re.compile(r"(?:^|[。！？]\s*)(?:说白了|说穿了|先说结论)[，,]?"),
    },
    {
        "id": "long_front_modifier",
        "name": "过长前置定语",
        "weight": 1.1,
        "pattern": re.compile(r"(?:一个|一种|一套|这种|这个)[^，。、；：！？\n]{15,}的[\u4e00-\u9fff]{2,6}"),
    },
    {
        "id": "when_front_clause",
        "name": "当…时前置从句",
        "weight": 0.9,
        "pattern": re.compile(r"(?:^|[。！？]\s*)当[^，。\n]{2,28}(?<!的时候)时[，,]"),
    },
    {
        "id": "topic_shell",
        "name": "前置话题壳",
        "weight": 1.0,
        "pattern": re.compile(
            r"(?:^|[。！？]\s*)(?:对于[^，。\n]{2,18}来说|对[^，。\n]{2,18}而言|"
            r"就[^，。\n]{2,18}而言|在[^，。\n]{2,15}方面)[，,]"
        ),
    },
    {
        "id": "sentence_initial_connector",
        "name": "句首连接词路标",
        "weight": 1.0,
        "pattern": re.compile(r"(?:^|[。！？]\s*)(?:然而|因此|此外|与此同时|换言之|总而言之)[，,]"),
    },
    {
        "id": "this_means_restatement",
        "name": "这意味着/这表明式复述",
        "weight": 1.0,
        "pattern": re.compile(r"(?:这意味着|这表明|这说明|换句话说)"),
    },
    {
        "id": "nominalized_action",
        "name": "动作名词化",
        "weight": 0.9,
        "pattern": re.compile(r"(?:完成|实现|进行|开展)了?(?:对)?[^，。\n]{0,12}的(?:优化|提升|调整|分析|改造|升级)"),
    },
    {
        "id": "performative_emotion",
        "name": "表演式第一人称情绪",
        "weight": 2.2,
        "pattern": re.compile(
            r"(?:我(?:整个人)?(?:直接)?(?:愣|愣住|愣了)|"
            r"我[^。！？]{0,18}(?:愣了|愣住)[^。！？]{0,18}|"
            r"心里[^。！？]{0,14}(?:咯噔|一紧)|后背(?:有点|真的|其实)?(?:发凉|出汗)|"
            r"我盯着[^。！？]{0,35}(?:看了|看着)[^。！？]{0,16}|"
            r"最先扎进我眼睛|让我(?:直接)?(?:愣|后背发凉)|"
            r"我非常理解[^。！？]{0,32}(?:感觉|疲惫|焦虑|无奈|心情|处境)|"
            r"就是单纯的[，,]?想看看)"
        ),
    },
    {
        "id": "grand_conclusion",
        "name": "空泛升华/宏大收束",
        "weight": 1.8,
        "pattern": re.compile(
            r"(?:顺着上面的再聊聊|这背后其实(?:连着|是)|更大的(?:科学|技术|时代|社会)议题|"
            r"这让我想起|这到底是[^。！？]{0,50}还是[^。！？]{0,50}|"
            r"(?:但|不过)?有一点很明确|正在发生(?:深刻|巨大的)(?:的)?变化)"
        ),
    },
    {
        "id": "empty_reaction_shell",
        "name": "空洞共情/反应壳",
        "weight": 2.0,
        "pattern": re.compile(
            r"(?:(?:这种|那种)感觉(?:不难理解|可以理解|很容易理解)|"
            r"(?:^|[。！？]\s*)(?:只是|就是)?(?:单纯地?|单纯的[，,]?)?"
            r"想看看(?:现在)?到底做到哪一步(?:了)?)"
        ),
    },
]

# These are not merely statistical style hints.  A single surviving hit is
# conspicuous enough that AutoPR must keep the selective rewrite loop active
# even when the article-level calibrated score has already dropped below the
# normal threshold.
CRITICAL_RULE_IDS = frozenset({
    "performative_emotion",
    "grand_conclusion",
    "banned_starter",
    "empty_reaction_shell",
})

_COMMENT_START = re.compile(
    r"^(?:听起来|看起来|看上去|听上去|说白了|说到底|换句话说|意味着|"
    r"值得注意|不难看出|细看|再看|回过头看|问题在于|原因在于|结果是|"
    r"有意思的是|更重要的是|关键在于|真正的)"
)
_ANAPHOR = re.compile(
    r"^(?:这|那|其|此|上面|前面|刚才|以上|该|它|他|她|它们|他们|同样|"
    r"类似|相比|反过来|但|不过|所以|因此|于是|而|另|除此|与此)"
)


def _is_protected_block(block: str) -> bool:
    stripped = block.lstrip()
    return stripped.startswith(("```", "|", ">", "- ", "* ", "![", "["))


def split_blocks(text: str) -> list[str]:
    """Split Markdown into blank-line blocks while keeping exact block text."""
    return [b for b in re.split(r"\n\s*\n", text or "") if b.strip()]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if len(s.strip()) >= 2]


def _signature(sentence: str) -> tuple[int, bool, bool, int]:
    return (
        sentence.count("，"),
        "：" in sentence,
        ("（" in sentence or "(" in sentence),
        len(sentence) // 15,
    )


def _isomorphic_hits(block: str) -> list[str]:
    sents = [s for s in _sentences(block) if len(s) > 10]
    quotes: list[str] = []
    for i in range(len(sents) - 1):
        left, right = sents[i], sents[i + 1]
        if _signature(left) == _signature(right) and _signature(left)[0] >= 1:
            quotes.append(left + "。" + right)
    return quotes


def _serial_heading_hits(blocks: list[str]) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []
    rx = re.compile(r"^\s*#{1,6}\s*(?:一|二|三|四|五|六|第一|第二|第三|第四|第五)[、，.．\s]")
    for i, block in enumerate(blocks):
        first = block.strip().splitlines()[0]
        if rx.search(first):
            candidates.append((i, first))
    return candidates if len(candidates) >= 3 else []


def _length_telemetry(blocks: list[str]) -> dict:
    prose = [b for b in blocks if not _is_protected_block(b) and not b.lstrip().startswith("#")]
    para_lengths = [len(_CJK_RE.findall(b)) for b in prose if _CJK_RE.search(b)]
    sent_lengths = [
        len(_CJK_RE.findall(s))
        for b in prose
        for s in _sentences(b)
        if _CJK_RE.search(s)
    ]

    def cv(values: list[int]) -> float:
        if len(values) < 2 or statistics.mean(values) == 0:
            return 0.0
        return statistics.pstdev(values) / statistics.mean(values)

    return {
        "sentence_length_cv": round(cv(sent_lengths), 4),
        "paragraph_length_cv": round(cv(para_lengths), 4),
        "sentence_count": len(sent_lengths),
        "paragraph_count": len(para_lengths),
        "scored": False,
        "note": "descriptive only; Chinese corpus evidence does not support using length variance as an AI tell",
    }


def analyze_raw(text: str) -> dict:
    blocks = split_blocks(text)
    hits: list[dict] = []
    paragraph_scores = [0.0 for _ in blocks]

    for i, block in enumerate(blocks):
        protected = _is_protected_block(block)
        is_heading = block.lstrip().startswith("#")
        if protected:
            continue
        if not is_heading:
            for rule in _REGEX_RULES:
                for match in rule["pattern"].finditer(block):
                    quote = match.group(0).strip()
                    hits.append({
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "paragraph_index": i,
                        "quote": quote[:180],
                        "weight": rule["weight"],
                    })
                    paragraph_scores[i] += float(rule["weight"])

            for quote in _isomorphic_hits(block):
                weight = 1.5
                hits.append({
                    "rule_id": "adjacent_isomorphism",
                    "rule_name": "相邻句结构同款",
                    "paragraph_index": i,
                    "quote": quote[:180],
                    "weight": weight,
                })
                paragraph_scores[i] += weight

            if i > 0:
                stripped = block.strip()
                if _COMMENT_START.match(stripped) and not _ANAPHOR.match(stripped):
                    weight = 1.5
                    hits.append({
                        "rule_id": "zero_subject_comment",
                        "rule_name": "段首零主语评论",
                        "paragraph_index": i,
                        "quote": stripped[:120],
                        "weight": weight,
                    })
                    paragraph_scores[i] += weight

    for i, quote in _serial_heading_hits(blocks):
        weight = 1.5
        hits.append({
            "rule_id": "serial_heading",
            "rule_name": "序数词当小标题",
            "paragraph_index": i,
            "quote": quote[:180],
            "weight": weight,
        })
        paragraph_scores[i] += weight

    cjk_chars = len(_CJK_RE.findall(text or ""))
    raw_weight = sum(h["weight"] for h in hits)
    density = raw_weight / max(cjk_chars / 1000.0, 0.5)
    paragraphs = []
    for i, block in enumerate(blocks):
        if paragraph_scores[i] <= 0:
            continue
        paragraphs.append({
            "paragraph_index": i,
            "risk_weight": round(paragraph_scores[i], 3),
            "text": block[:400],
            "hit_count": sum(1 for h in hits if h["paragraph_index"] == i),
        })

    return {
        "cjk_chars": cjk_chars,
        "raw_weight": round(raw_weight, 3),
        "risk_density_per_1k_cjk": round(density, 4),
        "hit_count": len(hits),
        "hits": hits,
        "flagged_paragraphs": paragraphs,
        "telemetry": _length_telemetry(blocks),
    }


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    data = sorted(values)
    if len(data) == 1:
        return data[0]
    pos = (len(data) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return data[lo]
    frac = pos - lo
    return data[lo] * (1 - frac) + data[hi] * frac


def load_corpus_texts(corpus_dir: str | Path) -> list[str]:
    root = Path(corpus_dir)
    if not root.exists():
        return []
    texts = []
    for path in root.rglob("*.md"):
        if path.parent.name == "_meta":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _CJK_RE.search(text):
            texts.append(text)
    return texts


def calibrate_corpus(texts: Iterable[str]) -> dict:
    densities = [analyze_raw(text)["risk_density_per_1k_cjk"] for text in texts]
    densities = [float(v) for v in densities]
    return {
        "documents": len(densities),
        "p50": round(_quantile(densities, 0.50), 4),
        "p75": round(_quantile(densities, 0.75), 4),
        "p90": round(_quantile(densities, 0.90), 4),
        "p95": round(_quantile(densities, 0.95), 4),
    }


def _calibrated_score(density: float, calibration: dict | None) -> float:
    if not calibration or calibration.get("documents", 0) < 10:
        return min(100.0, density * 12.0)

    p75 = max(float(calibration.get("p75", 0.0)), 0.05)
    p90 = max(float(calibration.get("p90", p75)), p75 + 0.01)
    p95 = max(float(calibration.get("p95", p90)), p90 + 0.01)
    if density <= p75:
        return 30.0 * density / p75
    if density <= p90:
        return 30.0 + 25.0 * (density - p75) / (p90 - p75)
    if density <= p95:
        return 55.0 + 20.0 * (density - p90) / (p95 - p90)
    tail = (density - p95) / max(p95, 0.5)
    return min(100.0, 75.0 + 25.0 * min(1.0, tail))


def analyze_text(text: str, corpus_dir: str | Path | None = None) -> dict:
    report = analyze_raw(text)
    calibration = None
    if corpus_dir:
        calibration = calibrate_corpus(load_corpus_texts(corpus_dir))
    score = round(_calibrated_score(report["risk_density_per_1k_cjk"], calibration), 1)
    verdict = "low"
    if score >= 60:
        verdict = "high"
    elif score >= 35:
        verdict = "medium"

    report.update({
        "risk_score": score,
        "verdict": verdict,
        "calibration": calibration,
        "meaning": "AI-tone risk relative to local writing patterns; not an authorship probability",
    })
    return report


def flagged_paragraph_indexes(report: dict, min_weight: float = 1.0) -> list[int]:
    return sorted({
        int(p["paragraph_index"])
        for p in report.get("flagged_paragraphs", [])
        if float(p.get("risk_weight", 0)) >= min_weight
    })


def critical_hits(report: dict) -> list[dict]:
    return [
        hit for hit in report.get("hits", [])
        if str(hit.get("rule_id")) in CRITICAL_RULE_IDS
    ]


def critical_hit_count(report: dict) -> int:
    return len(critical_hits(report))
