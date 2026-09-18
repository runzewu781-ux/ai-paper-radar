from dataclasses import dataclass
from statistics import median
from typing import List, Optional, Sequence, Tuple
import fitz

from .page_evidence import PageEvidence
from .text_types import TypedLine
from .typography import TypographyProfile


@dataclass
class PageLayout:
    kind: str  # "single", "dual", "landscape"
    page_width: float
    page_height: float
    column_boundary: Optional[float] = None
    text_left: float = 0.0
    text_right: float = 0.0
    left_col_left: Optional[float] = None
    left_col_right: Optional[float] = None
    right_col_left: Optional[float] = None
    right_col_right: Optional[float] = None


def _line_rects(
    page: fitz.Page,
    evidence: Optional[PageEvidence] = None,
) -> List[Tuple[fitz.Rect, str]]:
    lines: List[Tuple[fitz.Rect, str]] = []
    text_dict = evidence.text_dict if evidence is not None else page.get_text("dict")
    for block in text_dict["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            rect = fitz.Rect(spans[0]["bbox"])
            for span in spans[1:]:
                rect = rect | fitz.Rect(span["bbox"])
            text = " ".join(s.get("text", "") for s in spans).strip()
            if text:
                lines.append((rect, text))
    return lines


def _quantile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    pos = min(len(vals) - 1, max(0, int(round((len(vals) - 1) * q))))
    return vals[pos]


def detect_layout(
    page: fitz.Page,
    profile: Optional[TypographyProfile] = None,
    typed_lines: Optional[Sequence[TypedLine]] = None,
    evidence: Optional[PageEvidence] = None,
) -> PageLayout:
    rect = page.mediabox
    w, h = rect.width, rect.height

    if w > h:
        return PageLayout(kind="landscape", page_width=w, page_height=h,
                          text_left=0, text_right=w)

    lines = _line_rects(page, evidence)
    if not lines:
        return PageLayout(kind="single", page_width=w, page_height=h,
                          text_left=0, text_right=w)
    original_lines = lines

    typed_body = [
        (line.bbox, line.text)
        for line in (typed_lines or [])
        if line.is_body_like and line.bbox.width >= w * 0.08
    ]
    # Prefer document-profiled body lines when there is enough evidence. This
    # prevents titles, captions and axis labels from voting on page columns.
    if len(typed_body) >= 6:
        lines = typed_body

    # Use line-level geometry instead of declaring the page single-column as
    # soon as one title/caption spans the centre. Academic pages routinely have
    # full-width headings sitting above otherwise two-column content.
    useful = [(r, t) for r, t in lines if len(t) >= 3 and r.width >= w * 0.08]
    x0s = [r.x0 for r, _ in useful] or [r.x0 for r, _ in lines]
    x1s = [r.x1 for r, _ in useful] or [r.x1 for r, _ in lines]
    text_left = _quantile(x0s, 0.05)
    text_right = _quantile(x1s, 0.95)

    mid = w / 2.0
    # Ignore very wide lines when learning columns; they are usually titles,
    # captions, equations or section headings.
    column_lines = [
        (r, t) for r, t in useful
        if r.width <= w * 0.66 and r.y0 > h * 0.03 and r.y1 < h * 0.97
    ]
    left = [(r, t) for r, t in column_lines if (r.x0 + r.x1) / 2.0 < mid and r.x1 < mid + w * 0.06]
    right = [(r, t) for r, t in column_lines if (r.x0 + r.x1) / 2.0 >= mid and r.x0 > mid - w * 0.06]

    # A page can have body text in only one column while a large vector figure
    # occupies the other (Sleeper Agents Figure 1 is a representative case).
    # Therefore counts, edge separation and occupied widths all contribute.
    if len(left) >= 3 and len(right) >= 3:
        left_x0 = _quantile([r.x0 for r, _ in left], 0.10)
        left_x1 = _quantile([r.x1 for r, _ in left], 0.90)
        right_x0 = _quantile([r.x0 for r, _ in right], 0.10)
        right_x1 = _quantile([r.x1 for r, _ in right], 0.90)
        gap = right_x0 - left_x1
        left_width = median([r.width for r, _ in left])
        right_width = median([r.width for r, _ in right])

        strong_gap = gap >= max(6.0, w * 0.012)
        plausible_columns = (
            left_x1 - left_x0 >= w * 0.18
            and right_x1 - right_x0 >= w * 0.12
            and left_width >= w * 0.10
            and right_width >= w * 0.06
        )
        if strong_gap and plausible_columns:
            boundary = (left_x1 + right_x0) / 2.0
            return PageLayout(
                kind="dual", page_width=w, page_height=h,
                column_boundary=boundary,
                text_left=min(left_x0, text_left), text_right=max(right_x1, text_right),
                left_col_left=left_x0, left_col_right=left_x1,
                right_col_left=right_x0, right_col_right=right_x1,
            )

    # Typed BODY evidence is intentionally conservative. If it cannot prove a
    # dual layout, keep the older geometric detector as a fallback rather than
    # allowing a partial classifier to downgrade a genuinely two-column page.
    if typed_body:
        legacy = detect_layout(page, evidence=evidence)
        if legacy.kind == "dual":
            return legacy

    return PageLayout(kind="single", page_width=w, page_height=h,
                      text_left=text_left, text_right=text_right)
