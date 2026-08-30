from typing import List, Optional, Tuple
import fitz

from .captions import Caption
from .layout import PageLayout


def _get_image_blocks(page: fitz.Page) -> List[fitz.Rect]:
    rects = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") == 1:
            rects.append(fitz.Rect(b["bbox"]))
    return rects


def _get_drawing_rects(page: fitz.Page, min_width: float = 20.0) -> List[fitz.Rect]:
    rects = []
    for p in page.get_drawings():
        r = fitz.Rect(p["rect"])
        if r.width > min_width and r.height > 5:
            rects.append(r)
    return rects


def _get_hline_rects(page: fitz.Page, min_width: float = 30.0, max_height: float = 4.0) -> List[fitz.Rect]:
    rects = []
    for p in page.get_drawings():
        r = fitz.Rect(p["rect"])
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
    if rect.y0 < page_h * 0.09:
        return True
    return False


def _get_text_blocks(page: fitz.Page) -> List[Tuple[fitz.Rect, str, float]]:
    results = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        parts = []
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                parts.append(span.get("text", ""))
        text = " ".join(parts).strip()
        if text:
            results.append((fitz.Rect(b["bbox"]), text, b["bbox"][0]))
    return results


def _horizontal_overlap(a: fitz.Rect, b: fitz.Rect) -> float:
    overlap_x0 = max(a.x0, b.x0)
    overlap_x1 = min(a.x1, b.x1)
    if overlap_x1 <= overlap_x0:
        return 0.0
    overlap_width = overlap_x1 - overlap_x0
    min_width = min(a.width, b.width)
    if min_width <= 0:
        return 0.0
    return overlap_width / min_width


def _cluster_rects(rects: List[fitz.Rect], gap_threshold: float = 15.0) -> List[fitz.Rect]:
    if not rects:
        return []
    sorted_rects = sorted(rects, key=lambda r: (r.y0, r.x0))
    clusters: List[List[fitz.Rect]] = [[sorted_rects[0]]]

    for r in sorted_rects[1:]:
        merged = False
        for cluster in clusters:
            union = cluster[0]
            for cr in cluster[1:]:
                union = union | cr
            expanded = fitz.Rect(union.x0 - gap_threshold, union.y0 - gap_threshold,
                                 union.x1 + gap_threshold, union.y1 + gap_threshold)
            if r.intersects(expanded):
                cluster.append(r)
                merged = True
                break
        if not merged:
            clusters.append([r])

    result = []
    for cluster in clusters:
        union = cluster[0]
        for r in cluster[1:]:
            union = union | r
        result.append(union)
    return result


def _is_body_text_line(bbox: fitz.Rect, text: str, layout: PageLayout,
                       x_tolerance: float = 3.0, width_ratio: float = 0.75) -> bool:
    if layout.kind == "dual" and layout.column_boundary:
        col_width = layout.column_boundary - layout.text_left
        if bbox.x0 < layout.column_boundary:
            expected_x0 = layout.text_left
            expected_width = col_width
        else:
            expected_x0 = layout.column_boundary
            expected_width = layout.text_right - layout.column_boundary
    else:
        expected_x0 = layout.text_left
        expected_width = layout.text_right - layout.text_left

    x_aligned = abs(bbox.x0 - expected_x0) < x_tolerance + 2
    wide_enough = bbox.width > expected_width * width_ratio
    return x_aligned and wide_enough


def locate_figure_content(
    page: fitz.Page,
    caption: Caption,
    layout: PageLayout,
    all_captions: List[Caption],
) -> Tuple[Optional[fitz.Rect], float]:
    """Search upward from caption to find figure content. Returns (bbox, confidence)."""
    page_rect = page.mediabox
    cap_y0 = caption.bbox.y0

    boundary = layout.column_boundary or (page_rect.width / 2.0)
    if caption.dual_column and caption.column_side:
        if caption.column_side == "left":
            search_x0, search_x1 = page_rect.x0, boundary
        else:
            search_x0, search_x1 = boundary, page_rect.x1
    else:
        search_x0, search_x1 = page_rect.x0, page_rect.x1

    search_region = fitz.Rect(search_x0, page_rect.y0, search_x1, cap_y0)

    img_rects = [r for r in _get_image_blocks(page)
                 if r.intersects(search_region) and _horizontal_overlap(r, caption.bbox) > 0.3]
    draw_rects = [r for r in _get_drawing_rects(page)
                  if r.intersects(search_region) and _horizontal_overlap(r, caption.bbox) > 0.3]

    indented_text_rects = []
    text_blocks = _get_text_blocks(page)
    for bbox, text, x0 in text_blocks:
        if not bbox.intersects(search_region):
            continue
        if bbox.y0 >= cap_y0:
            continue
        is_indented = x0 > layout.text_left + 5
        is_not_caption = not text.lower().startswith(("figure", "fig.", "table"))
        if is_indented and is_not_caption:
            indented_text_rects.append(bbox)

    upper_bound = page_rect.y0 + 30
    for bbox, text, x0 in text_blocks:
        if bbox.y1 >= cap_y0:
            continue
        if not bbox.intersects(search_region):
            continue
        if _is_body_text_line(bbox, text, layout):
            if bbox.y1 > upper_bound:
                upper_bound = bbox.y1

    for other_cap in all_captions:
        if other_cap is caption:
            continue
        if other_cap.page_num != caption.page_num:
            continue
        if other_cap.bbox.y1 < cap_y0 and other_cap.bbox.y1 > upper_bound:
            upper_bound = other_cap.bbox.y1

    all_signal_rects = img_rects + draw_rects + indented_text_rects
    all_signal_rects = [r for r in all_signal_rects if r.y0 > upper_bound - 5]

    if not all_signal_rects:
        fallback = fitz.Rect(search_x0 + 10, upper_bound, search_x1 - 10, cap_y0 - 2)
        if fallback.height > 30:
            return fallback, 0.5
        return None, 0.0

    clusters = _cluster_rects(all_signal_rects, gap_threshold=15.0)

    relevant_clusters = []
    for c in clusters:
        if _horizontal_overlap(c, caption.bbox) > 0.2 or c.intersects(caption.bbox):
            relevant_clusters.append(c)

    if not relevant_clusters:
        relevant_clusters = clusters

    content_bbox = relevant_clusters[0]
    for c in relevant_clusters[1:]:
        content_bbox = content_bbox | c

    content_bbox = fitz.Rect(
        max(content_bbox.x0, search_x0),
        max(content_bbox.y0, upper_bound),
        min(content_bbox.x1, search_x1),
        min(content_bbox.y1, cap_y0 - 7),
    )

    has_visual = bool(img_rects or draw_rects)
    found_upper_body = upper_bound > page_rect.y0 + 35

    if has_visual and found_upper_body:
        confidence = 0.9
    elif has_visual or found_upper_body:
        confidence = 0.7
    elif indented_text_rects:
        confidence = 0.6
    else:
        confidence = 0.5

    return content_bbox, confidence


