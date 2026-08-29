"""Selective less-AI-tone rewrite bridge for AutoPR.

The external lieflat-less-ai-tone Skill is treated as a policy document, not as
an invitation to rewrite the whole article.  AutoPR first runs its deterministic
local detector, sends only flagged prose blocks to the LLM, then accepts a patch
only when publication-critical invariants are unchanged.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .agents import setup_client, call_text_llm_api
from .ai_tone_detector import CRITICAL_RULE_IDS, split_blocks

_NUMBER_RE = re.compile(r'(?<![A-Za-z0-9])(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:[%％])?')
_REF_RE = re.compile(r'\b(?:Figure|Fig\.?|Table)\s*[:：]?\s*\d+\b', re.IGNORECASE)
_URL_RE = re.compile(r'https?://[^\s<>)\]]+')
_TECH_RE = re.compile(r'(?<![A-Za-z0-9])(?:[A-Za-z][A-Za-z0-9_.+/-]*[A-Za-z0-9]|[A-Za-z]{2,})(?![A-Za-z0-9])')
_HEADING_RE = re.compile(r'^\s*#{1,6}\s+', re.MULTILINE)
_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
_CN_QUANT_RE = re.compile(
    r'(?:约|近|超过|不足|至少|至多|大约)?(?:数十|数百|数千|数万|上百|上千|上万|'
    r'百余|千余|万余|几十|几百|几千|几万)(?:个|篇|项|次|人|组|倍|年|天|小时|分钟|秒)?'
)

# These words materially change scientific claim strength or logical status.
# Exact counts are deliberately conservative; rejected rewrites fall back to
# the already grounded paragraph rather than trying to "fix" a risky patch.
_QUALIFIERS = (
    "可能", "或许", "大约", "约", "至少", "至多", "最多", "仅", "仅在", "只有",
    "通常", "一般", "部分", "全部", "显著", "轻微", "相关", "相关性", "因果",
    "不能", "无法", "尚未", "未", "不一定", "并不", "并非", "几乎", "近似",
)

_CUSTOM_RULE_HELP = {
    "performative_emotion": (
        "AutoPR附加规则：去掉伪造作者现场感或表演式第一人称情绪，例如“我愣了”“心里咯噔”"
        "“后背发凉”“我盯着看了很久”。只去掉这种表演框架；不能制造新的个人经历、读者心理或事实。"
    ),
    "grand_conclusion": (
        "AutoPR附加规则：收掉没有材料承载的宏大升华和万能结尾。保留原有事实与明确观点；"
        "不要补行业趋势、时代意义或价值判断。"
    ),
    "empty_reaction_shell": (
        "AutoPR附加规则：删除空洞的共情、观看反应或过渡壳，直接进入下一条有信息量的陈述；"
        "不要用另一句‘值得注意/不难理解/让人感慨’替换。"
    ),
}


def resolve_skill_path(explicit: str | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    for key in ("AUTOPR_LESS_AI_SKILL", "LESS_AI_TONE_SKILL"):
        value = os.getenv(key, "").strip()
        if value:
            candidates.append(Path(value))

    here = Path(__file__).resolve()
    # .../科普工作流/ai-paper-radar/AutoPR/pragent/backend/less_ai_tone.py
    try:
        workspace = here.parents[4]
        candidates.append(workspace / "lieflat-less-ai-tone" / "SKILL.md")
    except IndexError:
        pass

    for candidate in candidates:
        path = candidate.expanduser()
        if path.is_dir():
            path = path / "SKILL.md"
        if path.exists() and path.is_file():
            return path.resolve()
    return None


def load_skill_text(explicit: str | None = None) -> tuple[str, str]:
    path = resolve_skill_path(explicit)
    if path is None:
        return "", ""
    return path.read_text(encoding="utf-8"), str(path)


def _normalized_numbers(text: str) -> Counter:
    return Counter(token.replace(",", "").replace("％", "%") for token in _NUMBER_RE.findall(text or ""))


def _refs(text: str) -> Counter:
    return Counter(re.sub(r"\s+", " ", x).lower() for x in _REF_RE.findall(text or ""))


def _urls(text: str) -> Counter:
    return Counter(_URL_RE.findall(text or ""))


def _tech_tokens(text: str) -> Counter:
    # Preserve model/dataset/method names and English technical identifiers.
    return Counter(token.casefold() for token in _TECH_RE.findall(text or ""))


def _qualifiers(text: str) -> Counter:
    return Counter({q: text.count(q) for q in _QUALIFIERS if text.count(q)})


def _chinese_quantifiers(text: str) -> Counter:
    return Counter(_CN_QUANT_RE.findall(text or ""))


def publication_fingerprint(text: str) -> dict[str, Any]:
    return {
        "numbers": _normalized_numbers(text),
        "refs": _refs(text),
        "urls": _urls(text),
        "tech_tokens": _tech_tokens(text),
        "qualifiers": _qualifiers(text),
        "chinese_quantifiers": _chinese_quantifiers(text),
        "image_tags": Counter(_IMAGE_RE.findall(text or "")),
        "heading_count": len(_HEADING_RE.findall(text or "")),
    }


def validate_rewrite(original: str, rewritten: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not rewritten or not rewritten.strip():
        return False, ["empty rewrite"]
    before = publication_fingerprint(original)
    after = publication_fingerprint(rewritten)
    for key in (
        "numbers", "refs", "urls", "tech_tokens", "qualifiers",
        "chinese_quantifiers", "image_tags", "heading_count",
    ):
        if before[key] != after[key]:
            reasons.append(f"{key} changed")
    if "\n\n" in rewritten.strip():
        reasons.append("rewrite introduced a new paragraph boundary")
    return not reasons, reasons


def _json_object(text: str) -> dict:
    match = re.search(r'\{[\s\S]*\}', text or "")
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _protected_block(block: str) -> bool:
    stripped = block.lstrip()
    return stripped.startswith(("#", "```", "|", ">", "- ", "* ", "![", "["))


def _rules_for_paragraph(report: dict, paragraph_index: int) -> list[dict]:
    return [
        hit for hit in report.get("hits", [])
        if int(hit.get("paragraph_index", -1)) == paragraph_index
    ]


def _rewrite_system(skill_text: str) -> str:
    return (
        "你是 AutoPR 的中文成稿清理编辑。下面的外部 Skill 是主要规则来源。"
        "你只能改本次明确命中的规则，不得顺便润色。未命中的信息必须保持。\n\n"
        "===== lieflat-less-ai-tone SKILL =====\n"
        + skill_text
        + "\n\n===== AutoPR 额外硬约束 =====\n"
        "1. 只修改当前一个段落，不新增/删除段落。\n"
        "2. 姓名、机构、论文方法、模型/数据集名称、数字、单位、日期、Figure/Table 引用、URL、"
        "因果关系和限定词不得新增、删除或改变强度。\n"
        "3. 不得为了所谓 burstiness 调句长；句长/段长波动不是本项目的 AI 味判据。\n"
        "4. 如果命中属于正常科研列举、必要术语、引用、操作步骤或 Skill 明确豁免情形，返回 changed=false。\n"
        "5. 只返回严格 JSON，不要 Markdown 代码块。"
    )


async def rewrite_flagged_paragraphs(
    text: str,
    report: dict,
    api_key: str,
    api_base: str,
    model: str,
    *,
    style_guide: str | None = None,
    skill_path: str | None = None,
    min_weight: float = 1.0,
) -> tuple[str, dict]:
    """Rewrite only detector-flagged blocks; reject patches that break invariants."""
    skill_text, resolved_skill = load_skill_text(skill_path)
    if not skill_text:
        return text, {
            "enabled": False,
            "reason": "lieflat-less-ai-tone SKILL.md not found",
            "changed_paragraphs": [],
            "rejected_paragraphs": [],
        }

    blocks = split_blocks(text)
    target_indexes = {
        int(p["paragraph_index"])
        for p in report.get("flagged_paragraphs", [])
        if float(p.get("risk_weight", 0)) >= min_weight
    }
    changed: list[dict] = []
    rejected: list[dict] = []
    unchanged_by_model: list[int] = []
    system = _rewrite_system(skill_text)

    async with setup_client(api_key, api_base) as client:
        for index in sorted(target_indexes):
            if index < 0 or index >= len(blocks):
                continue
            original = blocks[index]
            if _protected_block(original):
                continue
            hits = _rules_for_paragraph(report, index)
            hit_ids = [str(hit.get("rule_id")) for hit in hits]
            critical_ids = [rule_id for rule_id in hit_ids if rule_id in CRITICAL_RULE_IDS]
            extra = [
                _CUSTOM_RULE_HELP[rule_id]
                for rule_id in hit_ids
                if rule_id in _CUSTOM_RULE_HELP
            ]
            previous = blocks[index - 1] if index > 0 else ""
            following = blocks[index + 1] if index + 1 < len(blocks) else ""
            prompt = {
                "paragraph_index": index,
                "detector_hits": hits,
                "critical_hits": critical_ids,
                "critical_policy": (
                    "若 critical_hits 非空，这些是 AutoPR 已确认必须处理的模式，不属于可豁免的普通科研列举。"
                    "除非任何改写都会破坏事实/数字/限定词，否则必须 changed=true，并只移除该模式的修辞外壳。"
                    if critical_ids else "无 critical hit；正常科研列举或必要术语可以豁免。"
                ),
                "autopr_extra_rules": extra,
                "style_guide": style_guide or "",
                "previous_context_read_only": previous,
                "target_paragraph": original,
                "next_context_read_only": following,
                "output_schema": {
                    "changed": "boolean",
                    "rules_applied": ["rule_id"],
                    "text": "rewritten target paragraph only",
                    "reason": "brief reason or exemption",
                },
            }
            raw = await call_text_llm_api(
                client,
                system,
                json.dumps(prompt, ensure_ascii=False),
                model,
            )
            parsed = _json_object(raw)
            if not parsed:
                rejected.append({"paragraph_index": index, "reason": ["invalid JSON response"]})
                continue
            if parsed.get("changed") is not True:
                unchanged_by_model.append(index)
                continue
            candidate = str(parsed.get("text") or "").strip()
            ok, reasons = validate_rewrite(original, candidate)
            if not ok:
                rejected.append({
                    "paragraph_index": index,
                    "reason": reasons,
                    "rules": hit_ids,
                })
                continue
            blocks[index] = candidate
            changed.append({
                "paragraph_index": index,
                "rules": hit_ids,
                "rules_applied": parsed.get("rules_applied") or [],
            })

    rewritten = "\n\n".join(blocks)
    if len(split_blocks(rewritten)) != len(blocks):
        # This should be impossible after per-block validation, but fail closed.
        return text, {
            "enabled": True,
            "skill_path": resolved_skill,
            "reason": "global paragraph invariant failed; reverted all rewrites",
            "changed_paragraphs": [],
            "rejected_paragraphs": rejected,
        }

    return rewritten, {
        "enabled": True,
        "skill_path": resolved_skill,
        "target_paragraphs": sorted(target_indexes),
        "changed_paragraphs": changed,
        "rejected_paragraphs": rejected,
        "unchanged_by_model": unchanged_by_model,
    }
