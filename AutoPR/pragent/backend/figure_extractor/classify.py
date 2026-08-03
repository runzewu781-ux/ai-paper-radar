from typing import Optional
from PIL import Image
import base64
import io
import json
import os

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

_CLASSIFY_PROMPT = (
    "判断这张学术论文图片的类型，只回答一个字母：\n"
    "A = 含数据的图表（折线图、柱状图、散点图、热力图、数据表格、实验结果图）\n"
    "B = 不含数据的示意图（架构图、流程图、pipeline、概念图）\n"
    "C = 其他（照片、截图、公式等）\n"
    "只回答 A、B 或 C。"
)

_TYPE_MAP = {"A": "data_chart", "B": "flow_diagram", "C": "other"}


def _img_to_data_uri(img: Image.Image, max_side: int = 1024) -> str:
    w, h = img.size
    if max(w, h) > max_side:
        ratio = max_side / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


async def classify_image(
    img: Image.Image,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    model: str = "qwen3.8-max-preview",
) -> str:
    if AsyncOpenAI is None:
        return "other"

    api_key = api_key or os.getenv("OPENAI_API_KEY", "")
    api_base = api_base or os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

    if not api_key:
        return "other"

    client = AsyncOpenAI(api_key=api_key, base_url=api_base)
    data_uri = _img_to_data_uri(img)

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": _CLASSIFY_PROMPT},
                ],
            }],
            max_tokens=10,
            temperature=0,
        )
        answer = resp.choices[0].message.content.strip().upper()
        for ch in answer:
            if ch in _TYPE_MAP:
                return _TYPE_MAP[ch]
        return "other"
    except Exception:
        return "other"
