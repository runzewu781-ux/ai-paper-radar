from typing import List, Optional, Sequence, Tuple
import math
import fitz

from .captions import Caption
from .layout import PageLayout
from .text_types import TypedLine


TextBlock = Tuple[fitz.Rect, str, float, int]


def _get_image_blocks(page: fitz.Page) -> List[fitz.Rect]:
    return [
        fitz.Rect(b["bbox"])
        for b in page.get_text("dict")["blocks"]
        if b.get("type") == 1
    ]


def _get_drawing_rects(page: fitz.Page, min_width: float = 8.0) -> List[fitz.Rect]:
    rects: List[fitz.Rect] = []
    for drawing in page.get_drawings():
        r = fitz.Rect(drawing["rect"])
        if r.width >= min_width and (r.height >= 1.0 or r.width >= 20.0):
            rects.append(r)
    return rects


def _get_hline_rects(page: fitz.Page, min_width: float = 30.0, max_height: float = 4.0) -> List[fitz.Rect]:
    rects: List[fitz.Rect] = []
    for drawing in page.get_drawings():
        r = fitz.Rect(drawing["rect"])
        if r.width > min_width and r.height < max_height:
            rects.append(r)
    return rects


def _is_header_line(rect: fitz.Rect, page: fitz.Page, img_blocks: List[fitz.Rect]) -> bool:
    page_h = page.mediabox.height
    if rect.y0 > page_h * 0.12:
        return False
    for ib in img_blocks:
        if ib.y0 < page_h * 0.12 and rect.y0 < ib.y1 + 35:
            return True
    return rect.y0 < page_h * 0.09


def _get_text_blocks(page: fitz.Page) -> List[TextBlock]:
    results: List[TextBlock] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        parts = []
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                parts.append(span.get("text", ""))
        text = " ".join(parts).strip()
        if text:
            results.append((fitz.Rect(block["bbox"]), text, block["bbox"][0], len(block.get("lines", []))))
    return results


def _horizontal_overlap(a: fitz.Rect, b: fitz.Rect) -> float:
    overlap_x0 = max(a.x0, b.x0)
    overlap_x1 = min(a.x1, b.x1)
    if overlap_x1 <= overlap_x0:
        return 0.0
    minimum = min(a.width, b.width)
    return 0.0 if minimum <= 0 else (overlap_x1 - overlap_x0) / minimum


def _rect_distance(a: fitz.Rect, b: fitz.Rect) -> float:
    dx = max(a.x0 - b.x1, b.x0 - a.x1, 0.0)
    dy = max(a.y0 - b.y1, b.y0 - a.y1, 0.0)
    return math.hypot(dx, dy)


def _bounds(rects: List[fitz.Rect]) -> fitz.Rect:
    """Bounding rect that also works for zero-height PDF ruling lines."""
    return fitz.Rect(
        min(r.x0 for r in rects),
        min(r.y0 for r in rects),
        max(r.x1 for r in rects),
        max(r.y1 for r in rects),
    )


def _cluster_rects(rects: List[fitz.Rect], gap_threshold: float = 15.0) -> List[Tuple[fitz.Rect, List[fitz.Rect]]]:
    if not rects:
        return []
    clusters: List[List[fitz.Rect]] = []
    for r in sorted(rects, key=lambda x: (x.y0, x.x0)):
        chosen: Optional[List[fitz.Rect]] = None
        for cluster in clusters:
            union = _bounds(cluster)
            expanded = fitz.Rect(
                union.x0 - gap_threshold, union.y0 - gap_threshold,
                union.x1 + gap_threshold, union.y1 + gap_threshold,
            )
            if r.intersects(expanded):
                chosen = cluster
                break
        if chosen is None:
            clusters.append([r])
        else:
            chosen.append(r)

    result: List[Tuple[fitz.Rect, List[fitz.Rect]]] = []
    for members in clusters:
        result.append((_bounds(members), members))
    return result


