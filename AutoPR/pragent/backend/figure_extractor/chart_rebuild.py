import asyncio
import json
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image
from .reconstruct import extract_chart_data, LIEFLAT_SNIPPET_IDS

LIEFLAT_DIR = Path(r"C:\Users\Administrator\Desktop\lieflat-charts-main")

CAPACITY = {
    "F1": {"max_units": 40, "max_cats": 6},
    "F5": {"max_units": 40, "max_cats": 8},
    "F2": {"max_units": None, "max_cats": 30},
    "F4": {"max_units": None, "max_cats": 6},
    "F12": {"max_units": 40, "max_cats": 6},
    "L11": {"max_units": None, "max_cats": 8},
    "L13": {"max_units": None, "max_cats": 6},
    "L14": {"max_units": 100, "max_cats": 6},
    "L15": {"max_units": 100, "max_cats": 8},
}
UNIT_CHARTS = {"F1", "F5", "F12"}


import re


def clean_rows(raw):
    out = []
    for row in (raw or []):
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            try:
                out.append([str(row[0]), float(row[1])])
            except Exception:
                continue
    return out


def is_series(labels):
    if not labels:
        return False
    pat = re.compile(r'(19|20)\d{2}$')
    num = sum(1 for l in labels if pat.search(l) or l.replace('.', '', 1).isdigit())
    return num > len(labels) * 0.6


def adapt(chart_id, rows):
    rows = clean_rows(rows)
    if not rows:
        return [], 1, chart_id
    labels = [r[0] for r in rows]

    if is_series(labels):
        rows = rows[:30]
        return rows, 1, "F2"

    rows.sort(key=lambda r: -r[1])
    rows = rows[:8]
    chart_id = "F5"
    max_v = max(r[1] for r in rows)
    unit = 1
    if max_v > CAPACITY["F5"]["max_units"]:
        unit = math.ceil(max_v / CAPACITY["F5"]["max_units"])
        rows = [[name, max(1, round(v / unit))] for name, v in rows]
    return rows, unit, chart_id


def build_config(chart_id, title, meta, rows, unit, outfile):
    charts = [{
        "id": chart_id,
        "title": title,
        "meta": meta + (" · 1 tick=%s" % unit if unit > 1 else ""),
        "src": "%s · reconstructed" % chart_id,
        "data": rows,
    }]
    return {"skin": "mono", "title": title, "outfile": str(outfile), "charts": charts}


async def rebuild_chart(image_path, out_html, api_key, api_base, model="qwen3.8-max-preview"):
    img = Image.open(str(image_path))
    data = await extract_chart_data(img, api_key, api_base, model)
    if not data or not data.get("data"):
        return None, "no data extracted"
    chart_id = data.get("chart_id")
    if chart_id not in LIEFLAT_SNIPPET_IDS:
        chart_id = "F5"
    rows, unit, chart_id = adapt(chart_id, data.get("data"))
    if not rows:
        return None, "empty after adapt"
    cfg = build_config(chart_id, data.get("title", ""), data.get("title", "")[:40],
                       rows, unit, out_html)
    cfg_path = Path(str(out_html) + ".json")
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run(["node", "scripts/build.mjs", str(cfg_path)],
                       cwd=str(LIEFLAT_DIR), capture_output=True, text=True)
    if Path(out_html).exists():
        return str(out_html), "ok %s cats=%d unit=%d" % (chart_id, len(rows), unit)
    return None, r.stderr[:300]


def main():
    import os
    if len(sys.argv) < 3:
        print("usage: python -m pragent.backend.figure_extractor.chart_rebuild <image> <out.html>")
        return
    key = os.getenv("BAILIAN_KEY", "")
    base = os.getenv("BAILIAN_BASE", "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    out, msg = asyncio.run(rebuild_chart(sys.argv[1], sys.argv[2], key, base))
    print(msg, "->", out)


if __name__ == "__main__":
    main()
