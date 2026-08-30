"""公众号文风蒸馏。

支持一个或多个本地语料目录（每篇文章一个 .txt/.md 文件），先分块蒸馏，
再把各块风格画像汇总成统一画像，避免大语料一次性塞入上下文。

输出：
- profile: 结构化风格画像
- style_guide: 可直接注入公众号生成提示词的风格指南
- sources: 实际读取的语料目录与文章数量
"""
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from pragent.core.agents import setup_client, call_text_llm_api
except ImportError:
    from pragent.core.agents import setup_client, call_text_llm_api


_DISTILL_SYSTEM = (
    "你是中文写作风格分析师。我给你一批真实公众号长文的正文，你要从中提炼出这些文章共有的写作风格，"
    "用于指导 AI 复刻该风格。只分析 HOW（怎么写），不要学习或复述 WHAT（具体事实与观点）。"
    "请输出严格 JSON，字段如下：\n"
    "{\n"
    "  \"structure\": \"文章整体结构怎么组织（开头如何切入、中间如何推进、结尾如何收）\",\n"
    "  \"opening\": \"开头段的典型写法与第一句的气口\",\n"
    "  \"transitions\": \"段落间如何衔接（转场句/意象/留白）\",\n"
    "  \"sentence_rhythm\": \"句式长短、标点、断句、节奏特点\",\n"
    "  \"tone\": \"叙述者姿态、语气、视角（第一二人称？说教还是共情？）\",\n"
    "  \"vocabulary\": \"高频表达类型、口语化程度、术语处理方式；不要照抄来源的独特句子\",\n"
    "  \"avoid\": \"这批文章里通常避免的写法/词/腔调\",\n"
    "  \"voice\": \"一句话概括这批文章共有的声音\"\n"
    "}"
    "只输出 JSON，不要解释。"
)

_MERGE_SYSTEM = (
    "你是中文写作风格总编。下面给你多组从真实文章分块提炼出的风格画像。"
    "请找出稳定、反复出现的共同写法；忽略偶发特征和具体内容事实。"
    "输出与输入相同字段的严格 JSON：structure, opening, transitions, sentence_rhythm, tone, vocabulary, avoid, voice。"
    "不要解释，不要复制原文句子。"
)

_STYLE_GUIDE_TEMPLATE = (
    "以下是从真实科普公众号语料中蒸馏出的文风指南，写作时必须遵循其抽象写法，"
    "但不得复刻来源文章的独特句子、事实表述或标题。\n"
    "# 结构\n{structure}\n"
    "# 开头\n{opening}\n"
    "# 段落衔接\n{transitions}\n"
    "# 句式与节奏\n{sentence_rhythm}\n"
    "# 语气与视角\n{tone}\n"
    "# 用词\n{vocabulary}\n"
    "# 绝对要避免\n{avoid}\n"
    "# 总体声音\n{voice}\n"
)

_PROFILE_KEYS = (
    "structure", "opening", "transitions", "sentence_rhythm",
    "tone", "vocabulary", "avoid", "voice",
)


def _chunk_texts(texts: Sequence[str], max_chars: int = 60000) -> List[str]:
    """按文章边界分块，避免切断单篇文章。"""
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for raw in texts:
        text = raw.strip()
        if not text:
            continue
        extra = len(text) + (20 if current else 0)
        if current and current_len + extra > max_chars:
            chunks.append("\n\n===== 文章分隔 =====\n\n".join(current))
            current = [text]
            current_len = len(text)
        else:
            current.append(text)
            current_len += extra
    if current:
        chunks.append("\n\n===== 文章分隔 =====\n\n".join(current))
    return chunks


def _parse_profile(raw: str) -> Dict[str, str]:
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(raw[start:end + 1])
            if isinstance(data, dict):
                return {k: str(data.get(k, "")).strip() for k in _PROFILE_KEYS}
    except Exception:
        pass
    return {"raw": raw}


def _make_guide(profile: Dict[str, str]) -> str:
    if all(k in profile for k in _PROFILE_KEYS):
        return _STYLE_GUIDE_TEMPLATE.format(**profile)
    return str(profile.get("raw", ""))


