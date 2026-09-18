from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import fitz


@dataclass
class PageEvidence:
    """Cached PDF-native evidence for one page.

    Text extraction is eager because typography and caption discovery scan the
    whole document. Drawings are lazy because only pages containing a Figure or
    Table caption need visual-geometry analysis.
    """

    text_dict: dict
    drawing_rects: Optional[List[fitz.Rect]] = None

    @classmethod
    def from_page(cls, page: fitz.Page) -> "PageEvidence":
        return cls(text_dict=page.get_text("dict"))

    def get_drawing_rects(self, page: fitz.Page) -> List[fitz.Rect]:
        if self.drawing_rects is None:
            # Downstream extraction only consumes drawing bounding boxes. Do
            # not retain the much heavier path/item dictionaries returned by
            # PyMuPDF once the rectangles have been projected out.
            self.drawing_rects = [
                fitz.Rect(drawing["rect"])
                for drawing in page.get_drawings()
            ]
        return self.drawing_rects


def build_document_evidence(doc: fitz.Document) -> Dict[int, PageEvidence]:
    """Read each page text layer once for reuse across the extraction pipeline."""

    return {
        page_num: PageEvidence.from_page(doc[page_num])
        for page_num in range(len(doc))
    }
