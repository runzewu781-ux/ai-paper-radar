import asyncio
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

import fitz
from PIL import Image

from .captions import find_captions, Caption
from .layout import detect_layout, PageLayout
from .locate import locate_figure_content, locate_table_content
from .crop import render_and_trim
from .quality import run_quality_checks
from .report import write_manifest, generate_contact_sheet
from .classify import classify_image
from .matching import RegionProposal, resolve_page_assignments
from .text_types import classify_page_lines
from .typography import estimate_document_typography


async def run_extraction(
    pdf_path: str,
    output_dir: str,
    dpi: int = 200,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    model: str = "qwen3.8-max-preview",
    skip_classify: bool = False,
) -> Dict[str, Any]:
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    figures_dir = output_dir / "figures"
    tables_dir = output_dir / "tables"
    review_dir = output_dir / "review_required"

    for d in (figures_dir, tables_dir, review_dir):
        d.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    typography = estimate_document_typography(doc)
    print(
        "[figure_extractor] Typography: "
        f"font={typography.body_font} size={typography.body_size:.1f} "
        f"gap={typography.body_line_gap:.1f} confidence={typography.confidence:.2f}"
    )

    captions = find_captions(doc, typography)
    print(f"[figure_extractor] Found {len(captions)} captions "
          f"({sum(1 for c in captions if c.kind == 'figure')} figures, "
          f"{sum(1 for c in captions if c.kind == 'table')} tables)")

    layouts: Dict[int, PageLayout] = {}
    typed_lines: Dict[int, list] = {}
    for page_num in range(total_pages):
        page_captions = [c for c in captions if c.page_num == page_num]
        typed_lines[page_num] = classify_page_lines(
            doc[page_num], typography, page_captions, page_num=page_num,
        )
        layouts[page_num] = detect_layout(
            doc[page_num], typography, typed_lines[page_num],
        )

    raw_proposals: Dict[tuple, RegionProposal] = {}
    proposals_by_page: Dict[int, List[RegionProposal]] = {}
    for cap in captions:
        page = doc[cap.page_num]
        layout = layouts[cap.page_num]
        page_captions = [c for c in captions if c.page_num == cap.page_num]
        page_lines = typed_lines[cap.page_num]
        if cap.kind == "figure":
            bbox, confidence = locate_figure_content(
                page, cap, layout, page_captions, page_lines,
            )
        else:
            bbox, confidence = locate_table_content(
                page, cap, layout, page_captions, page_lines,
            )
        if bbox is None:
            continue
        proposal = RegionProposal(cap, bbox, confidence)
        raw_proposals[proposal.key] = proposal
        proposals_by_page.setdefault(cap.page_num, []).append(proposal)

    assigned_proposals: Dict[tuple, RegionProposal] = {}
    for page_num, proposals in proposals_by_page.items():
        page_captions = [c for c in captions if c.page_num == page_num]
        assigned_proposals.update(
            resolve_page_assignments(page_captions, proposals, layouts[page_num])
        )

    items: List[Dict[str, Any]] = []
    images_for_sheet: List[Dict[str, Any]] = []

    for cap in captions:
        page = doc[cap.page_num]
        layout = layouts[cap.page_num]
        page_captions = [c for c in captions if c.page_num == cap.page_num]

        key = (cap.kind, cap.number, cap.page_num)
        proposal = assigned_proposals.get(key)
        if proposal is None:
            reason = "assignment conflict" if key in raw_proposals else "no content found"
            print(f"[figure_extractor] SKIP {cap.label} (p{cap.page_num+1}): {reason}")
            continue
        bbox, confidence = proposal.bbox, proposal.confidence

        img = render_and_trim(
            page,
            bbox,
            dpi=dpi,
            padding=0.0 if cap.kind == "table" else 5.0,
        )

        page_rect = page.mediabox
        scale = dpi / 72.0
        qr = run_quality_checks(
            img, bbox, page_rect, confidence,
            page_width_px=page_rect.width * scale,
            page_height_px=page_rect.height * scale,
            page=page,
            layout=layout,
            caption=cap,
            typed_lines=typed_lines[cap.page_num],
        )

        visual_type = cap.kind
        if not skip_classify and img is not None and cap.kind == "figure" and not qr.is_blank:
            visual_type = await classify_image(img, api_key=api_key, api_base=api_base, model=model)

        if qr.needs_review:
            dest_dir = review_dir
        elif cap.kind == "table":
            dest_dir = tables_dir
        else:
            dest_dir = figures_dir

        filename = f"{cap.kind}_{cap.number}.png"
        dest_path = dest_dir / filename

        if img is not None:
            img.save(str(dest_path), "PNG")

        item = {
            "file": f"{dest_dir.name}/{filename}",
            "kind": cap.kind,
            "number": str(cap.number),
            "sub_labels": cap.sub_labels,
            "page": cap.page_num,
            "caption": cap.text,
            "bbox": [round(bbox.x0, 1), round(bbox.y0, 1),
                     round(bbox.x1, 1), round(bbox.y1, 1)],
            "confidence": confidence,
            "needs_review": qr.needs_review,
            "has_body_text_contamination": qr.has_body_text_contamination,
            "body_text_chars": qr.body_text_chars,
            "visual_type": visual_type,
            "layout": layout.kind,
            "issues": qr.issues,
            "qa_metrics": qr.metrics.to_dict() if qr.metrics is not None else {},
            "typography": {
                "body_font": typography.body_font,
                "body_size": typography.body_size,
                "body_line_gap": typography.body_line_gap,
                "profile_confidence": typography.confidence,
            },
        }
        items.append(item)

        if img is not None:
            sheet_item = dict(item)
            sheet_item["_img"] = img
            images_for_sheet.append(sheet_item)

        status = "REVIEW" if qr.needs_review else "OK"
        print(f"[figure_extractor] {status} {cap.label} (p{cap.page_num+1}) "
              f"conf={confidence:.1f} type={visual_type} "
              f"size={img.size if img else 'None'}")

    doc.close()

    manifest_path = write_manifest(items, output_dir, pdf_path.name, total_pages)
    print(f"[figure_extractor] Manifest: {manifest_path}")

    sheet_path = generate_contact_sheet(images_for_sheet, output_dir)
    if sheet_path:
        print(f"[figure_extractor] Contact sheet: {sheet_path}")

    zip_path = output_dir / "paper_figures.zip"
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=str(output_dir),
                        base_dir="figures")

    summary = {
        "total_captions": len(captions),
        "extracted": len(items),
        "figures": sum(1 for it in items if it["kind"] == "figure"),
        "tables": sum(1 for it in items if it["kind"] == "table"),
        "needs_review": sum(1 for it in items if it["needs_review"]),
        "output_dir": str(output_dir),
    }
    print(f"[figure_extractor] Done: {summary}")
    return summary
