from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Iterable, List, Optional, Sequence

import fitz

from .captions import Caption
from .page_evidence import PageEvidence
from .typography import TypographyProfile, normalize_font


class TextType(str, Enum):
    BODY = "body"
    CAPTION = "caption"
    FIGURE_TEXT = "figure_text"
    TABLE_CELL = "table_cell"
    FORMULA = "formula"
    FORMULA_EXPLANATION = "formula_explanation"
    LIST_ITEM = "list_item"
    SECTION_HEADING = "section_heading"
    HEADER_FOOTER = "header_footer"
    FOOTNOTE = "footnote"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TypedLine:
    bbox: fitz.Rect
    text: str
    text_type: TextType
    font: str
    size: float
    bold: bool
    sentence_like: bool
    page_num: int

    @property
    def is_body_like(self) -> bool:
        return self.text_type in {TextType.BODY, TextType.FORMULA_EXPLANATION, TextType.LIST_ITEM}


_LIST_RE = re.compile(r"^(?:[-•·‣▪]|\(?\d+[.)]|\(?[a-zA-Z][.)])\s+")
_FORMULA_RE = re.compile(r"(?:[=<>±≈∑∏√∞∫]|\\(?:alpha|beta|gamma|sum|frac)|\b(?:argmax|argmin)\b)")
_SENTENCE_PUNCT_RE = re.compile(r"[.!?。！？;；,:，：]")
_SECTION_RE = re.compile(r"^(?:\d+(?:\.\d+)*\s+|[A-Z](?:\.\d+)*\s+)[A-Z一-龥]")


def _line_text(line: dict) -> str:
    return " ".join(span.get("text", "") for span in line.get("spans", [])).strip()


def _dominant_span(line: dict) -> tuple[str, float, bool]:
    spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
    if not spans:
        return "unknown", 0.0, False
    span = max(spans, key=lambda s: len(s.get("text", "").strip()))
    font = normalize_font(str(span.get("font", "")))
    size = float(span.get("size", 0.0) or 0.0)
    raw_font = str(span.get("font", "")).lower()
    flags = int(span.get("flags", 0) or 0)
    bold = bool(flags & 16) or any(token in raw_font for token in ("bold", "semibold", "-bd", "_bd"))
    return font, size, bold


def _intersection_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty or a.width <= 0 or a.height <= 0:
        return 0.0
    return (inter.width * inter.height) / (a.width * a.height)


def _visual_support(
    page: fitz.Page,
    evidence: Optional[PageEvidence] = None,
) -> List[fitz.Rect]:
    result: List[fitz.Rect] = []
    page_area = max(page.mediabox.width * page.mediabox.height, 1.0)
    text_dict = evidence.text_dict if evidence is not None else page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") == 1:
            result.append(fitz.Rect(block["bbox"]))
    drawing_rects = (
        evidence.get_drawing_rects(page)
        if evidence is not None
        else [fitz.Rect(drawing["rect"]) for drawing in page.get_drawings()]
    )
    for rect in drawing_rects:
        area = max(rect.width, 0.0) * max(rect.height, 0.0)
        if rect.width >= 8 and rect.height >= 4 and area <= page_area * 0.70:
            result.append(rect)
    return result


def _near_visual(rect: fitz.Rect, visuals: Sequence[fitz.Rect], max_gap: float = 24.0) -> bool:
    halo = fitz.Rect(rect.x0 - max_gap, rect.y0 - max_gap, rect.x1 + max_gap, rect.y1 + max_gap)
    return any(v.intersects(halo) for v in visuals)


def _inside_caption(rect: fitz.Rect, captions: Sequence[Caption]) -> bool:
    return any(_intersection_ratio(rect, cap.bbox) >= 0.55 for cap in captions)


def classify_page_lines(
    page: fitz.Page,
    profile: TypographyProfile,
    captions: Sequence[Caption] = (),
    page_num: Optional[int] = None,
    evidence: Optional[PageEvidence] = None,
) -> List[TypedLine]:
    """Classify PDF text lines before they participate in visual clustering.

    The classifier is deliberately deterministic. It uses document typography
    priors plus local visual adjacency so BODY/FORMULA/LIST lines can become
    blockers instead of accidental Figure evidence.
    """

    visuals = _visual_support(page, evidence)
    width = page.mediabox.width
    height = page.mediabox.height
    result: List[TypedLine] = []
    resolved_page_num = int(page_num if page_num is not None else getattr(page, "number", 0) or 0)

    text_dict = evidence.text_dict if evidence is not None else page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = _line_text(line)
            if not text:
                continue
            rect = fitz.Rect(line["bbox"])
            font, size, bold = _dominant_span(line)
            sentence_like = len(text) >= 24 and bool(_SENTENCE_PUNCT_RE.search(text))
            close_size = abs(size - profile.body_size) <= profile.size_tolerance
            close_font = profile.body_font == "unknown" or font == profile.body_font
            body_style = close_size and (close_font or profile.confidence < 0.18)
            wide = rect.width >= width * 0.25
            near_visual = _near_visual(rect, visuals)

            if _inside_caption(rect, captions):
                text_type = TextType.CAPTION
            elif rect.y1 < height * 0.045 or rect.y0 > height * 0.965:
                text_type = TextType.HEADER_FOOTER
            elif size <= max(7.5, profile.body_size * 0.78) and rect.y0 > height * 0.82:
                text_type = TextType.FOOTNOTE
            elif _LIST_RE.match(text):
                text_type = TextType.LIST_ITEM if body_style else TextType.UNKNOWN
            elif _FORMULA_RE.search(text) and not sentence_like:
                text_type = TextType.FORMULA
            elif (
                body_style
                and sentence_like
                and (text.lower().startswith(("where ", "with ", "here ", "in which ")) or _FORMULA_RE.search(text))
            ):
                text_type = TextType.FORMULA_EXPLANATION
            elif (
                (bold or size >= profile.body_size * 1.18)
                and len(text) <= 110
                and not sentence_like
                and (_SECTION_RE.match(text) or rect.width <= width * 0.65)
            ):
                text_type = TextType.SECTION_HEADING
            elif near_visual and len(text) <= 90 and not sentence_like and rect.width <= width * 0.55:
                text_type = TextType.FIGURE_TEXT
            elif near_visual and len(text) <= 120 and sum(ch.isdigit() for ch in text) >= 2 and not sentence_like:
                text_type = TextType.TABLE_CELL
            elif body_style and (sentence_like or (wide and len(text) >= 35)):
                text_type = TextType.BODY
            else:
                text_type = TextType.UNKNOWN

            result.append(TypedLine(
                bbox=rect,
                text=text,
                text_type=text_type,
                font=font,
                size=size,
                bold=bold,
                sentence_like=sentence_like,
                page_num=resolved_page_num,
            ))

    return result


def body_like_lines(lines: Iterable[TypedLine]) -> List[TypedLine]:
    return [line for line in lines if line.is_body_like]
