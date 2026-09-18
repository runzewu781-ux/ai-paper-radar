from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional, Sequence

import fitz

from .captions import Caption
from .page_evidence import PageEvidence
from .text_types import TextType, TypedLine


@dataclass(frozen=True)
class CropMetrics:
    body_char_ratio: float = 0.0
    body_area_ratio: float = 0.0
    body_line_count: int = 0
    max_consec_body_lines: int = 0
    full_width_body_lines: int = 0
    figure_label_char_ratio: float = 0.0
    table_cell_char_ratio: float = 0.0
    visual_support_ratio: float = 0.0
    area_ratio: float = 0.0
    caption_distance: float = 0.0
    x_overlap: float = 0.0
    column_consistency: float = 1.0

    def to_dict(self) -> dict:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, float):
                data[key] = round(value, 4)
        return data


def _intersection_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty or a.width <= 0 or a.height <= 0:
        return 0.0
    return (inter.width * inter.height) / (a.width * a.height)


def _area(rect: fitz.Rect) -> float:
    return max(rect.width, 0.0) * max(rect.height, 0.0)


def _x_overlap(a: fitz.Rect, b: fitz.Rect) -> float:
    overlap = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    return overlap / max(min(a.width, b.width), 1.0)


def _vertical_distance(a: fitz.Rect, b: fitz.Rect) -> float:
    if a.y1 < b.y0:
        return b.y0 - a.y1
    if b.y1 < a.y0:
        return a.y0 - b.y1
    return 0.0


def _visual_support_rects(
    page: fitz.Page,
    bbox: fitz.Rect,
    evidence: Optional[PageEvidence] = None,
) -> list[fitz.Rect]:
    result: list[fitz.Rect] = []
    page_area = max(_area(page.mediabox), 1.0)
    text_dict = evidence.text_dict if evidence is not None else page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") == 1:
            rect = fitz.Rect(block["bbox"])
            if rect.intersects(bbox):
                result.append(rect)
    drawing_rects = (
        evidence.get_drawing_rects(page)
        if evidence is not None
        else [fitz.Rect(drawing["rect"]) for drawing in page.get_drawings()]
    )
    for rect in drawing_rects:
        area = _area(rect)
        if (
            rect.intersects(bbox)
            and rect.width >= 8
            and rect.height >= 4
            and area <= page_area * 0.70
        ):
            result.append(rect)
    return result


def compute_crop_metrics(
    page: fitz.Page,
    bbox: fitz.Rect,
    typed_lines: Sequence[TypedLine],
    caption: Optional[Caption] = None,
    column_boundary: Optional[float] = None,
    evidence: Optional[PageEvidence] = None,
) -> CropMetrics:
    crop_area = max(_area(bbox), 1.0)
    page_area = max(_area(page.mediabox), 1.0)

    lines = [line for line in typed_lines if _intersection_ratio(line.bbox, bbox) >= 0.55]
    if caption is not None:
        lines = [line for line in lines if _intersection_ratio(line.bbox, caption.bbox) < 0.55]

    total_chars = sum(len(line.text) for line in lines)
    body_lines = [line for line in lines if line.is_body_like]
    figure_lines = [line for line in lines if line.text_type == TextType.FIGURE_TEXT]
    table_lines = [line for line in lines if line.text_type == TextType.TABLE_CELL]

    body_chars = sum(len(line.text) for line in body_lines)
    body_area = sum(_area(line.bbox & bbox) for line in body_lines)
    figure_chars = sum(len(line.text) for line in figure_lines)
    table_chars = sum(len(line.text) for line in table_lines)

    sorted_body = sorted(body_lines, key=lambda line: (line.bbox.y0, line.bbox.x0))
    max_consecutive = 0
    current = 0
    previous: Optional[TypedLine] = None
    for line in sorted_body:
        if previous is None:
            current = 1
        else:
            vertical_gap = line.bbox.y0 - previous.bbox.y1
            same_band = abs(line.bbox.x0 - previous.bbox.x0) <= max(18.0, bbox.width * 0.08)
            if -2.0 <= vertical_gap <= max(12.0, line.size * 1.8) and same_band:
                current += 1
            else:
                current = 1
        max_consecutive = max(max_consecutive, current)
        previous = line

    full_width_body = sum(1 for line in body_lines if line.bbox.width >= bbox.width * 0.62)

    support_rects = _visual_support_rects(page, bbox, evidence)
    support_area = sum(_area(rect & bbox) for rect in support_rects)
    visual_support_ratio = min(1.0, support_area / crop_area)

    if caption is not None:
        caption_distance = _vertical_distance(caption.bbox, bbox)
        x_overlap = _x_overlap(caption.bbox, bbox)
    else:
        caption_distance = 0.0
        x_overlap = 0.0

    column_consistency = 1.0
    if column_boundary is not None and caption is not None:
        caption_crosses = caption.bbox.x0 < column_boundary < caption.bbox.x1
        cap_mid = (caption.bbox.x0 + caption.bbox.x1) / 2.0
        bbox_mid = (bbox.x0 + bbox.x1) / 2.0
        crosses = bbox.x0 < column_boundary < bbox.x1
        if not caption_crosses and not crosses and (cap_mid < column_boundary) != (bbox_mid < column_boundary):
            column_consistency = 0.0

    return CropMetrics(
        body_char_ratio=body_chars / max(total_chars, 1),
        body_area_ratio=min(1.0, body_area / crop_area),
        body_line_count=len(body_lines),
        max_consec_body_lines=max_consecutive,
        full_width_body_lines=full_width_body,
        figure_label_char_ratio=figure_chars / max(total_chars, 1),
        table_cell_char_ratio=table_chars / max(total_chars, 1),
        visual_support_ratio=visual_support_ratio,
        area_ratio=crop_area / page_area,
        caption_distance=caption_distance,
        x_overlap=x_overlap,
        column_consistency=column_consistency,
    )
