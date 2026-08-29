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
        "\"ordered\": bool(原图标签顺序是否具有时间、阶段或其他语义)}, "
        "\"explanation_zh\": str(用一句话向科普读者解释这张图讲了什么、数据含义)}。"
        "relation 描述原图中的真实关系，不是你希望使用的图型。"
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


async def describe_structure(img, api_key, api_base, model) -> Optional[dict]:
    system = (
        "你是科研插图结构分析师。读懂这张非数据流程/框架图，拆解其结构。"
        "返回严格 JSON：{\"role\": str(总览/流程/框架/系统/任务), "
        "\"stages\": [str, ...](阶段或模块名), \"flow\": str(信息如何流动), "
        "\"keep\": [str, ...](必须保留的术语), \"drop\": [str, ...](可丢弃的装饰), "
        "\"explanation_zh\": str(用中文向科普读者解释这张图的机制/流程，避免只描述图形本身)}。"
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
