import asyncio
import base64
import io
import re
from pathlib import Path
from typing import List, Dict, Optional

from PIL import Image
from tqdm.asyncio import tqdm

from pragent.backend.agents import setup_client
from pragent.backend.loader import ImagePDFLoader

PAGE_PROMPT = """你正在分析一篇学术论文的某一页截图。
任务:判断本页是否包含图表(figure / table / 示意图 / 实验结果图 / 流程图 / 架构图)。
- 若包含:用中文写一段连贯、忠实的描述,涵盖本页每个图表——它展示了什么、想说明的结论、以及图注(caption)文字(若能读到)。描述要具体,便于据此撰写科普推文。
- 若本页没有图表(仅正文段落、公式推导、参考文献、标题页、致谢等):只回复 NO_FIGURE,不要任何其他文字。
只关注图表及其信息,不要复述纯正文。"""


def _to_data_uri(img: Image.Image) -> str:
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")


def _is_no_figure(text: str) -> bool:
    norm = re.sub(r"\s+", "", (text or "").strip().upper())
    return norm == "" or norm == "NO_FIGURE" or norm.startswith("NO_FIGURE")


async def _describe_page(client, model: str, png_path: str, sem: asyncio.Semaphore) -> Optional[str]:
    async with sem:
        try:
            img = Image.open(png_path)
            data_uri = _to_data_uri(img)
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": PAGE_PROMPT},
                ]}],
                max_tokens=1000,
            )
            content = getattr(resp.choices[0].message, "content", None) or ""
            if not content.strip():
                content = getattr(resp.choices[0].message, "reasoning_content", None) or ""
            return content
        except Exception as e:
            tqdm.write(f"[!] vision describe failed for {Path(png_path).name}: {e}")
            return None


async def run_figure_extraction_vision(
    pdf_path: str,
    base_work_dir: str,
    api_key: str,
    api_base: str,
    model: str,
    dpi: int = 144,
    concurrency: int = 3,
    max_pages: Optional[int] = None,
) -> List[Dict]:
    """YOLO-free figure path.

    Renders each page to an image and lets the vision model read the figures
    directly, returning items compatible with
    blog_pipeline.generate_final_post(precomputed_items=...). The full-page
    render is used as a placeholder image; a downstream 'beautify' skill can
    later replace that placeholder using the description.
    """
    pages_dir = Path(base_work_dir) / "vision_pages" / Path(pdf_path).stem
    pages_dir.mkdir(parents=True, exist_ok=True)

    tqdm.write(f"\n--- [vision path] Rendering pages of '{Path(pdf_path).name}' at {dpi} dpi ---")
    loader = ImagePDFLoader(pdf_path, dpi=dpi)
    page_images = loader.load()
    if max_pages and len(page_images) > max_pages:
        tqdm.write(f"[*] vision path: limiting to first {max_pages} of {len(page_images)} pages (max_pages=None for all).")
        page_images = page_images[:max_pages]
    if not page_images:
        tqdm.write("[!] vision path: failed to render any page.")
        return []

    png_paths = []
    for i, img in enumerate(page_images):
        p = pages_dir / f"page_{i+1}.png"
        img.save(p)
        png_paths.append(str(p))
    tqdm.write(f"[*] vision path: rendered {len(png_paths)} pages.")

    sem = asyncio.Semaphore(max(1, concurrency))
    async with setup_client(api_key, api_base) as client:
        if not client:
            tqdm.write("[!] vision path: API client setup failed.")
            return []
        descriptions = await asyncio.gather(
            *[_describe_page(client, model, p, sem) for p in png_paths]
        )

    items: List[Dict] = []
    for png_path, desc in zip(png_paths, descriptions):
        if _is_no_figure(desc):
            continue
        abs_png = str(Path(png_path).resolve())
        items.append({
            "type": "figure",
            "item_path": abs_png,
            "caption_path": abs_png,
            "description": (desc or "").strip(),
        })

    tqdm.write(f"[*] vision path: {len(items)} pages contain figures/tables (of {len(png_paths)} pages).")
    return items
