from dataclasses import dataclass
from typing import List, Optional, Sequence
import fitz
import numpy as np
from PIL import Image

from .captions import Caption
from .layout import PageLayout
from .page_evidence import PageEvidence
from .qa_metrics import CropMetrics, compute_crop_metrics
from .text_types import TypedLine


@dataclass
class QualityResult:
    is_blank: bool = False
    is_truncated: bool = False
    has_body_text_contamination: bool = False
    body_text_chars: int = 0
    is_duplicate: bool = False
    is_abnormal_size: bool = False
    needs_review: bool = False
    issues: List[str] = None
    metrics: Optional[CropMetrics] = None

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


def _intersection_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty or a.width <= 0 or a.height <= 0:
        return 0.0
    return (inter.width * inter.height) / (a.width * a.height)


def check_body_text_contamination(
    page: fitz.Page,
    bbox: fitz.Rect,
    caption: Optional[Caption] = None,
    evidence: Optional[PageEvidence] = None,
) -> tuple[bool, int]:
    """Detect paragraph-like PDF text swallowed by a visual crop.

    Figure labels, legends and table cells are usually short per line. Body
    prose and captions instead form long multi-line blocks with high character
    density. This uses the PDF text layer, so no OCR is required.
    """
    contaminated_chars = 0
    paragraph_blocks = 0
    page_rect = page.mediabox
    page_area = max(page_rect.width * page_rect.height, 1.0)
    visual_support: List[fitz.Rect] = []
    table_rule_rects: List[fitz.Rect] = []
    text_dict = evidence.text_dict if evidence is not None else page.get_text("dict")
    for block in text_dict["blocks"]:
        if block.get("type") == 1:
            r = fitz.Rect(block["bbox"])
            if r.intersects(bbox):
                visual_support.append(r)
    drawing_rects = (
        evidence.get_drawing_rects(page)
        if evidence is not None
        else [fitz.Rect(drawing["rect"]) for drawing in page.get_drawings()]
    )
    for r in drawing_rects:
        area = max(r.width, 0.0) * max(r.height, 0.0)
        if (
            caption is not None
            and caption.kind == "table"
            and r.intersects(bbox)
            and ((r.width >= 20 and r.height <= 4) or (r.height >= 20 and r.width <= 4))
        ):
            table_rule_rects.append(r)
        if (
            r.intersects(bbox)
            and r.width >= 20
            and r.height >= 8
            and area <= page_area * 0.65
        ):
            visual_support.append(r)

    for block in text_dict["blocks"]:
        if block.get("type") != 0:
            continue
        rect = fitz.Rect(block["bbox"])
        if _intersection_ratio(rect, bbox) < 0.55:
            continue
        if caption is not None and _intersection_ratio(rect, caption.bbox) >= 0.55:
            continue

        lines = block.get("lines", [])
        parts = [
            span.get("text", "")
            for line in lines
            for span in line.get("spans", [])
        ]
        text = " ".join(parts).strip()
        if not text:
            continue
        line_count = max(len(lines), 1)
        chars_per_line = len(text) / line_count

        # Table rows often arrive as one block with many short lines, but real
        # body prose in two-column papers can also average only 40-60 chars per
        # rendered line. Sentence punctuation is therefore a second prose
        # signal instead of requiring an unrealistically high 65 chars/line.
        sentence_marks = sum(text.count(mark) for mark in (".", "!", "?", "。", "！", "？"))
        min_chars_per_line = 65 if caption is not None and caption.kind == "table" else 30
        prose_at_normal_width = (
            caption is not None
            and caption.kind == "table"
            and sentence_marks >= 2
            and chars_per_line >= 30
        )
        paragraph_like = (
            line_count >= 3
            and len(text) >= 110
            and (chars_per_line >= min_chars_per_line or prose_at_normal_width)
        )
        if paragraph_like:
            # Text enclosed by an image or a substantial drawing region is
            # usually part of the figure itself (prompt screenshots, UI cards,
            # diagram callouts). Only unsupported prose counts as page-body
            # contamination.
            if any(_intersection_ratio(rect, support) >= 0.72 for support in visual_support):
                continue
            if caption is not None and caption.kind == "figure":
                # Text-heavy figures often place explanatory labels directly
                # above/below a card or panel. Legitimate labels tend to have
                # roughly the same width as that nearby visual container,
                # unlike swallowed full-column body prose.
                near_matching_panel = False
                for support in visual_support:
                    horizontal_overlap = max(
                        0.0,
                        min(rect.x1, support.x1) - max(rect.x0, support.x0),
                    )
                    min_width = max(min(rect.width, support.width), 1.0)
                    overlap_ratio = horizontal_overlap / min_width
                    width_ratio = rect.width / max(support.width, 1.0)
                    vertical_gap = max(
                        support.y0 - rect.y1,
                        rect.y0 - support.y1,
                        0.0,
                    )
                    if overlap_ratio >= 0.65 and 0.65 <= width_ratio <= 1.15 and vertical_gap <= 26:
                        near_matching_panel = True
                        break
                if near_matching_panel:
                    continue
            if table_rule_rects:
                rule_x0 = min(r.x0 for r in table_rule_rects)
                rule_y0 = min(r.y0 for r in table_rule_rects)
                rule_x1 = max(r.x1 for r in table_rule_rects)
                rule_y1 = max(r.y1 for r in table_rule_rects)
                if (
                    rect.x0 >= rule_x0 - 8
                    and rect.x1 <= rule_x1 + 8
                    and rect.y0 >= rule_y0 - 8
                    and rect.y1 <= rule_y1 + 8
                ):
                    continue
            paragraph_blocks += 1
            contaminated_chars += len(text)

    return paragraph_blocks > 0 and contaminated_chars >= 110, contaminated_chars


