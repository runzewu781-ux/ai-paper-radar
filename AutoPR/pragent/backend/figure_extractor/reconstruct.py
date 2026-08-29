import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from .classify import classify_image, _img_to_data_uri

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

_REF_RE = re.compile(
    r'(?:Figure|Fig\.?|Table)\s*[:：]?\s*(\d+)', re.IGNORECASE
)


def find_referenced_numbers(post_text: str) -> Dict[str, set]:
    figs = set()
    tabs = set()
    for m in re.finditer(r'(Figure|Fig\.?|Table)\s*[:：]?\s*(\d+)', post_text, re.IGNORECASE):
        kind = "table" if m.group(1).lower() == "table" else "figure"
        num = int(m.group(2))
        if kind == "table":
            tabs.add(num)
        else:
            figs.add(num)
    return {"figure": figs, "table": tabs}


def load_manifest(manifest_path: str) -> Dict[str, Any]:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def plan_reconstruction(manifest: Dict[str, Any], post_text: str) -> List[Dict[str, Any]]:
    refs = find_referenced_numbers(post_text)
    plan = []
    for item in manifest.get("items", []):
        kind = item["kind"]
        number = int(item["number"])
        if number not in refs.get(kind, set()):
            continue
        visual_type = item.get("visual_type", kind)
        if kind == "table" or visual_type == "data_chart":
            skill = "lieflat-charts"
        else:
            skill = "science-structure-illustrations"
        plan.append({
            "number": number,
            "kind": kind,
            "file": item["file"],
            "caption": item["caption"],
            "visual_type": visual_type,
            "skill": skill,
        })
    return plan


async def _vision_json(img, system: str, user: str, api_key, api_base, model) -> Optional[dict]:
    if AsyncOpenAI is None:
        return None
    client = AsyncOpenAI(api_key=api_key, base_url=api_base)
    data_uri = _img_to_data_uri(img)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": system + "\n" + user},
                ],
            }],
            temperature=0,
        )
        raw = resp.choices[0].message.content
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        return None
    return None


async def extract_chart_data(img, api_key, api_base, model) -> Optional[dict]:
    system = (
        "你是科研图表数据提取器，只负责读懂原图的数据和语义，不负责选择可视化模板。"
        "忠实读取图中可确认的真实数值；不得为了画图修改、补造、插值、排序或重排数据。"
        "所有输出必须用中文，并返回严格 JSON："
        "{\"title_zh\": str(中文结论式标题), "
        "\"data_zh\": [[中文标签, 数字], ...]，"
        "若原图明确是同一类目的前后/两条件对比，则为 [[中文标签, 前值, 后值], ...]，"
        "\"semantics\": {"
        "\"relation\": str，取值仅限 comparison/ranking/time_series/part_to_whole/"
        "before_after/ordered_stages/funnel/independent_percentages，"
        "\"value_kind\": str，取值仅限 count/percent/score/measurement/unknown，"
        "\"unit\": str(图中单位，没有则空字符串), "
        "\"ordered\": bool(原图标签顺序是否具有时间、阶段或其他语义), "
        "\"series_labels\": [str, str](只有每行明确包含两个条件/系列数值时填写，按数值列顺序), "
        "\"complex_table\": bool(若原图是稠密科研表格，超过8行、超过2个数值指标列，或含不能安全丢弃的文本列则为true)}, "
        "\"complex_figure\": bool(若原图含多个相互独立的子图/坐标轴，而data_zh只覆盖其中一部分核心信息则为true；"
        "若图中存在完整汇总表，data_zh已忠实覆盖该汇总表所表达的主要比较，则可为false)}, "
        "\"explanation_zh\": str(用一句中性中文解释这张图讲了什么、数据含义；只陈述图中可确认的信息，"
        "禁用爆款、炸裂、碾压、颠覆、一键、震撼等营销/情绪词，不替读者下判断)}。"
        "relation 描述原图中的真实关系，不是你希望使用的图型。"
        "对于同一类别下两个条件/模型的并列数值，可以保持 relation=comparison，data_zh 使用三列并填写 series_labels。"
        "复杂表格不要为了套图型只摘取一个指标；complex_table=true 时可保留可确认的 data_zh，但后续系统会优先保留原表。"
        "多面板复合图不要只抽一个面板就假装重构整图；如果抽取数据不足以等价表达整张图，必须 complex_figure=true。"
        "data_zh 至少 2 项；无法可靠读取具体数字时不要猜测，返回空 data_zh。"
    )
    return await _vision_json(
        img,
        system,
        "提取数据、单位和数据关系并翻译成中文，只返回 JSON；不要输出任何图型 ID。",
        api_key,
        api_base,
        model,
    )


async def assess_chart_replacement(
    img,
    extracted: Optional[dict],
    api_key,
    api_base,
    model,
    caption: str = "",
) -> Optional[dict]:
    """Decide whether one reconstructed chart can faithfully replace the whole source image."""
    if not extracted:
        return {"safe_to_replace": False, "reason": "no extracted data"}
    system = (
        "你是科研图表重构的完整性审计器。判断给定结构化数据是否足以替代整张原图，而不会丢失主要、独立的信息。"
        "严格保守：多面板图若包含多个独立坐标轴/不同指标/不同关系，而抽取数据只覆盖其中一部分，必须 false。"
        "若原图虽有多个面板，但存在一个清晰的汇总表，抽取数据完整覆盖该汇总表且足以表达题注强调的核心比较，可以 true。"
        "稠密科研表、流程框架、抽取不完整或无法确认时一律 false。"
        "只返回严格JSON：{\"safe_to_replace\": bool, \"reason\": str}。"
    )
    user = (
        "题注：" + (caption or "(无)")
        + "\n结构化抽取：" + json.dumps(extracted, ensure_ascii=False)
        + "\n判断这份数据能否作为整张原图的等价替代。"
    )
    return await _vision_json(img, system, user, api_key, api_base, model)


async def describe_structure(img, api_key, api_base, model) -> Optional[dict]:
    system = (
        "你是科研插图结构分析师。读懂这张非数据流程/框架图，拆解其结构。"
        "只根据图中可确认的信息描述机制，不补传播效果、产品价值或营销判断。"
        "中文解释保持中性、具体，禁用爆款、炸裂、碾压、颠覆、一键、震撼、高吸引力等营销/情绪词。"
        "返回严格 JSON：{\"role\": str(总览/流程/框架/系统/任务), "
        "\"stages\": [str, ...](阶段或模块名), \"flow\": str(信息如何流动), "
        "\"keep\": [str, ...](必须保留的术语), \"drop\": [str, ...](可丢弃的装饰), "
        "\"explanation_zh\": str(用中性中文向科普读者解释这张图的机制/流程，避免只描述图形本身，"
        "不得夸大原图没有表达的能力或效果)}。"
    )
    return await _vision_json(img, system, "分析结构并给出中文解释，只返回 JSON。", api_key, api_base, model)


async def prepare_skill_inputs(
    plan: List[Dict[str, Any]],
    base_dir: str,
    api_key: str,
    api_base: str,
    model: str = "qwen3.8-max-preview",
) -> List[Dict[str, Any]]:
    from PIL import Image
    base = Path(base_dir)
    results = []
    for entry in plan:
        img_path = base / entry["file"]
        if not img_path.exists():
            continue
        img = Image.open(str(img_path))
        if entry["skill"] == "lieflat-charts":
            payload = await extract_chart_data(img, api_key, api_base, model)
            entry["lieflat_config"] = payload
        else:
            payload = await describe_structure(img, api_key, api_base, model)
            entry["structure"] = payload
        results.append(entry)
    return results
