import re
from dataclasses import dataclass, field
from typing import List, Optional
import fitz


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
    r'^(Figure|Fig\.?)\s+(\d+)\s*[.:：]', re.IGNORECASE
)
_TAB_RE = re.compile(
    r'^(Table)\s+(\d+)\s*[.:：]', re.IGNORECASE
)
_SUB_RE = re.compile(r'\((\w)\)', re.IGNORECASE)


def _block_text(block: dict) -> str:
    parts = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            parts.append(span.get("text", ""))
    return " ".join(parts).strip()


def find_captions(doc: fitz.Document) -> List[Caption]:
    captions: List[Caption] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block.get("type") != 0:
                continue
            text = _block_text(block)
            if not text:
                continue

            bbox = fitz.Rect(block["bbox"])

            m_fig = _FIG_RE.match(text)
            m_tab = _TAB_RE.match(text)

            if m_fig:
                number = int(m_fig.group(2))
                subs = _SUB_RE.findall(text)
                captions.append(Caption(
                    kind="figure",
                    number=number,
                    label=f"Figure {number}",
                    text=text,
                    bbox=bbox,
                    page_num=page_num,
                    sub_labels=subs,
                ))
            elif m_tab:
                number = int(m_tab.group(2))
                captions.append(Caption(
                    kind="table",
                    number=number,
                    label=f"Table {number}",
                    text=text,
                    bbox=bbox,
                    page_num=page_num,
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
