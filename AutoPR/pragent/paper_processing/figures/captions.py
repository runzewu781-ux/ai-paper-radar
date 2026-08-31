import re
from dataclasses import dataclass, field
from typing import List, Optional
import fitz

from .typography import TypographyProfile, normalize_font


@dataclass
class Caption:
    kind: str  # "figure" or "table"
    number: int
    label: str  # e.g. "Figure 1", "Table 3"
    text: str  # full caption text
    bbox: fitz.Rect
    page_num: int  # 0-indexed
    sub_labels: List[str] = field(default_factory=list)
    dual_column: bool = False
    column_side: Optional[str] = None  # "left" or "right"


_FIG_RE = re.compile(
    r'^(Figure|Fig\.?)\s+(\d+)\b', re.IGNORECASE
)
_TAB_RE = re.compile(
    r'^(Table)\s+(\d+)\b', re.IGNORECASE
)
_SUB_RE = re.compile(r'\((\w)\)', re.IGNORECASE)


def _line_text(line: dict) -> str:
    return " ".join(
        span.get("text", "")
        for span in line.get("spans", [])
    ).strip()


def _line_bbox(line: dict) -> fitz.Rect:
    return fitz.Rect(line["bbox"])


def _union_rects(rects: List[fitz.Rect]) -> fitz.Rect:
    return fitz.Rect(
        min(r.x0 for r in rects),
        min(r.y0 for r in rects),
        max(r.x1 for r in rects),
        max(r.y1 for r in rects),
    )


def _label_is_emphasized(line: dict) -> bool:
    """Captions commonly emphasize the Figure/Table label."""
    seen = 0
    for span in line.get("spans", []):
        text = span.get("text", "").strip()
        if not text:
            continue
        seen += len(text)
        font = str(span.get("font", "")).lower()
        flags = int(span.get("flags", 0) or 0)
        if (flags & 16) or any(token in font for token in ("bold", "semibold", "-bd", "_bd")):
            return True
        if seen >= 12:
            break
    return False


def _looks_like_caption_line(line: dict, match: re.Match) -> bool:
    """Reject prose references such as ``Figure 11 shows ...``."""
    text = _line_text(line)
    suffix = text[match.end():].lstrip()
    punctuated = suffix.startswith((":", ".", "-", "–", "—"))
    content_after_label = suffix.lstrip(":.-–— ")
    label_only_colon = suffix.startswith(":") and not content_after_label
    return label_only_colon or (punctuated and len(content_after_label) >= 5) or _label_is_emphasized(line)


def _dominant_line_style(line: dict) -> tuple[str, float]:
    spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
    if not spans:
        return "unknown", 0.0
    span = max(spans, key=lambda item: len(item.get("text", "").strip()))
    return normalize_font(str(span.get("font", ""))), float(span.get("size", 0.0) or 0.0)


def _font_family(font: str) -> str:
    # Weight/slant changes are common *inside* a real caption (bold label,
    # regular continuation). Only treat a genuinely different font family as
    # a paragraph-style transition.
    family = font
    for token in ("bolditalic", "semibold", "bold", "italic", "oblique", "medium", "medi", "regular", "regu", "roman"):
        family = family.replace(token, "")
    return family or font


def _caption_text_and_bbox(
    lines: List[dict],
    start: int,
    typography: Optional[TypographyProfile] = None,
) -> tuple[str, fitz.Rect]:
    selected = [lines[start]]
    previous = _line_bbox(lines[start])
    start_text = _line_text(lines[start])
    start_font, start_size = _dominant_line_style(lines[start])
    start_match = _FIG_RE.match(start_text) or _TAB_RE.match(start_text)
    start_suffix = start_text[start_match.end():].lstrip() if start_match is not None else ""
    label_only_colon = start_suffix.startswith(":") and not start_suffix.lstrip(":.-–— ")

    for line in lines[start + 1:start + 7]:
        text = _line_text(line)
        if not text:
            break
        if _FIG_RE.match(text) or _TAB_RE.match(text):
            break
        rect = _line_bbox(line)
        if rect.y0 - previous.y1 > 8.0:
            break

        if typography is not None and not label_only_colon:
            font, size = _dominant_line_style(line)
            body_size = typography.body_size
            body_font = typography.body_font
            resumes_body_style = (
                abs(size - body_size) <= typography.size_tolerance
                and (body_font == "unknown" or font == body_font)
            )
            style_changed = (
                abs(size - start_size) > max(0.7, typography.size_tolerance * 0.75)
                or (
                    start_font != "unknown"
                    and font != "unknown"
                    and _font_family(font) != _font_family(start_font)
                )
            )
            selected_text = " ".join(_line_text(item) for item in selected).rstrip()
            caption_already_complete = selected_text.endswith((".", "!", "?", "。", "！", "？"))
            # A completed caption followed by a genuine typography transition
            # back to the document body is a strong paragraph boundary. If the
            # styles do not change, keep the continuation: many real academic
            # captions are multi-sentence and use body-like typography.
            if resumes_body_style and style_changed and caption_already_complete:
                break

        selected.append(line)
        previous = rect

    text = " ".join(_line_text(line) for line in selected).strip()
    bbox = _union_rects([_line_bbox(line) for line in selected])
    return text, bbox


def find_captions(
    doc: fitz.Document,
    typography: Optional[TypographyProfile] = None,
) -> List[Caption]:
    captions: List[Caption] = []
    seen = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block.get("type") != 0:
                continue
            lines = block.get("lines", [])
            for line_index, line in enumerate(lines):
                line_text = _line_text(line)
                if not line_text:
                    continue

                m_fig = _FIG_RE.match(line_text)
                m_tab = _TAB_RE.match(line_text)
                match = m_fig or m_tab
                if match is None or not _looks_like_caption_line(line, match):
                    continue

                kind = "figure" if m_fig else "table"
                number = int(match.group(2))
                key = (kind, number, page_num)
                if key in seen:
                    continue

                text, bbox = _caption_text_and_bbox(lines, line_index, typography)
                seen.add(key)
                captions.append(Caption(
                    kind=kind,
                    number=number,
                    label=f"{'Figure' if kind == 'figure' else 'Table'} {number}",
                    text=text,
                    bbox=bbox,
                    page_num=page_num,
                    sub_labels=_SUB_RE.findall(text) if kind == "figure" else [],
                ))

    _mark_dual_column(captions, doc)
    return captions


def _mark_dual_column(captions: List[Caption], doc: fitz.Document):
    from collections import defaultdict
    by_page = defaultdict(list)
    for cap in captions:
        by_page[cap.page_num].append(cap)

    for page_num, caps in by_page.items():
        if len(caps) < 2:
            continue
        mid = doc[page_num].mediabox.width / 2.0
        for i in range(len(caps)):
            for j in range(i + 1, len(caps)):
                a, b = caps[i], caps[j]
                x_disjoint = a.bbox.x1 < b.bbox.x0 - 5 or b.bbox.x1 < a.bbox.x0 - 5
                y_close = abs(a.bbox.y0 - b.bbox.y0) < 40
                if x_disjoint and y_close:
                    a.dual_column = True
                    b.dual_column = True
                    for c in (a, b):
                        cx = (c.bbox.x0 + c.bbox.x1) / 2.0
                        c.column_side = "left" if cx < mid else "right"