def _column_bounds(page: fitz.Page, caption: Caption, layout: PageLayout) -> Tuple[float, float]:
    rect = page.mediabox
    if layout.kind != "dual" or layout.column_boundary is None:
        return rect.x0, rect.x1

    boundary = layout.column_boundary
    left_overlap = max(0.0, min(caption.bbox.x1, boundary) - caption.bbox.x0)
    right_overlap = max(0.0, caption.bbox.x1 - max(caption.bbox.x0, boundary))
    cap_width = max(caption.bbox.width, 1.0)

    if left_overlap / cap_width >= 0.22 and right_overlap / cap_width >= 0.22:
        return rect.x0, rect.x1
    if right_overlap > left_overlap:
        return boundary, rect.x1
    return rect.x0, boundary


def _expected_column(layout: PageLayout, bbox: fitz.Rect) -> Tuple[float, float]:
    if layout.kind == "dual" and layout.column_boundary is not None:
        if (bbox.x0 + bbox.x1) / 2.0 < layout.column_boundary:
            x0 = layout.left_col_left if layout.left_col_left is not None else layout.text_left
            x1 = layout.left_col_right if layout.left_col_right is not None else layout.column_boundary
        else:
            x0 = layout.right_col_left if layout.right_col_left is not None else layout.column_boundary
            x1 = layout.right_col_right if layout.right_col_right is not None else layout.text_right
        return x0, max(x1, x0 + 1.0)
    return layout.text_left, max(layout.text_right, layout.text_left + 1.0)


def _typed_body_support(bbox: fitz.Rect, typed_lines: Optional[Sequence[TypedLine]]) -> bool:
    if not typed_lines:
        return False
    body_hits = 0
    body_chars = 0
    for line in typed_lines:
        if not line.is_body_like:
            continue
        inter = line.bbox & bbox
        if inter.is_empty or line.bbox.width <= 0 or line.bbox.height <= 0:
            continue
        ratio = (inter.width * inter.height) / max(line.bbox.width * line.bbox.height, 1.0)
        if ratio >= 0.55:
            body_hits += 1
            body_chars += len(line.text)
    return body_hits >= 2 and body_chars >= 80


def _is_body_text_block(
    bbox: fitz.Rect,
    text: str,
    line_count: int,
    layout: PageLayout,
    typed_lines: Optional[Sequence[TypedLine]] = None,
) -> bool:
    if text.lower().startswith(("figure", "fig.", "table")):
        return False
    if _typed_body_support(bbox, typed_lines):
        return True
    if (
        layout.kind == "dual"
        and layout.column_boundary is not None
        and bbox.x0 < layout.column_boundary - 20
        and bbox.x1 > layout.column_boundary + 20
        and line_count >= 3
        and len(text) >= 120
    ):
        return True
    expected_x0, expected_x1 = _expected_column(layout, bbox)
    expected_width = max(expected_x1 - expected_x0, 1.0)
    aligned = abs(bbox.x0 - expected_x0) <= max(10.0, expected_width * 0.08)
    wide = bbox.width >= expected_width * 0.58
    paragraph = line_count >= 3 and len(text) >= 120
    dense_paragraph = line_count >= 6 and len(text) >= 180
    return (aligned and wide and paragraph) or dense_paragraph


def _other_caption_between(cluster: fitz.Rect, caption: Caption, all_captions: List[Caption]) -> bool:
    if cluster.y1 <= caption.bbox.y0:
        low, high = cluster.y1, caption.bbox.y0
    elif cluster.y0 >= caption.bbox.y1:
        low, high = caption.bbox.y1, cluster.y0
    else:
        return False
    for other in all_captions:
        if other is caption or other.page_num != caption.page_num:
            continue
        cy = (other.bbox.y0 + other.bbox.y1) / 2.0
        if low < cy < high:
            return True
    return False


def _expand_with_nearby_labels(
    bbox: fitz.Rect,
    text_blocks: List[TextBlock],
    layout: PageLayout,
    search_x0: float,
    search_x1: float,
    upper_y: float,
    lower_y: float,
    typed_lines: Optional[Sequence[TypedLine]] = None,
) -> fitz.Rect:
    expanded = bbox
    halo = fitz.Rect(bbox.x0 - 14, bbox.y0 - 16, bbox.x1 + 14, bbox.y1 + 16)
    for tb, text, _, line_count in text_blocks:
        if tb.y1 < upper_y or tb.y0 > lower_y:
            continue
        if tb.x1 < search_x0 or tb.x0 > search_x1:
            continue
        if not tb.intersects(halo):
            continue
        if _is_body_text_block(tb, text, line_count, layout, typed_lines):
            continue
        if text.lower().startswith(("figure", "fig.", "table")):
            continue
        expanded = expanded | tb
    return expanded


