from dataclasses import dataclass
from typing import List, Optional
import numpy as np
from PIL import Image


@dataclass
class QualityResult:
    is_blank: bool = False
    is_truncated: bool = False
    has_body_text_contamination: bool = False
    is_duplicate: bool = False
    is_abnormal_size: bool = False
    needs_review: bool = False
    issues: List[str] = None

    def __post_init__(self):
        if self.issues is None:
            self.issues = []


def check_blank(img: Image.Image, threshold: int = 250, min_ratio: float = 0.01) -> bool:
    arr = np.array(img.convert("L"))
    non_white = np.sum(arr < threshold)
    total = arr.size
    return (non_white / total) < min_ratio


def check_abnormal_size(img: Image.Image, page_width_px: float, page_height_px: float) -> bool:
    w, h = img.size
    if w < 100 or h < 100:
        return True
    if w > page_width_px * 0.9 and h > page_height_px * 0.9:
        return True
    return False


def check_truncated(bbox, page_rect, tolerance: float = 3.0) -> bool:
    touches_edge = (
        abs(bbox.x0 - page_rect.x0) < tolerance or
        abs(bbox.y0 - page_rect.y0) < tolerance or
        abs(bbox.x1 - page_rect.x1) < tolerance or
        abs(bbox.y1 - page_rect.y1) < tolerance
    )
    return touches_edge


def run_quality_checks(
    img: Optional[Image.Image],
    bbox,
    page_rect,
    confidence: float,
    page_width_px: float = 1700,
    page_height_px: float = 2200,
) -> QualityResult:
    result = QualityResult()

    if img is None:
        result.is_blank = True
        result.needs_review = True
        result.issues.append("render_failed")
        return result

    if check_blank(img):
        result.is_blank = True
        result.needs_review = True
        result.issues.append("blank_image")

    if check_abnormal_size(img, page_width_px, page_height_px):
        result.is_abnormal_size = True
        result.needs_review = True
        result.issues.append("abnormal_size")

    if check_truncated(bbox, page_rect):
        result.is_truncated = True
        result.issues.append("truncated_at_edge")

    if confidence < 0.7:
        result.needs_review = True
        result.issues.append(f"low_confidence_{confidence}")

    return result
