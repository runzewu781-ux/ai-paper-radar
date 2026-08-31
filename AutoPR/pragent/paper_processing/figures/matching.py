from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import fitz
from scipy.optimize import linear_sum_assignment

from .captions import Caption
from .layout import PageLayout


@dataclass(frozen=True)
class RegionProposal:
    caption: Caption
    bbox: fitz.Rect
    confidence: float

    @property
    def key(self) -> tuple[str, int, int]:
        return (self.caption.kind, self.caption.number, self.caption.page_num)


def _iou(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    inter_area = inter.width * inter.height
    union_area = a.width * a.height + b.width * b.height - inter_area
    return inter_area / max(union_area, 1.0)


def _x_overlap(a: fitz.Rect, b: fitz.Rect) -> float:
    overlap = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    return overlap / max(min(a.width, b.width), 1.0)


def _vertical_distance(a: fitz.Rect, b: fitz.Rect) -> float:
    if a.y1 < b.y0:
        return b.y0 - a.y1
    if b.y1 < a.y0:
        return a.y0 - b.y1
    return 0.0


def _same_column(caption: Caption, region: fitz.Rect, layout: PageLayout) -> float:
    if layout.kind != "dual" or layout.column_boundary is None:
        return 1.0
    cap_mid = (caption.bbox.x0 + caption.bbox.x1) / 2.0
    reg_mid = (region.x0 + region.x1) / 2.0
    cap_side = cap_mid < layout.column_boundary
    reg_side = reg_mid < layout.column_boundary
    crosses = region.x0 < layout.column_boundary < region.x1
    return 1.0 if cap_side == reg_side or crosses else 0.0


def _intervening_caption_penalty(
    caption: Caption,
    region: fitz.Rect,
    captions: Sequence[Caption],
) -> float:
    if region.y1 <= caption.bbox.y0:
        low, high = region.y1, caption.bbox.y0
    elif region.y0 >= caption.bbox.y1:
        low, high = caption.bbox.y1, region.y0
    else:
        return 0.0
    for other in captions:
        if other is caption or other.kind != caption.kind:
            continue
        cy = (other.bbox.y0 + other.bbox.y1) / 2.0
        if low < cy < high and _x_overlap(other.bbox, region) >= 0.25:
            return 1.0
    return 0.0


def _score(
    caption: Caption,
    candidate: RegionProposal,
    layout: PageLayout,
    captions: Sequence[Caption],
) -> float:
    if candidate.caption.kind != caption.kind:
        return -1000.0

    page_h = max(layout.page_height, 1.0)
    distance = _vertical_distance(caption.bbox, candidate.bbox)
    proximity = max(0.0, 1.0 - distance / (page_h * 0.28))
    overlap = _x_overlap(caption.bbox, candidate.bbox)
    same_col = _same_column(caption, candidate.bbox, layout)
    intervening = _intervening_caption_penalty(caption, candidate.bbox, captions)
    owner_bonus = 0.75 if candidate.key == (caption.kind, caption.number, caption.page_num) else 0.0

    return (
        3.2 * proximity
        + 1.5 * overlap
        + 1.2 * same_col
        + 0.8 * candidate.confidence
        + owner_bonus
        - 2.5 * intervening
    )


def _dedupe_candidates(proposals: Sequence[RegionProposal]) -> List[RegionProposal]:
    unique: List[RegionProposal] = []
    for proposal in sorted(proposals, key=lambda p: p.confidence, reverse=True):
        duplicate = next(
            (
                existing for existing in unique
                if existing.caption.kind == proposal.caption.kind and _iou(existing.bbox, proposal.bbox) >= 0.94
            ),
            None,
        )
        if duplicate is None:
            unique.append(proposal)
    return unique


def resolve_page_assignments(
    captions: Sequence[Caption],
    proposals: Sequence[RegionProposal],
    layout: PageLayout,
) -> Dict[tuple[str, int, int], RegionProposal]:
    """Resolve competing caption→region proposals with one-to-one assignment.

    For ordinary pages with one Figure/Table this is a no-op. On dense pages
    with several captions it prevents two captions from silently claiming the
    same crop. Dummy candidates allow a low-quality caption to remain unassigned
    instead of stealing a neighbour's region.
    """

    result: Dict[tuple[str, int, int], RegionProposal] = {}
    if not proposals:
        return result

    for kind in ("figure", "table"):
        kind_caps = [c for c in captions if c.kind == kind]
        kind_props = [p for p in proposals if p.caption.kind == kind]
        if not kind_caps or not kind_props:
            continue
        if len(kind_caps) == 1:
            result[(kind_caps[0].kind, kind_caps[0].number, kind_caps[0].page_num)] = kind_props[0]
            continue

        candidates = _dedupe_candidates(kind_props)
        n_rows = len(kind_caps)
        n_real = len(candidates)
        n_cols = max(n_rows, n_real)
        scores = [[-4.0 for _ in range(n_cols)] for _ in range(n_rows)]

        for i, cap in enumerate(kind_caps):
            for j, candidate in enumerate(candidates):
                scores[i][j] = _score(cap, candidate, layout, kind_caps)

        row_ind, col_ind = linear_sum_assignment([[-value for value in row] for row in scores])
        for row, col in zip(row_ind, col_ind):
            if col >= n_real:
                continue
            score = scores[row][col]
            if score < 1.5:
                continue
            cap = kind_caps[row]
            candidate = candidates[col]
            result[(cap.kind, cap.number, cap.page_num)] = RegionProposal(
                caption=cap,
                bbox=candidate.bbox,
                confidence=min(candidate.confidence, 0.8) if candidate.key != (cap.kind, cap.number, cap.page_num) else candidate.confidence,
            )

        # Preserve non-conflicting original proposals. A proposal is omitted
        # only when it substantially duplicates a region already assigned to a
        # different caption, which is exactly the conflict this layer exists to
        # prevent.
        assigned_kind = [p for p in result.values() if p.caption.kind == kind]
        for proposal in kind_props:
            if proposal.key in result:
                continue
            if any(_iou(proposal.bbox, assigned.bbox) >= 0.90 for assigned in assigned_kind):
                continue
            result[proposal.key] = proposal

    return result