def locate_figure_content(
    page: fitz.Page,
    caption: Caption,
    layout: PageLayout,
    all_captions: List[Caption],
    typed_lines: Optional[Sequence[TypedLine]] = None,
) -> Tuple[Optional[fitz.Rect], float]:
    """Find the best visual cluster immediately preceding a Figure caption."""
    page_rect = page.mediabox
    cap_y0 = caption.bbox.y0
    search_x0, search_x1 = _column_bounds(page, caption, layout)
    search_region = fitz.Rect(search_x0, page_rect.y0, search_x1, cap_y0)
    text_blocks = _get_text_blocks(page)
    img_blocks = _get_image_blocks(page)

    previous_caption_y = page_rect.y0 + 18
    for other in all_captions:
        if other is caption or other.page_num != caption.page_num:
            continue
        if other.bbox.y1 < cap_y0:
            previous_caption_y = max(previous_caption_y, other.bbox.y1)

    signals: List[fitz.Rect] = []
    page_area = max(page_rect.width * page_rect.height, 1.0)
    for r in img_blocks + _get_drawing_rects(page):
        if not r.intersects(search_region):
            continue
        if r.y1 <= previous_caption_y - 3 or r.y0 >= cap_y0 or r.y1 > cap_y0 - 2:
            continue
        if _is_header_line(r, page, img_blocks):
            continue
        area = max(r.width, 0.0) * max(r.height, 0.0)
        if (
            r.width >= page_rect.width * 0.95
            and r.y0 < page_rect.height * 0.20
            and area >= page_area * 0.28
        ):
            # Page-level decoration/background, not the figure itself.
            continue
        if min(r.x1, search_x1) - max(r.x0, search_x0) <= 2:
            continue
        signals.append(r)

    clusters = _cluster_rects(signals, gap_threshold=14.0)
    candidates: List[Tuple[float, fitz.Rect, int]] = []
    region_area = max(search_region.width * search_region.height, 1.0)
    for cluster, members in clusters:
        if cluster.y1 > cap_y0 + 2 or cluster.y0 < previous_caption_y - 3:
            continue
        if _other_caption_between(cluster, caption, all_captions):
            continue
        distance = max(0.0, cap_y0 - cluster.y1)
        if distance > page_rect.height * 0.48:
            continue
        proximity = max(0.0, 1.0 - distance / (page_rect.height * 0.34))
        overlap = _horizontal_overlap(cluster, caption.bbox)
        area = min(1.0, (cluster.width * max(cluster.height, 2.0)) / (region_area * 0.22))
        member_score = min(1.0, len(members) / 8.0)
        score = 3.2 * proximity + 1.7 * overlap + 1.1 * area + 0.8 * member_score
        candidates.append((score, cluster, len(members)))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        score, best, member_count = candidates[0]

        changed = True
        while changed:
            changed = False
            for _, other, _ in candidates[1:]:
                if other.intersects(best):
                    continue
                close = _rect_distance(best, other) <= 28.0
                aligned = _horizontal_overlap(best, other) >= 0.25
                if close and aligned and not _other_caption_between(other, caption, all_captions):
                    best = best | other
                    changed = True

        best = _expand_with_nearby_labels(
            best, text_blocks, layout, search_x0, search_x1,
            previous_caption_y, cap_y0 - 2, typed_lines,
        )
        content_bbox = fitz.Rect(
            max(best.x0, search_x0),
            max(best.y0, previous_caption_y),
            min(best.x1, search_x1),
            min(best.y1, cap_y0 - 8),
        )
        min_visual_width = max(20.0, (search_x1 - search_x0) * 0.18)
        if content_bbox.width > min_visual_width and content_bbox.height > 20:
            confidence = 0.9 if score >= 4.2 and member_count >= 2 else 0.8
            return content_bbox, confidence

    upper_bound = previous_caption_y
    header_lines = [
        r for r in _get_hline_rects(page)
        if _is_header_line(r, page, img_blocks)
        and min(r.x1, search_x1) - max(r.x0, search_x0) > (search_x1 - search_x0) * 0.45
    ]
    if header_lines:
        upper_bound = max(upper_bound, max(r.y1 for r in header_lines) + 5)
    for tb, text, _, line_count in text_blocks:
        if tb.y1 >= cap_y0 or not tb.intersects(search_region):
            continue
        if _is_body_text_block(tb, text, line_count, layout, typed_lines):
            upper_bound = max(upper_bound, tb.y1)
    fallback = fitz.Rect(search_x0 + 6, upper_bound + 2, search_x1 - 6, cap_y0 - 8)
    if fallback.width > 20 and fallback.height > 25:
        return fallback, 0.5
    return None, 0.0


