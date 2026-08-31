from typing import Optional
import fitz
import numpy as np
from PIL import Image
import io


def render_crop(
    page: fitz.Page,
    bbox: fitz.Rect,
    dpi: int = 200,
    padding: float = 5.0,
) -> Optional[Image.Image]:
    page_rect = page.mediabox
    clip = fitz.Rect(
        max(page_rect.x0, bbox.x0 - padding),
        max(page_rect.y0, bbox.y0 - padding),
        min(page_rect.x1, bbox.x1 + padding),
        min(page_rect.y1, bbox.y1 + padding),
    )

    if clip.width < 5 or clip.height < 5:
        return None

    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)

    try:
        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return img
    except Exception:
        return None


def trim_whitespace(img: Image.Image, threshold: int = 250, safe_margin: int = 10) -> Image.Image:
    arr = np.array(img.convert("L"))
    non_white = np.where(arr < threshold)

    if len(non_white[0]) == 0:
        return img

    y_min, y_max = non_white[0].min(), non_white[0].max()
    x_min, x_max = non_white[1].min(), non_white[1].max()

    h, w = arr.shape
    crop_area = (y_max - y_min) * (x_max - x_min)
    total_area = h * w

    if crop_area < total_area * 0.05:
        return img

    y_min = max(0, y_min - safe_margin)
    y_max = min(h, y_max + safe_margin)
    x_min = max(0, x_min - safe_margin)
    x_max = min(w, x_max + safe_margin)

    return img.crop((x_min, y_min, x_max, y_max))


def render_and_trim(
    page: fitz.Page,
    bbox: fitz.Rect,
    dpi: int = 200,
    padding: float = 5.0,
) -> Optional[Image.Image]:
    img = render_crop(page, bbox, dpi=dpi, padding=padding)
    if img is None:
        return None
    return trim_whitespace(img)