def locate_table_content(
    page: fitz.Page,
    caption: Caption,
    layout: PageLayout,
    all_captions: List[Caption],
) -> Tuple[Optional[fitz.Rect], float]:
    """Search downward from caption to find table content. Returns (bbox, confidence)."""
    page_rect = page.mediabox
    cap_y1 = caption.bbox.y1

    boundary = layout.column_boundary or (page_rect.width / 2.0)
    if caption.dual_column and caption.column_side:
        if caption.column_side == "left":
            search_x0, search_x1 = page_rect.x0, boundary
        else:
            search_x0, search_x1 = boundary, page_rect.x1
    else:
        search_x0, search_x1 = page_rect.x0, page_rect.x1

    cap_y0 = caption.bbox.y0
    img_blocks = _get_image_blocks(page)

    hlines = _get_hline_rects(page)
    hlines = [r for r in hlines if not _is_header_line(r, page, img_blocks)]

    def overlaps_x(r: fitz.Rect) -> bool:
        ox0 = max(r.x0, search_x0)
        ox1 = min(r.x1, search_x1)
        if ox1 <= ox0:
            return False
        rw = r.x1 - r.x0
        return rw > 0 and (ox1 - ox0) / rw > 0.3

    hlines = [r for r in hlines if overlaps_x(r)]

    above_h = sorted([r for r in hlines if r.y1 < cap_y0], key=lambda r: r.y0)
    below_h = sorted([r for r in hlines if r.y0 > cap_y1], key=lambda r: r.y0)

    use_above = len(above_h) > 0 and len(above_h) >= len(below_h)
    use_below = (not use_above) and len(below_h) > 0

    if use_above:
        x0 = min(r.x0 for r in above_h)
        x1 = max(r.x1 for r in above_h)
        top_y = above_h[0].y0
        for bbox, text, bx0 in _get_text_blocks(page):
            if bbox.y1 <= top_y + 2 and bbox.y0 >= top_y - 30 and overlaps_x(bbox):
                if not text.lower().startswith(("figure", "fig.", "table")):
                    top_y = min(top_y, bbox.y0)
        content_bbox = fitz.Rect(
            max(x0, search_x0),
            max(top_y - 4, page_rect.y0),
            min(x1, search_x1),
            min(cap_y0 - 7, page_rect.y1),
        )
        return content_bbox, (0.9 if len(above_h) >= 2 else 0.7)

    if use_below:
        x0 = min(r.x0 for r in below_h)
        x1 = max(r.x1 for r in below_h)
        content_bbox = fitz.Rect(
            max(x0, search_x0),
            max(cap_y1 + 2, page_rect.y0),
            min(x1, search_x1),
            min(below_h[-1].y1 + 4, page_rect.y1),
        )
        return content_bbox, (0.9 if len(below_h) >= 2 else 0.7)

    search_region = fitz.Rect(search_x0, page_rect.y0, search_x1, cap_y0)
    text_blocks = _get_text_blocks(page)
    upper_bound = page_rect.y0 + 30
    for bbox, text, x0 in text_blocks:
        if bbox.y1 >= cap_y0 or not bbox.intersects(search_region):
            continue
        if _is_body_text_line(bbox, text, layout) and bbox.y1 > upper_bound:
            upper_bound = bbox.y1
    for other_cap in all_captions:
        if other_cap is caption or other_cap.page_num != caption.page_num:
            continue
        if other_cap.bbox.y1 < cap_y0 and other_cap.bbox.y1 > upper_bound:
            upper_bound = other_cap.bbox.y1
    fallback = fitz.Rect(search_x0 + 10, upper_bound, search_x1 - 10, cap_y0 - 2)
    if fallback.height > 20:
        return fallback, 0.5
    return None, 0.0
