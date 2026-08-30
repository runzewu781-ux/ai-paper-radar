"""Deterministic Chinese SVG renderer for scientific flow / architecture diagrams.

The vision model extracts structure only.  This module does not invent nodes or
relationships; it turns the extracted stage list and flow summary into a compact,
readable Chinese diagram suitable for AutoPR's article view.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Iterable


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _wrap(text: str, width: int = 13, max_lines: int = 3) -> list[str]:
    """Rough CJK-friendly wrapping without external font/layout dependencies."""
    text = _clean(text)
    if not text:
        return []
    lines: list[str] = []
    current = ""
    weight = 0
    for ch in text:
        w = 1 if ord(ch) > 127 else 0.55
        if current and weight + w > width:
            lines.append(current)
            current = ch
            weight = w
            if len(lines) >= max_lines - 1:
                break
        else:
            current += ch
            weight += w
    consumed = "".join(lines) + current
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(consumed) < len(text) and lines:
        lines[-1] = lines[-1].rstrip("…") + "…"
    return lines[:max_lines]


def _text_lines(lines: Iterable[str], x: float, y: float, *, size: int = 19,
                weight: int = 600, gap: int = 28, anchor: str = "middle") -> str:
    parts = []
    for i, line in enumerate(lines):
        parts.append(
            f'<text x="{x}" y="{y + i * gap}" text-anchor="{anchor}" '
            f'font-size="{size}" font-weight="{weight}">{html.escape(line)}</text>'
        )
    return "\n".join(parts)


def render_structure_svg(structure: dict[str, Any], out_path: str | Path,
                         *, title: str = "", number: int | None = None) -> str | None:
    stages = [_clean(x) for x in (structure or {}).get("stages", []) if _clean(x)]
    if len(stages) < 2:
        return None
    stages = stages[:6]
    role = _clean((structure or {}).get("role")) or "流程"
    flow = _clean((structure or {}).get("flow"))
    keep = [_clean(x) for x in (structure or {}).get("keep", []) if _clean(x)][:5]

    width = 1080
    margin = 66
    title_y = 58
    card_top = 112
    card_h = 150
    gap = 34
    usable = width - margin * 2
    card_w = (usable - gap * (len(stages) - 1)) / len(stages)
    if card_w < 135:
        card_w = 135
        gap = max(18, (usable - card_w * len(stages)) / max(1, len(stages) - 1))

    footer_top = card_top + card_h + 72
    footer_h = 118 if flow else 62
    term_h = 76 if keep else 0
    height = footer_top + footer_h + term_h + 34

    label = _clean(title) or (f"Figure {number} · 中文结构重绘" if number else "中文结构重绘")
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" rx="22" fill="#F7F6F2"/>',
        '<text x="66" y="58" font-size="28" font-weight="700" fill="#222">'
        + html.escape(label) + '</text>',
        f'<text x="{width - 66}" y="58" text-anchor="end" font-size="17" fill="#6F6A61">'
        + html.escape(role) + '</text>',
    ]

    centers: list[float] = []
    for i, stage in enumerate(stages):
        x = margin + i * (card_w + gap)
        cx = x + card_w / 2
        centers.append(cx)
        svg.append(
            f'<rect x="{x:.1f}" y="{card_top}" width="{card_w:.1f}" height="{card_h}" '
            'rx="18" fill="#FFFFFF" stroke="#D8D4CB" stroke-width="2"/>'
        )
        svg.append(
            f'<circle cx="{x + 28:.1f}" cy="{card_top + 27}" r="15" fill="#2D2B28"/>'
        )
        svg.append(
            f'<text x="{x + 28:.1f}" y="{card_top + 33}" text-anchor="middle" '
            f'font-size="15" font-weight="700" fill="#FFFFFF">{i + 1}</text>'
        )
        lines = _wrap(stage, width=max(8, int(card_w / 12.5)), max_lines=3)
        start_y = card_top + 72 - max(0, len(lines) - 1) * 10
        svg.append(_text_lines(lines, cx, start_y, size=19, weight=650, gap=28))
        if i < len(stages) - 1:
            x1 = x + card_w + 8
            x2 = x + card_w + gap - 8
            cy = card_top + card_h / 2
            svg.append(
                f'<line x1="{x1:.1f}" y1="{cy:.1f}" x2="{x2:.1f}" y2="{cy:.1f}" '
                'stroke="#80786C" stroke-width="3" stroke-linecap="round"/>'
            )
            svg.append(
                f'<path d="M {x2 - 10:.1f} {cy - 7:.1f} L {x2:.1f} {cy:.1f} '
                f'L {x2 - 10:.1f} {cy + 7:.1f}" fill="none" stroke="#80786C" '
                'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
            )

    if flow:
        svg.append(
            f'<rect x="{margin}" y="{footer_top}" width="{usable}" height="96" rx="16" '
            'fill="#EEEAE2"/>'
        )
        svg.append(
            f'<text x="{margin + 24}" y="{footer_top + 30}" font-size="16" font-weight="700" '
            'fill="#5E584F">信息如何流动</text>'
        )
        flow_lines = _wrap(flow, width=47, max_lines=2)
        svg.append(_text_lines(flow_lines, margin + 24, footer_top + 60,
                               size=17, weight=450, gap=25, anchor="start"))

    if keep:
        term_y = footer_top + (112 if flow else 10)
        terms = "  ·  ".join(keep)
        svg.append(
            f'<text x="{margin}" y="{term_y + 28}" font-size="15" font-weight="700" '
            'fill="#6F6A61">关键术语</text>'
        )
        svg.append(
            f'<text x="{margin + 86}" y="{term_y + 28}" font-size="15" fill="#4B4741">'
            + html.escape(terms) + '</text>'
        )

    svg.append('</svg>')
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(svg), encoding="utf-8")
    return str(out)
