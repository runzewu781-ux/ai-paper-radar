import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image

from .reconstruct import extract_chart_data


_ROUTE_ID_RE = re.compile(r'data-chart-id="([A-Z0-9]+)"')
_ROUTE_RELATION_RE = re.compile(r'data-chart-relation="([a-z_]+)"')


def get_lieflat_dir() -> Path:
    """Resolve the sibling Lieflat repo, with an environment override."""
    configured = os.getenv("LIEFLAT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    workspace = Path(__file__).resolve().parents[5]
    return workspace / "lieflat-charts"


def clean_rows(raw):
    """Validate extracted rows without dropping, sorting, truncating, or scaling them."""
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    out = []
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            return None
        try:
            values = [float(value) for value in row[1:]]
        except (TypeError, ValueError):
            return None
        out.append([str(row[0]), *values])
    return out


def build_config(title, rows, semantics, outfile):
    chart = {
        "title": title,
        "meta": title[:40],
        "src": "AutoPR · deterministic Lieflat route · reconstructed from paper figure",
        "data": rows,
        "semantics": semantics if isinstance(semantics, dict) else {},
    }
    return {
        "skin": "mono",
        "title": title,
        "outfile": str(outfile),
        "charts": [chart],
    }


def _extract_route(html_path: Path):
    source = html_path.read_text(encoding="utf-8")
    id_match = _ROUTE_ID_RE.search(source)
    relation_match = _ROUTE_RELATION_RE.search(source)
    return (
        id_match.group(1) if id_match else "unknown",
        relation_match.group(1) if relation_match else "unknown",
    )


def render_lieflat_payload(data, out_html, lieflat_dir=None):
    """Render vision-extracted data through Lieflat's deterministic router."""
    if not data or not data.get("data_zh"):
        return None, "no data extracted", {}

    rows = clean_rows(data.get("data_zh"))
    if not rows:
        return None, "invalid or incomplete data rows; use original paper figure", {}

    out_html = Path(out_html).resolve()
    title_zh = data.get("title_zh", "") or "论文数据重构"
    semantics = data.get("semantics") if isinstance(data.get("semantics"), dict) else {}
    cfg = build_config(title_zh, rows, semantics, out_html)
    cfg_path = Path(str(out_html) + ".json")
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    root = Path(lieflat_dir).resolve() if lieflat_dir else get_lieflat_dir().resolve()
    build_script = root / "scripts" / "build.mjs"
    if not build_script.exists():
        return None, "lieflat build script missing: %s" % build_script, {}

    node = shutil.which("node")
    if not node:
        return None, "node executable not found", {}

    if out_html.exists():
        out_html.unlink()

    try:
        result = subprocess.run(
            [node, str(build_script), str(cfg_path)],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "lieflat build failed: %s" % exc, {}

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown build error").strip()
        return None, detail[:600], {}
    if not out_html.exists():
        return None, "lieflat reported success but outfile was not created", {}

    chart_id, relation = _extract_route(out_html)
    meta = {
        "explanation_zh": data.get("explanation_zh", ""),
        "chart_id": chart_id,
        "relation": relation,
    }
    return (
        str(out_html),
        "ok routed=%s relation=%s cats=%d" % (chart_id, relation, len(rows)),
        meta,
    )


async def rebuild_chart(image_path, out_html, api_key, api_base, model="qwen3.8-max-preview"):
    with Image.open(str(image_path)) as img:
        data = await extract_chart_data(img, api_key, api_base, model)
    return render_lieflat_payload(data, out_html)


def main():
    if len(sys.argv) < 3:
        print("usage: python -m pragent.backend.figure_extractor.chart_rebuild <image> <out.html>")
        return
    key = os.getenv("BAILIAN_KEY", "")
    base = os.getenv(
        "BAILIAN_BASE",
        "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )
    out, msg, _meta = asyncio.run(rebuild_chart(sys.argv[1], sys.argv[2], key, base))
    print(msg, "->", out)


if __name__ == "__main__":
    main()
