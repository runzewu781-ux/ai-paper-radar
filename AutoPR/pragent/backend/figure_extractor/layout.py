from dataclasses import dataclass
from typing import Optional
import fitz


@dataclass
class PageLayout:
    kind: str  # "single", "dual", "landscape"
    page_width: float
    page_height: float
    column_boundary: Optional[float] = None
    text_left: float = 0.0
    text_right: float = 0.0


def detect_layout(page: fitz.Page) -> PageLayout:
    rect = page.mediabox
    w, h = rect.width, rect.height

    if w > h:
        return PageLayout(kind="landscape", page_width=w, page_height=h,
                          text_left=0, text_right=w)

    blocks = page.get_text("dict")["blocks"]
    x0_list = []
    x1_list = []
    for b in blocks:
        if b.get("type") != 0:
            continue
        x0_list.append(b["bbox"][0])
        x1_list.append(b["bbox"][2])

    if not x0_list:
        return PageLayout(kind="single", page_width=w, page_height=h,
                          text_left=0, text_right=w)

    text_left = min(x0_list)
    text_right = max(x1_list)

    mid = w / 2.0
    gap_threshold = 20.0
    has_gap = True
    for b in blocks:
        if b.get("type") != 0:
            continue
        bx0, bx1 = b["bbox"][0], b["bbox"][2]
        if bx0 < mid - gap_threshold and bx1 > mid + gap_threshold:
            has_gap = False
            break

    if has_gap and text_right - text_left > w * 0.6:
        left_max_x1 = max(
            (b["bbox"][2] for b in blocks
             if b.get("type") == 0 and b["bbox"][2] < mid + gap_threshold),
            default=mid
        )
        right_min_x0 = min(
            (b["bbox"][0] for b in blocks
             if b.get("type") == 0 and b["bbox"][0] > mid - gap_threshold),
            default=mid
        )
        boundary = (left_max_x1 + right_min_x0) / 2.0
        return PageLayout(kind="dual", page_width=w, page_height=h,
                          column_boundary=boundary,
                          text_left=text_left, text_right=text_right)

    return PageLayout(kind="single", page_width=w, page_height=h,
                      text_left=text_left, text_right=text_right)
