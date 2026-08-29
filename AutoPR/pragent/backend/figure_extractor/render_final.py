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
figure.viz .explain { font-size: .9rem; color: #3a3a35; background: #f4f2ec;
                      border-left: 3px solid #8b7355; padding: .55rem .85rem;
                      margin: .6rem 0 0; border-radius: 3px; line-height: 1.7;
                      font-family: -apple-system, sans-serif; }
.viz-title { display: flex; align-items: center; gap: .45rem; margin: .1rem 0 .65rem;
             color: #4a4640; font: 600 .83rem/1.4 -apple-system, sans-serif; }
.source-details { margin-top: .7rem; border-top: 1px dashed #d7d2c8; padding-top: .55rem;
                  font-family: -apple-system, sans-serif; }
.source-details summary { cursor: pointer; color: #777066; font-size: .8rem; }
.source-details img { margin-top: .65rem; }
.source-caption { margin-top: .45rem; color: #817a70; font-size: .72rem; line-height: 1.55; }
.badge { display: inline-block; font-size: .7rem; font-family: -apple-system, sans-serif;
         color: #fff; background: #8b7355; border-radius: 3px; padding: 1px 6px;
         margin-right: 6px; vertical-align: middle; }
"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _esc_attr(s: str) -> str:
    return (_esc(s).replace('"', "&quot;").replace("'", "&#39;"))


def _file_data_uri(path: Path) -> str:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    mime = {
        ".svg": "image/svg+xml",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "image/png")
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def _find_refs(text: str) -> set:
    return {int(m) for m in _REF_RE.findall(text)}


def _find_refs_pairs(text: str) -> list:
    out = []
    for m in re.finditer(r'(Figure|Fig\.?|Table)\s*[:：]?\s*(\d+)', text, re.IGNORECASE):
        kind = "table" if m.group(1).lower() == "table" else "figure"
        out.append((kind, int(m.group(2))))
    return out


def _visual_figure(number: int, kind: str, manifest_item: Optional[Dict],
                   reconstructed: Dict[str, Dict], base_dir: Path) -> Optional[str]:
    recon = reconstructed.get("%s_%d" % (kind, number)) or {}
    caption = manifest_item.get("caption", "") if manifest_item else ""
    explain = recon.get("explanation_zh", "") or ""
    xplain_html = ('<p class="explain">%s</p>' % _esc(explain)) if explain else ""
    label = ("Table" if kind == "table" else "Figure") + " %d" % number
    source_details = (
        '<details class="source-details"><summary>查看 %s 的论文英文题注</summary>'
        '<div class="source-caption">%s</div></details>' % (_esc(label), _esc(caption))
    ) if caption else ""

    if recon.get("type") == "lieflat":
        html_path = Path(recon["html_path"])
        if html_path.exists():
            inner = html_path.read_text(encoding="utf-8")
            badge = '<span class="badge">数据图 · 中文重构</span>'
            return ('<figure class="viz"><div class="viz-title">%s%s</div>'
                    '<iframe srcdoc="%s" height="%s"></iframe>%s%s</figure>'
                    % (badge, _esc(label), _esc_attr(inner), recon.get("height", 560),
                       xplain_html, source_details))

    if recon.get("type") == "skill_html":
        html_path = Path(recon["html_path"])
        if html_path.exists():
            inner = html_path.read_text(encoding="utf-8")
            badge_label = recon.get("badge", "Lieflat Skill · 原版模板")
            badge = '<span class="badge">%s</span>' % _esc(badge_label)
            return ('<figure class="viz"><div class="viz-title">%s%s</div>'
                    '<iframe srcdoc="%s" height="%s"></iframe>%s%s</figure>'
                    % (badge, _esc(label), _esc_attr(inner), recon.get("height", 560),
                       xplain_html, source_details))

    if recon.get("type") == "structure_svg":
        svg_path = Path(recon.get("path", ""))
        if svg_path.exists():
            badge = '<span class="badge">流程图 · 中文重绘</span>'
            return ('<figure class="viz"><div class="viz-title">%s%s</div>'
                    '<img src="%s" alt="%s">%s%s</figure>'
                    % (badge, _esc(label), _file_data_uri(svg_path), _esc(label),
                       xplain_html, source_details))

    img_path = None
    badge = ""
    if recon.get("type") == "image":
        p = Path(recon["path"])
        if p.exists():
            img_path = p
            badge_label = recon.get("badge", "流程图 · 结构重绘")
            badge = '<span class="badge">%s</span>' % _esc(badge_label)
    if img_path is None and manifest_item:
        p = base_dir / manifest_item["file"]
        if p.exists():
            img_path = p
            badge = '<span class="badge">原图</span>'

    if img_path is None:
        return None
    if recon.get("original_as_reference") and explain:
        return ('<figure class="viz"><div class="viz-title">%s%s · 中文解读</div>%s'
                '<details class="source-details"><summary>查看 %s 论文原图（英文，供核对）</summary>'
                '<img src="%s" alt="%s"><div class="source-caption">%s</div></details></figure>'
                % (badge, _esc(label), xplain_html, _esc(label), _file_data_uri(img_path),
                   _esc(label), _esc(caption)))
    return ('<figure class="viz"><div class="viz-title">%s%s</div>'
            '<img src="%s" alt="%s">%s%s</figure>'
            % (badge, _esc(label), _file_data_uri(img_path), _esc(label), xplain_html, source_details))


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
    start_index = 0
    if title:
        # A caller-supplied title is metadata, not a signal to discard the
        # first content paragraph. The old implementation always consumed the
        # first block as <h1>, which silently dropped real article content.
        body.append("<h1>%s</h1>" % _esc(title))
        if blocks:
            first_text = " ".join(blocks[0]).strip()
            if first_text == title.strip():
                # Backward compatibility for callers that derive the title
                # from the first block: render it once as the heading, not
                # again as the opening paragraph.
                start_index = 1
    elif blocks:
        body.append("<h1>%s</h1>" % _esc(" ".join(blocks[0])))
        start_index = 1
    else:
        body.append("<h1>%s</h1>" % _esc("科普文章"))

    for blk in blocks[start_index:]:
        text = " ".join(blk)
        body.append("<p>%s</p>" % _esc(text))

        for kind, num in _find_refs_pairs(text):
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