def run_quality_checks(
    img: Optional[Image.Image],
    bbox,
    page_rect,
    confidence: float,
    page_width_px: float = 1700,
    page_height_px: float = 2200,
    page: Optional[fitz.Page] = None,
    layout: Optional[PageLayout] = None,
    caption: Optional[Caption] = None,
    typed_lines: Optional[Sequence[TypedLine]] = None,
    evidence: Optional[PageEvidence] = None,
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

    w, h = img.size
    too_small = w < 100 or h < 100
    too_large = w > page_width_px * 0.9 and h > page_height_px * 0.9
    compact_table = (
        caption is not None
        and caption.kind == "table"
        and w >= 300
        and h >= 55
    )
    # Compact tables may legitimately be shorter than the generic 100px
    # minimum, but a crop covering almost the whole page is never compact.
    if too_large or (too_small and not compact_table):
        result.is_abnormal_size = True
        result.needs_review = True
        result.issues.append("abnormal_size")

    if check_truncated(bbox, page_rect):
        result.is_truncated = True
        result.needs_review = True
        result.issues.append("truncated_at_edge")

    if page is not None:
        contaminated, contaminated_chars = check_body_text_contamination(
            page, bbox, caption, evidence,
        )
        if contaminated:
            result.has_body_text_contamination = True
            result.body_text_chars = contaminated_chars
            result.needs_review = True
            result.issues.append(f"body_text_contamination_{contaminated_chars}")

        if typed_lines is not None:
            result.metrics = compute_crop_metrics(
                page,
                bbox,
                typed_lines,
                caption=caption,
                column_boundary=layout.column_boundary if layout is not None else None,
                evidence=evidence,
            )
            # Column mismatch is a structural hard gate. Body metrics remain
            # telemetry until calibrated on a larger labelled crop set; the
            # proven legacy contamination detector above remains authoritative.
            if result.metrics.column_consistency < 0.5:
                result.needs_review = True
                result.issues.append("column_mismatch")

    if confidence < 0.75:
        result.needs_review = True
        result.issues.append(f"low_confidence_{confidence}")

    return result
