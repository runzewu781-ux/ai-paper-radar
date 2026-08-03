import base64
import re
from pathlib import Path
from typing import Dict, Optional, Any

_REF_RE = re.compile(r'(?:Figure|Fig\.?|Table)\s*[:：]?\s*(\d+)', re.IGNORECASE)

_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #fafaf8; color: #222;
       font-family: Georgia, 'Songti SC', 'SimSun', serif; line-height: 1.8; }
.page { max-width: 860px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
h1 { font-size: 1.7rem; line-height: 1.4; border-bottom: 2px solid #333;
     padding-bottom: .5rem; margin: 0 0 1.6rem; }
p { margin: 0 0 1.1rem; font-size: 1.02rem; text-align: justify; }
hr { border: none; border-top: 1px solid #ddd; margin: 2rem 0; }
figure.viz { margin: 1.6rem 0; background: #fff; border: 1px solid #e3e1db;
             border-radius: 6px; padding: .8rem; }
figure.viz img { display: block; width: 100%; height: auto; border-radius: 4px; }
figure.viz iframe { display: block; width: 100%; border: none; background: #F0EFEB;
                    border-radius: 4px; }
figure.viz figcaption { font-size: .82rem; color: #666; font-style: italic;
                        margin-top: .5rem; font-family: -apple-system, sans-serif; }
.badge { display: inline-block; font-size: .7rem; font-family: -apple-system, sans-serif;
         color: #fff; background: #8b7355; border-radius: 3px; padding: 1px 6px;
         margin-right: 6px; vertical-align: middle; }
"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _esc_attr(s: str) -> str:
    return (_esc(s).replace('"', "&quot;").replace("'", "&#39;"))


def _img_b64(path: Path) -> str:
    data = path.read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode()


def _find_refs(text: str) -> set:
    return {int(m) for m in _REF_RE.findall(text)}


def _visual_figure(number: int, kind: str, manifest_item: Optional[Dict],
                   reconstructed: Dict[str, Dict], base_dir: Path) -> Optional[str]:
    recon = reconstructed.get("%s_%d" % (kind, number))
    caption = manifest_item.get("caption", "") if manifest_item else ""

    if recon and recon.get("type") == "lieflat":
        html_path = Path(recon["html_path"])
        if html_path.exists():
            inner = html_path.read_text(encoding="utf-8")
            badge = '<span class="badge">数据图 · lieflat 重构</span>'
            return ('<figure class="viz"><iframe srcdoc="%s" height="%s"></iframe>'
                    '<figcaption>%s%s</figcaption></figure>'
                    % (_esc_attr(inner), recon.get("height", 560), badge, _esc(caption)))

    img_path = None
    badge = ""
    if recon and recon.get("type") == "image":
        p = Path(recon["path"])
        if p.exists():
            img_path = p
            badge = '<span class="badge">流程图 · 结构重绘</span>'
    if img_path is None and manifest_item:
        p = base_dir / manifest_item["file"]
        if p.exists():
            img_path = p
            badge = '<span class="badge">原图</span>'

    if img_path is None:
        return None
    return ('<figure class="viz"><img src="%s" alt="%s">'
            '<figcaption>%s%s</figcaption></figure>'
            % (_img_b64(img_path), _esc(caption), badge, _esc(caption)))


def render_final_html(
    post_md: str,
    manifest: Dict[str, Any],
    base_dir: str,
    out_path: str,
    reconstructed: Optional[Dict[int, Dict]] = None,
    title: Optional[str] = None,
) -> str:
    base_dir = Path(base_dir)
    reconstructed = reconstructed or {}

    by_key = {}
    for item in manifest.get("items", []):
        by_key[(item["kind"], int(item["number"]))] = item

    lines = [l.rstrip() for l in post_md.split("\n")]
    blocks, cur = [], []
    for l in lines:
        if l.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(l)
    if cur:
        blocks.append(cur)

    seen = set()
    body = []
    first = True
    for blk in blocks:
        text = " ".join(blk)
        if first:
            body.append("<h1>%s</h1>" % _esc(title or text))
            first = False
        else:
            body.append("<p>%s</p>" % _esc(text))

        refs = _find_refs(text)
        for num in sorted(refs):
            kind = "table" if re.search(r'Table\s*[:：]?\s*%d\b' % num, text, re.I) else "figure"
            key = (kind, num)
            if key in seen:
                continue
            seen.add(key)
            item = by_key.get((kind, num)) or by_key.get(("figure", num)) or by_key.get(("table", num))
            vis = _visual_figure(num, kind, item, reconstructed, base_dir)
            if vis:
                body.append(vis)

    html = ('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            '<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n<main class="page">\n%s\n'
            '</main>\n</body>\n</html>\n'
            % (_esc(title or "科普文章"), _CSS, "\n".join(body)))

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out)
