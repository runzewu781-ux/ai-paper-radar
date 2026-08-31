from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Optional
import re

import fitz


_CAPTION_PREFIX_RE = re.compile(r"^(?:figure|fig\.?|table)\s+\d+\b", re.IGNORECASE)


@dataclass(frozen=True)
class TypographyProfile:
    """Document-level typography prior learned from the PDF text layer."""

    body_font: str
    body_size: float
    body_line_gap: float
    body_line_height: float
    caption_size: Optional[float]
    body_char_count: int
    confidence: float

    @property
    def size_tolerance(self) -> float:
        return max(0.7, self.body_size * 0.10)


def normalize_font(font: str) -> str:
    value = (font or "").strip().lower()
    if "+" in value and len(value.split("+", 1)[0]) <= 8:
        value = value.split("+", 1)[1]
    value = re.sub(r"[^a-z0-9]+", "", value)
    for token in ("regular", "roman", "book", "medium", "normal"):
        value = value.replace(token, "")
    return value or "unknown"


def _round_half(value: float) -> float:
    return round(float(value) * 2.0) / 2.0


def _iter_candidate_lines(doc: fitz.Document) -> Iterable[tuple[fitz.Page, dict, str, int]]:
    for page in doc:
        height = page.mediabox.height
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                text = " ".join(s.get("text", "") for s in spans).strip()
                if not text:
                    continue
                rect = fitz.Rect(line["bbox"])
                if rect.y1 < height * 0.045 or rect.y0 > height * 0.96:
                    continue
                if _CAPTION_PREFIX_RE.match(text):
                    continue
                yield page, line, text, len(text)


def estimate_document_typography(doc: fitz.Document) -> TypographyProfile:
    """Estimate dominant body typography using character-weighted evidence.

    Character weighting prevents short axis labels, headers and section numbers
    from overpowering the much longer body paragraphs.
    """

    size_hist: Counter[float] = Counter()
    font_hist: Counter[str] = Counter()
    joint_hist: Counter[tuple[str, float]] = Counter()
    caption_size_hist: Counter[float] = Counter()
    line_heights: list[float] = []
    line_gaps: list[float] = []
    total_chars = 0

    for page in doc:
        height = page.mediabox.height
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            lines = block.get("lines", [])
            previous_rect: Optional[fitz.Rect] = None
            previous_size: Optional[float] = None
            for line in lines:
                spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                text = " ".join(s.get("text", "") for s in spans).strip()
                rect = fitz.Rect(line["bbox"])
                if not text or rect.y1 < height * 0.045 or rect.y0 > height * 0.96:
                    continue

                weighted = sorted(
                    (
                        (len(s.get("text", "").strip()), normalize_font(str(s.get("font", ""))), _round_half(float(s.get("size", 0.0))))
                        for s in spans
                        if s.get("text", "").strip()
                    ),
                    reverse=True,
                )
                if not weighted:
                    continue
                _, line_font, line_size = weighted[0]
                chars = len(text)

                if _CAPTION_PREFIX_RE.match(text):
                    caption_size_hist[line_size] += chars
                else:
                    size_hist[line_size] += chars
                    font_hist[line_font] += chars
                    joint_hist[(line_font, line_size)] += chars
                    total_chars += chars
                    line_heights.append(rect.height)

                    if previous_rect is not None and previous_size is not None:
                        gap = rect.y0 - previous_rect.y1
                        if 0 <= gap <= max(12.0, line_size * 1.8) and abs(previous_size - line_size) <= 0.75:
                            line_gaps.append(gap)
                previous_rect = rect
                previous_size = line_size

    if not joint_hist:
        return TypographyProfile(
            body_font="unknown",
            body_size=10.0,
            body_line_gap=2.0,
            body_line_height=11.0,
            caption_size=None,
            body_char_count=0,
            confidence=0.0,
        )

    (body_font, body_size), dominant_chars = joint_hist.most_common(1)[0]
    caption_size = caption_size_hist.most_common(1)[0][0] if caption_size_hist else None
    confidence = dominant_chars / max(total_chars, 1)

    compatible_heights = [h for h in line_heights if 0.55 * body_size <= h <= 1.8 * body_size]
    body_line_height = median(compatible_heights) if compatible_heights else body_size * 1.15
    body_line_gap = median(line_gaps) if line_gaps else max(1.0, body_size * 0.20)

    return TypographyProfile(
        body_font=body_font,
        body_size=body_size,
        body_line_gap=float(body_line_gap),
        body_line_height=float(body_line_height),
        caption_size=caption_size,
        body_char_count=dominant_chars,
        confidence=float(confidence),
    )
