"""公众号文风蒸馏。

输入：一批公众号文章的纯文本（每篇一个 .txt/.md 文件）。
输出：结构化「风格画像」JSON + 一段可直接注入生成提示词的「风格指南」散文。

流程：
1. 批量读取文章文本。
2. 用 LLM 多轮蒸馏：先读原文提炼每篇的写法特征，再汇总成统一风格画像。
3. 输出 profile（JSON 字段）+ style_guide（散文，注入 wechat 提示词用）。
"""
import asyncio
import json
from pathlib import Path
from typing import List, Optional

try:
    from ..agents import setup_client, call_text_llm_api
except ImportError:
    from pragent.backend.agents import setup_client, call_text_llm_api

_DISTILL_SYSTEM = (
    "你是中文写作风格分析师。我给你一批真实公众号长文的正文，你要从中提炼出这些文章共有的写作风格，"
    "用于指导 AI 复刻该风格。看的是 HOW（怎么写），不是 WHAT（写什么内容）。"
    "请输出严格 JSON，字段如下：\n"
    "{\n"
    "  \"structure\": \"文章整体结构怎么组织（开头如何切入、中间如何推进、结尾如何收）\",\n"
    "  \"opening\": \"开头段的典型写法与第一句的气口\",\n"
    "  \"transitions\": \"段落间如何衔接（转场句/意象/留白）\",\n"
    "  \"sentence_rhythm\": \"句式长短、标点、断句、节奏特点\",\n"
    "  \"tone\": \"叙述者姿态、语气、视角（第一二人称？说教还是共情？）\",\n"
    "  \"vocabulary\": \"高频词、口语化程度、术语处理\",\n"
    "  \"avoid\": \"这批文章里从不会出现的写法/词/腔调\",\n"
    "  \"voice\": \"一句话概括这批文章共有的'声音'\"\n"
    "}"
    "只输出 JSON，不要解释。"
)

_STYLE_GUIDE_TEMPLATE = (
    "以下是从一批真实公众号长文中蒸馏出的文风指南，写作时必须严格遵循。\n"
    "# 结构\n{structure}\n"
    "# 开头\n{opening}\n"
    "# 段落衔接\n{transitions}\n"
    "# 句式与节奏\n{sentence_rhythm}\n"
    "# 语气与视角\n{tone}\n"
    "# 用词\n{vocabulary}\n"
    "# 绝对要避免\n{avoid}\n"
    "# 总体声音\n{voice}\n"
)


def _chunk_texts(texts: List[str], max_chars: int = 60000) -> List[str]:
    chunks, cur = [], ""
    for t in texts:
        t = t.strip()
        if not t:
            continue
        if len(cur) + len(t) > max_chars:
            chunks.append(cur)
            cur = t
        else:
            cur += "\n\n" + t
    if cur:
        chunks.append(cur)
    return chunks


async def distill_style(
    article_texts: List[str],
    api_key: str,
    api_base: str,
    model: str = "qwen3.8-max-preview",
) -> dict:
    """返回 {'profile': {...}, 'style_guide': str}。"""
    chunks = _chunk_texts(article_texts)
    if not chunks:
        return {}
    material = "\n\n===== 文章分隔 =====\n\n".join(chunks)

    async with setup_client(api_key, api_base) as client:
        raw = await call_text_llm_api(
            client, _DISTILL_SYSTEM,
            "以下是这批公众号文章的正文，请提炼共有的写作风格：\n\n" + material,
            model,
        )

    profile = {}
    try:
        m = raw[raw.find("{"): raw.rfind("}") + 1]
        profile = json.loads(m)
    except Exception:
        profile = {"raw": raw}

    try:
        guide = _STYLE_GUIDE_TEMPLATE.format(**profile)
    except Exception:
        guide = raw
    return {"profile": profile, "style_guide": guide}


async def distill_from_dir(
    dir_path: str,
    api_key: str,
    api_base: str,
    model: str = "qwen3.8-max-preview",
    out_path: Optional[str] = None,
) -> dict:
    texts = []
    for p in sorted(Path(dir_path).glob("*")):
        if p.suffix.lower() in (".txt", ".md"):
            try:
                texts.append(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    if not texts:
        raise FileNotFoundError("目录下没有 .txt/.md 文章")
    result = await distill_style(texts, api_key, api_base, model)
    if out_path:
        Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


async def _main():
    import argparse, os
    ap = argparse.ArgumentParser(description="公众号文风蒸馏")
    ap.add_argument("dir", help="存放公众号文章 .txt/.md 的目录")
    ap.add_argument("--out", help="风格画像输出路径 (json)")
    ens = ap.parse_args()
    key = os.getenv("BAILIAN_KEY", "")
    base = os.getenv("BAILIAN_BASE", "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    r = await distill_from_dir(ens.dir, key, base, out_path=ens.out)
    print(json.dumps(r.get("profile", {}), ensure_ascii=False, indent=2)[:2000])


if __name__ == "__main__":
    asyncio.run(_main())