def _cluster_hlines(hlines: List[fitz.Rect], page_height: float) -> List[Tuple[fitz.Rect, List[fitz.Rect]]]:
    if not hlines:
        return []
    max_gap = max(58.0, page_height * 0.085)
    groups: List[List[fitz.Rect]] = []
    for line in sorted(hlines, key=lambda r: r.y0):
        if not groups:
            groups.append([line])
            continue
        current = groups[-1]
        prev = current[-1]
        y_gap = line.y0 - prev.y1
        same_span = _horizontal_overlap(line, prev) >= 0.62
        similar_width = min(line.width, prev.width) / max(line.width, prev.width) >= 0.65
        if y_gap <= max_gap and (same_span or similar_width):
            current.append(line)
        else:
            groups.append([line])

    result: List[Tuple[fitz.Rect, List[fitz.Rect]]] = []
    for members in groups:
        result.append((_bounds(members), members))
    return result


def _bounded_ruled_table_candidate(
    caption: Caption,
    all_captions: List[Caption],
    hlines: List[fitz.Rect],
    search_x0: float,
    search_x1: float,
    page_rect: fitz.Rect,
) -> Optional[fitz.Rect]:
    """Build a ruled-table envelope without crossing another caption."""
    search_width = max(search_x1 - search_x0, 1.0)

    def overlaps_search(other: Caption) -> bool:
        overlap = min(other.bbox.x1, search_x1) - max(other.bbox.x0, search_x0)
        return overlap > 0 and overlap / max(other.bbox.width, 1.0) >= 0.30

    previous_barrier = page_rect.y0 + 18
    next_barrier = page_rect.y1 - 18
    for other in all_captions:
        if other is caption or other.page_num != caption.page_num or not overlaps_search(other):
            continue
        if other.bbox.y1 <= caption.bbox.y0:
            previous_barrier = max(previous_barrier, other.bbox.y1 + 2)
        elif other.bbox.y0 >= caption.bbox.y1:
            next_barrier = min(next_barrier, other.bbox.y0 - 2)

    directional: List[Tuple[float, str, List[fitz.Rect]]] = []
    above = [
        r for r in hlines
        if r.y0 >= previous_barrier and r.y1 <= caption.bbox.y0 - 2
    ]
    below = [
        r for r in hlines
        if r.y0 >= caption.bbox.y1 + 1 and r.y1 <= next_barrier
    ]
    if above:
        nearest = max(above, key=lambda r: r.y1)
        directional.append((caption.bbox.y0 - nearest.y1, "above", above))
    if below:
        nearest = min(below, key=lambda r: r.y0)
        directional.append((nearest.y0 - caption.bbox.y1, "below", below))
    if not directional:
        return None

    directional.sort(key=lambda item: item[0])
    for distance, direction, lines in directional:
        if distance > max(48.0, page_rect.height * 0.085):
            continue
        seed = max(lines, key=lambda r: r.y1) if direction == "above" else min(lines, key=lambda r: r.y0)
        compatible: List[fitz.Rect] = []
        for line in lines:
            width_ratio = min(line.width, seed.width) / max(line.width, seed.width, 1.0)
            if _horizontal_overlap(line, seed) >= 0.72 and width_ratio >= 0.68:
                compatible.append(line)
        if len(compatible) < 2:
            continue

        x0 = max(search_x0, min(r.x0 for r in compatible) - 2)
        x1 = min(search_x1, max(r.x1 for r in compatible) + 2)
        y0 = max(page_rect.y0, min(r.y0 for r in compatible) - 1)
        y1 = min(page_rect.y1, max(r.y1 for r in compatible) + 1)
        bbox = fitz.Rect(x0, y0, x1, y1)
        if (
            bbox.width >= search_width * 0.35
            and bbox.height >= 10
            and not _other_caption_between(bbox, caption, all_captions)
        ):
            return bbox
    return None


