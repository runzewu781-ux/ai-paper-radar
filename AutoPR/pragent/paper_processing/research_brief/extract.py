from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Optional

import fitz

from ..figures.page_evidence import PageEvidence, build_document_evidence
from ..figures.typography import TypographyProfile, estimate_document_typography
from .models import (
    BoundingBox,
    DocumentMetadata,
    EvidenceItem,
    EvidenceLocation,
    ResearchBrief,
    SectionEvidence,
    VisualEvidence,
)


_SECTION_NAME_RE = re.compile(
    r"^(?:\s*(?:\d+(?:\.\d+)*|[IVXLC]+|[A-Z])\.?\s+)?"
    r"(abstract|introduction|background|related\s+work|preliminaries|method|methods|methodology|"
    r"approach|model|experiments?|experimental\s+setup|evaluation|results?|discussion|analysis|"
    r"limitations?|conclusion|conclusions|acknowledg(?:e)?ments?|references|appendix)\b",
    re.IGNORECASE,
)
_CAPTION_RE = re.compile(r"^(figure|fig\.?|table)\s+(\d+)\b", re.IGNORECASE)
_NUMBERING_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[IVXLC]+|[A-Z])\.?\s+", re.IGNORECASE)
_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*|[IVXLC]+|[A-Z])\.?\s+\S+",
    re.IGNORECASE,
)
_LIST_RE = re.compile(r"^(?:[-•·‣▪]|\(?\d+[.)]|\(?[a-zA-Z][.)])\s+")
_FORMULA_RE = re.compile(r"(?:[=<>±≈∑∏√∞∫]|\\(?:alpha|beta|gamma|sum|frac)|\b(?:argmax|argmin)\b)")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_hash(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _bbox(rect: fitz.Rect) -> BoundingBox:
    return BoundingBox(
        left=float(rect.x0),
        top=float(rect.y0),
        right=float(rect.x1),
        bottom=float(rect.y1),
    )


def _block_text(block: dict) -> str:
    lines: list[str] = []
    for line in block.get("lines", []):
        text = " ".join(
            span.get("text", "")
            for span in line.get("spans", [])
            if span.get("text", "").strip()
        ).strip()
        if text:
            lines.append(text)
    return "\n".join(lines).strip()


def _block_style(block: dict) -> tuple[float, bool]:
    weighted: list[tuple[int, float, bool]] = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = span.get("text", "").strip()
            if not text:
                continue
            raw_font = str(span.get("font", "")).lower()
            flags = int(span.get("flags", 0) or 0)
            bold = bool(flags & 16) or any(
                token in raw_font for token in ("bold", "semibold", "-bd", "_bd", "demi")
            )
            weighted.append((len(text), float(span.get("size", 0.0) or 0.0), bold))
    if not weighted:
        return 0.0, False
    _, size, bold = max(weighted, key=lambda item: item[0])
    return size, bold


def _looks_like_header_footer(rect: fitz.Rect, page: fitz.Page) -> bool:
    height = max(page.mediabox.height, 1.0)
    return rect.y1 <= height * 0.035 or rect.y0 >= height * 0.965


def _looks_like_page_number(text: str, rect: fitz.Rect, page: fitz.Page) -> bool:
    compact = "".join(text.split())
    if not re.fullmatch(r"(?:\d{1,4}|[ivxlc]{1,8})", compact, re.IGNORECASE):
        return False
    height = max(page.mediabox.height, 1.0)
    return rect.y0 >= height * 0.90 or rect.y1 <= height * 0.08


def _normalize_heading(text: str) -> str:
    text = " ".join(text.split())
    text = _NUMBERING_RE.sub("", text)
    return text.strip(" .:-").lower()


def _looks_like_section_heading(
    text: str,
    size: float,
    bold: bool,
    profile: TypographyProfile,
) -> bool:
    compact = " ".join(text.split())
    if not compact or len(compact) > 140 or "\n" in text and len(text.splitlines()) > 2:
        return False
    visually_emphasized = bold or size >= profile.body_size * 1.12
    if _SECTION_NAME_RE.match(compact):
        return visually_emphasized
    # Be deliberately conservative here. Academic figures and tables contain
    # many short bold labels, so generic "short + bold" is not enough to call
    # something a document section. Outside the canonical section-name list,
    # require an explicit section number / appendix letter as well. Numbered
    # paper headings may legitimately be phrased as full questions, so terminal
    # punctuation is not a reason to reject them.
    return (
        visually_emphasized
        and bool(_NUMBERED_HEADING_RE.match(compact))
        and len(compact.split()) <= 18
    )


def _mostly_inside_visual(
    rect: fitz.Rect,
    visual_rects: Iterable[fitz.Rect],
    threshold: float = 0.50,
) -> bool:
    area = max(rect.width * rect.height, 1.0)
    for visual in visual_rects:
        inter = rect & visual
        if inter.is_empty:
            continue
        if (inter.width * inter.height) / area >= threshold:
            return True
    return False


def _title_candidate(
    page: fitz.Page,
    evidence: PageEvidence,
    profile: TypographyProfile,
) -> Optional[tuple[int, dict, str]]:
    candidates: list[tuple[float, int, dict, str]] = []
    for block_index, block in enumerate(evidence.text_dict.get("blocks", [])):
        if block.get("type") != 0:
            continue
        text = _block_text(block)
        if not text or len(text) > 420 or _CAPTION_RE.match(text):
            continue
        rect = fitz.Rect(block["bbox"])
        if _looks_like_header_footer(rect, page):
            continue
        # arXiv stamps and publisher sidebars are commonly rotated vertical
        # text with a deceptively large font size. A paper title should occupy
        # a horizontal reading band, not a tall narrow strip.
        if rect.height >= rect.width:
            continue
        if rect.y0 > page.mediabox.height * 0.32:
            continue
        size, _ = _block_style(block)
        if size < profile.body_size * 1.25:
            continue
        candidates.append((size, block_index, block, text))
    if not candidates:
        return None
    _, block_index, block, text = max(candidates, key=lambda item: (item[0], -item[2]["bbox"][1]))
    return block_index, block, text


def _source_type(
    text: str,
    is_heading: bool,
    is_title: bool,
    inside_visual: bool = False,
) -> str:
    if is_title:
        return "title"
    if is_heading:
        return "section_heading"
    if inside_visual:
        return "visual_text"
    match = _CAPTION_RE.match(" ".join(text.split()))
    if match:
        return "table_caption" if match.group(1).lower() == "table" else "figure_caption"
    if _LIST_RE.match(text):
        return "list"
    if _FORMULA_RE.search(text) and len(text) <= 180:
        return "formula"
    if len(text) >= 40:
        return "paragraph"
    return "other_text"


def _extract_text_ledger(
    doc: fitz.Document,
    page_evidence: dict[int, PageEvidence],
    profile: TypographyProfile,
    visual_regions: Optional[dict[int, list[fitz.Rect]]] = None,
) -> tuple[list[EvidenceItem], list[SectionEvidence], Optional[str]]:
    evidence_items: list[EvidenceItem] = []
    sections: list[SectionEvidence] = []
    current_section: Optional[SectionEvidence] = None

    title_info = _title_candidate(doc[0], page_evidence[0], profile)
    title_key = title_info[0] if title_info is not None else None
    title_text = title_info[2] if title_info is not None else None

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        blocks = page_evidence[page_index].text_dict.get("blocks", [])

        for block_index, block in enumerate(blocks):
            if block.get("type") != 0:
                continue
            text = _block_text(block)
            if not text:
                continue
            rect = fitz.Rect(block["bbox"])
            if _looks_like_header_footer(rect, page):
                continue
            if _looks_like_page_number(text, rect, page):
                continue

            size, bold = _block_style(block)
            is_title = page_index == 0 and title_key == block_index
            inside_visual = _mostly_inside_visual(
                rect,
                (visual_regions or {}).get(page_index, []),
            )
            is_heading = (
                not is_title
                and not inside_visual
                and _looks_like_section_heading(text, size, bold, profile)
            )
            item_id = f"text:p{page_index:04d}:b{block_index:04d}"

            if is_heading:
                section_id = f"section:{len(sections) + 1:03d}"
            else:
                section_id = current_section.id if current_section is not None else None

            item = EvidenceItem(
                id=item_id,
                source_type=_source_type(text, is_heading, is_title, inside_visual),
                text=text,
                text_hash=_text_hash(text),
                section_id=section_id,
                location=EvidenceLocation(
                    page_index=page_index,
                    bbox=_bbox(rect),
                    page_width=page_width,
                    page_height=page_height,
                    block_index=block_index,
                ),
            )
            evidence_items.append(item)

            if is_heading:
                current_section = SectionEvidence(
                    id=section_id,
                    heading=" ".join(text.split()),
                    normalized_heading=_normalize_heading(text),
                    heading_evidence_id=item_id,
                    evidence_ids=[item_id],
                )
                sections.append(current_section)
            elif current_section is not None:
                current_section.evidence_ids.append(item_id)

    return evidence_items, sections, title_text


def _load_visual_evidence(
    manifest_path: Path,
    doc: fitz.Document,
) -> tuple[list[VisualEvidence], list[VisualEvidence]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    items: Iterable[dict] = payload.get("items", []) if isinstance(payload, dict) else payload
    figures: list[VisualEvidence] = []
    tables: list[VisualEvidence] = []

    for item in items:
        kind = str(item.get("kind", "")).lower()
        if kind not in {"figure", "table"}:
            continue
        page_index = int(item["page"])
        if page_index < 0 or page_index >= len(doc):
            raise ValueError(f"manifest visual points outside PDF: {kind} {item.get('number')} page={page_index}")
        coords = item.get("bbox") or []
        if len(coords) != 4:
            raise ValueError(f"manifest visual has invalid bbox: {kind} {item.get('number')}")
        page = doc[page_index]
        visual = VisualEvidence(
            id=f"visual:{kind}:{int(item['number'])}:p{page_index:04d}",
            kind=kind,
            number=int(item["number"]),
            page_index=page_index,
            page_width=float(page.mediabox.width),
            page_height=float(page.mediabox.height),
            caption=str(item.get("caption", "")),
            bbox=BoundingBox(
                left=float(coords[0]),
                top=float(coords[1]),
                right=float(coords[2]),
                bottom=float(coords[3]),
            ),
            file=item.get("file"),
            confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
            needs_review=bool(item.get("needs_review", False)),
            issues=[str(value) for value in item.get("issues", [])],
        )
        (figures if kind == "figure" else tables).append(visual)

    return figures, tables


def build_research_brief(
    pdf_path: str | Path,
    manifest_path: Optional[str | Path] = None,
) -> ResearchBrief:
    """Build a deterministic provenance sidecar without invoking an LLM.

    Version 0.1 establishes the source ledger, document sections, and links to
    the existing Figure/Table manifest. Semantic claims remain empty until a
    later bounded extraction stage can attach them to these stable evidence IDs.
    """

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    doc = fitz.open(str(pdf_path))
    try:
        if len(doc) == 0:
            raise ValueError("PDF has no pages")
        figures: list[VisualEvidence] = []
        tables: list[VisualEvidence] = []
        warnings: list[str] = []
        if manifest_path is not None:
            manifest = Path(manifest_path)
            if not manifest.exists():
                raise FileNotFoundError(manifest)
            figures, tables = _load_visual_evidence(manifest, doc)
        else:
            warnings.append("figure_table_manifest_not_supplied")

        page_evidence = build_document_evidence(doc)
        profile = estimate_document_typography(doc, page_evidence)
        visual_regions: dict[int, list[fitz.Rect]] = {}
        for visual in figures + tables:
            visual_regions.setdefault(visual.page_index, []).append(
                fitz.Rect(
                    visual.bbox.left,
                    visual.bbox.top,
                    visual.bbox.right,
                    visual.bbox.bottom,
                )
            )
        evidence, sections, title = _extract_text_ledger(
            doc,
            page_evidence,
            profile,
            visual_regions=visual_regions,
        )

        if title is None:
            warnings.append("title_not_confidently_detected")
        if not sections:
            warnings.append("section_headings_not_confidently_detected")
        if any(item.needs_review for item in figures + tables):
            warnings.append("visual_evidence_contains_review_items")

        return ResearchBrief(
            document=DocumentMetadata(
                source_pdf=pdf_path.name,
                pdf_sha256=_sha256_file(pdf_path),
                page_count=len(doc),
                title=" ".join(title.split()) if title else None,
            ),
            evidence=evidence,
            sections=sections,
            figures=figures,
            tables=tables,
            warnings=warnings,
        )
    finally:
        doc.close()


def write_research_brief(brief: ResearchBrief, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        brief.model_dump_json(indent=2, exclude_none=True) + "\n",
        encoding="utf-8",
    )
    return output_path