async def _call_profile(system: str, user: str, api_key: str, api_base: str, model: str) -> Dict[str, str]:
    async with setup_client(api_key, api_base) as client:
        raw = await call_text_llm_api(client, system, user, model)
    return _parse_profile(raw or "")


async def distill_style(
    article_texts: List[str],
    api_key: str,
    api_base: str,
    model: str = "qwen3.8-max-preview",
    max_chars: int = 60000,
) -> dict:
    """分块蒸馏后汇总，返回 {'profile': ..., 'style_guide': ...}。"""
    chunks = _chunk_texts(article_texts, max_chars=max_chars)
    if not chunks:
        return {}

    partials: List[Dict[str, str]] = []
    for index, chunk in enumerate(chunks, start=1):
        profile = await _call_profile(
            _DISTILL_SYSTEM,
            f"这是第 {index}/{len(chunks)} 组文章。请提炼共有写作风格：\n\n{chunk}",
            api_key, api_base, model,
        )
        partials.append(profile)

    if len(partials) == 1:
        profile = partials[0]
    else:
        profile = await _call_profile(
            _MERGE_SYSTEM,
            "分块风格画像如下，请汇总稳定的共同风格：\n\n" +
            json.dumps(partials, ensure_ascii=False, indent=2),
            api_key, api_base, model,
        )

    return {
        "profile": profile,
        "style_guide": _make_guide(profile),
        "chunks": len(chunks),
    }


def _read_dirs(dir_paths: Sequence[str]) -> Tuple[List[str], List[dict]]:
    texts: List[str] = []
    sources: List[dict] = []
    for raw_dir in dir_paths:
        directory = Path(raw_dir)
        if not directory.is_dir():
            raise FileNotFoundError(f"语料目录不存在: {directory}")
        source_texts: List[str] = []
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in (".txt", ".md"):
                try:
                    text = path.read_text(encoding="utf-8").strip()
                except Exception:
                    continue
                if text:
                    source_texts.append(text)
        if not source_texts:
            raise FileNotFoundError(f"目录下没有可读取的 .txt/.md 文章: {directory}")
        texts.extend(source_texts)
        sources.append({"path": str(directory), "articles": len(source_texts)})
    return texts, sources


async def distill_from_dirs(
    dir_paths: Sequence[str],
    api_key: str,
    api_base: str,
    model: str = "qwen3.8-max-preview",
    out_path: Optional[str] = None,
) -> dict:
    texts, sources = _read_dirs(dir_paths)
    result = await distill_style(texts, api_key, api_base, model)
    result["sources"] = sources
    result["article_count"] = len(texts)
    if out_path:
        Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


async def distill_from_dir(
    dir_path: str,
    api_key: str,
    api_base: str,
    model: str = "qwen3.8-max-preview",
    out_path: Optional[str] = None,
) -> dict:
    """兼容旧调用：单目录入口。"""
    return await distill_from_dirs([dir_path], api_key, api_base, model, out_path)


async def _main():
    import argparse
    import os

    parser = argparse.ArgumentParser(description="公众号文风蒸馏（支持一个或多个语料目录）")
    parser.add_argument("dirs", nargs="+", help="语料目录；可同时传入科普中国、果壳等多个目录")
    parser.add_argument("--out", help="风格画像输出路径 (json)")
    parser.add_argument("--model", default="qwen3.8-max-preview")
    args = parser.parse_args()

    key = os.getenv("BAILIAN_KEY", "")
    base = os.getenv(
        "BAILIAN_BASE",
        "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )
    result = await distill_from_dirs(args.dirs, key, base, args.model, args.out)
    print(json.dumps({
        "sources": result.get("sources", []),
        "article_count": result.get("article_count", 0),
        "chunks": result.get("chunks", 0),
        "profile": result.get("profile", {}),
    }, ensure_ascii=False, indent=2)[:4000])


if __name__ == "__main__":
    asyncio.run(_main())