def locate_table_content(
    page: fitz.Page,
    caption: Caption,
    layout: PageLayout,
    all_captions: List[Caption],
    typed_lines: Optional[Sequence[TypedLine]] = None,
) -> Tuple[Optional[fitz.Rect], float]:
    """Find the nearest coherent table-rule cluster around a Table caption."""
    page_rect = page.mediabox
    search_x0, search_x1 = _column_bounds(page, caption, layout)
    img_blocks = _get_image_blocks(page)
    text_blocks = _get_text_blocks(page)

    def in_column(r: fitz.Rect) -> bool:
        overlap = min(r.x1, search_x1) - max(r.x0, search_x0)
        return overlap > 0 and overlap / max(r.width, 1.0) >= 0.35

    hlines = [
        r for r in _get_hline_rects(page)
        if in_column(r) and not _is_header_line(r, page, img_blocks)
    ]

    bounded_ruled = _bounded_ruled_table_candidate(
        caption, all_captions, hlines, search_x0, search_x1, page_rect,
    )
    if bounded_ruled is not None:
        # Ruling lines often mark only a header separator or one internal row.
        # Re-attach nearby short/dense text blocks inside the same caption
        # barrier so a valid table is not collapsed to a single ruled strip.
        expanded = bounded_ruled
        above_caption = bounded_ruled.y1 <= caption.bbox.y0
        lower_limit = caption.bbox.y0 - 8 if above_caption else page_rect.y1
        upper_limit = page_rect.y0 if above_caption else caption.bbox.y1 + 4
        for tb, text, _, line_count in text_blocks:
            if text.lower().startswith(("figure", "fig.", "table")):
                continue
            if tb.x1 < bounded_ruled.x0 - 10 or tb.x0 > bounded_ruled.x1 + 10:
                continue
            chars_per_line = len(text) / max(line_count, 1)
            if _is_body_text_block(tb, text, line_count, layout, typed_lines):
                continue
            if line_count >= 3 and len(text) >= 110 and chars_per_line >= 30:
                continue
            if above_caption:
                if tb.y1 < bounded_ruled.y0 - 18 or tb.y0 > lower_limit:
                    continue
            else:
                if tb.y1 < upper_limit or tb.y0 > bounded_ruled.y1 + 18:
                    continue
            expanded = expanded | tb

        bounded_ruled = fitz.Rect(
            max(search_x0, expanded.x0 - 2),
            max(page_rect.y0, expanded.y0 - 1),
            min(search_x1, expanded.x1 + 2),
            min(caption.bbox.y0 - 8, expanded.y1 + 1) if above_caption else min(page_rect.y1, expanded.y1 + 1),
        )
        if bounded_ruled.width > 30 and bounded_ruled.height > 18:
            return bounded_ruled, 0.9

    clusters = _cluster_hlines(hlines, page_rect.height)

    candidates: List[Tuple[float, fitz.Rect, List[fitz.Rect], str]] = []
    for cluster, members in clusters:
        if cluster.y1 <= caption.bbox.y0:
            direction = "above"
            distance = caption.bbox.y0 - cluster.y1
        elif cluster.y0 >= caption.bbox.y1:
            direction = "below"
            distance = cluster.y0 - caption.bbox.y1
        else:
            continue
        if distance > page_rect.height * 0.36:
            continue
        if _other_caption_between(cluster, caption, all_captions):
            continue

        proximity = max(0.0, 1.0 - distance / (page_rect.height * 0.24))
        overlap = _horizontal_overlap(cluster, caption.bbox)
        line_score = min(1.0, len(members) / 3.0)
        width_score = min(1.0, cluster.width / max(search_x1 - search_x0, 1.0))
        score = 4.0 * proximity + 1.4 * overlap + 1.2 * line_score + 0.7 * width_score
        candidates.append((score, cluster, members, direction))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        score, cluster, members, direction = candidates[0]
        x0 = max(search_x0, min(r.x0 for r in members) - 4)
        x1 = min(search_x1, max(r.x1 for r in members) + 4)
        y0 = max(page_rect.y0, cluster.y0 - 4)
        y1 = min(page_rect.y1, cluster.y1 + 4)

        for tb, text, _, line_count in text_blocks:
            if text.lower().startswith(("figure", "fig.", "table")):
                continue
            if tb.x1 < x0 - 6 or tb.x0 > x1 + 6:
                continue
            chars_per_line = len(text) / max(line_count, 1)
            if line_count >= 3 and len(text) >= 110 and chars_per_line >= 30:
                # Prose immediately above/below a table is not a table cell.
                continue
            if tb.y1 >= cluster.y0 - 18 and tb.y0 <= cluster.y1 + 18:
                x0 = max(search_x0, min(x0, tb.x0 - 2))
                x1 = min(search_x1, max(x1, tb.x1 + 2))
                y0 = max(page_rect.y0, min(y0, tb.y0 - 2))
                y1 = min(page_rect.y1, max(y1, tb.y1 + 2))

        if direction == "above":
            y1 = min(y1, caption.bbox.y0 - 8)
        else:
            y0 = max(y0, caption.bbox.y1 + 4)

        bbox = fitz.Rect(x0, y0, x1, y1)
        if bbox.width > 30 and bbox.height > 18:
            confidence = 0.9 if score >= 5.0 and len(members) >= 2 else 0.8
            return bbox, confidence

    # Some prompt/code tables have only a top and bottom rule separated by a
    # large text region, so vertical clustering intentionally splits the two
    # rules. Pair the nearest bottom rule with an earlier rule of the same span.
    above_lines = sorted(
        [r for r in hlines if r.y1 < caption.bbox.y0],
        key=lambda r: r.y0,
    )
    if above_lines:
        bottom = above_lines[-1]
        compatible = []
        for top in above_lines[:-1]:
            width_ratio = min(top.width, bottom.width) / max(top.width, bottom.width, 1.0)
            if _horizontal_overlap(top, bottom) < 0.75 or width_ratio < 0.75:
                continue
            pair = fitz.Rect(
                min(top.x0, bottom.x0), top.y0,
                max(top.x1, bottom.x1), bottom.y1,
            )
            if pair.height > page_rect.height * 0.7:
                continue
            if _other_caption_between(pair, caption, all_captions):
                continue
            compatible.append(top)
        if compatible:
            top = compatible[0]
            pair_bbox = fitz.Rect(
                max(search_x0, min(top.x0, bottom.x0) - 4),
                max(page_rect.y0, top.y0 - 4),
                min(search_x1, max(top.x1, bottom.x1) + 4),
                min(caption.bbox.y0 - 8, bottom.y1 + 4),
            )
            if pair_bbox.width > 30 and pair_bbox.height > 24:
                return pair_bbox, 0.9

    # Borderless tables may be represented as one dense multi-line text block.
    # If the nearest block before the caption is tabular (many short lines) and
    # tightly adjacent to the caption, use it as a conservative fallback.
    preceding = []
    for tb, text, _, line_count in text_blocks:
        if tb.y1 >= caption.bbox.y0:
            continue
        if tb.x1 < search_x0 or tb.x0 > search_x1:
            continue
        gap = caption.bbox.y0 - tb.y1
        chars_per_line = len(text) / max(line_count, 1)
        if gap <= 32 and line_count >= 4 and len(text) >= 80 and chars_per_line <= 55:
            preceding.append((gap, tb))
    if preceding:
        preceding.sort(key=lambda item: item[0])
        _, tb = preceding[0]
        borderless = fitz.Rect(
            max(search_x0, tb.x0 - 4),
            max(page_rect.y0, tb.y0 - 4),
            min(search_x1, tb.x1 + 4),
            min(caption.bbox.y0 - 8, tb.y1 + 4),
        )
        if borderless.width > 30 and borderless.height > 20:
            return borderless, 0.8

    cap_y0 = caption.bbox.y0
    upper_bound = page_rect.y0 + 24
    for tb, text, _, line_count in text_blocks:
        if tb.y1 >= cap_y0:
            continue
        if tb.x1 < search_x0 or tb.x0 > search_x1:
            continue
        if _is_body_text_block(tb, text, line_count, layout, typed_lines):
            upper_bound = max(upper_bound, tb.y1)
    fallback = fitz.Rect(search_x0 + 8, upper_bound + 2, search_x1 - 8, cap_y0 - 4)
    if fallback.width > 30 and fallback.height > 20:
        return fallback, 0.5
    return None, 0.0
