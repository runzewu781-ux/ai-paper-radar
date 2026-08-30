import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any
from PIL import Image, ImageDraw, ImageFont


def write_manifest(items: List[Dict[str, Any]], output_dir: Path, pdf_name: str, total_pages: int):
    manifest = {
        "pdf": pdf_name,
        "pages": total_pages,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "total_items": len(items),
        "items": items,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest_path


def generate_contact_sheet(items: List[Dict[str, Any]], output_dir: Path,
                           thumb_width: int = 300, cols: int = 4):
    valid_items = [it for it in items if it.get("_img") is not None]
    if not valid_items:
        return None

    thumbs = []
    for it in valid_items:
        img = it["_img"]
        ratio = thumb_width / img.width
        thumb_h = int(img.height * ratio)
        thumb = img.resize((thumb_width, thumb_h), Image.LANCZOS)
        thumbs.append((thumb, it))

    max_thumb_h = max(t[0].height for t in thumbs)
    cell_h = max_thumb_h + 50
    rows = math.ceil(len(thumbs) / cols)
    sheet_w = cols * (thumb_width + 20) + 20
    sheet_h = rows * (cell_h + 10) + 10

    sheet = Image.new("RGB", (sheet_w, sheet_h), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)

    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except (OSError, IOError):
        font = ImageFont.load_default()

    for idx, (thumb, it) in enumerate(thumbs):
        col = idx % cols
        row = idx // cols
        x = 20 + col * (thumb_width + 20)
        y = 10 + row * (cell_h + 10)

        sheet.paste(thumb, (x, y))

        label = f"{it['kind']} {it['number']} | p{it['page']+1} | conf={it['confidence']:.1f}"
        if it.get("needs_review"):
            label += " [REVIEW]"
        draw.text((x, y + thumb.height + 5), label, fill=(0, 0, 0), font=font)

    sheet_path = output_dir / "contact_sheet.png"
    sheet.save(str(sheet_path), "PNG")
    return sheet_path
