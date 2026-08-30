# pragent/ai_denoise/post_clean.py
# 公众号长文（卡兹克文风）的 L1 确定性清理 + 质检 + HTML 渲染。
# 全部为纯函数，不做任何文件 IO（落盘由 app.py / run.py 负责）。

import re
from typing import Dict, Optional

# ------------------------------------------------------------------------------
# L1 确定性机械清理（兜底，不依赖 LLM 完美遵守 prompt）
# ------------------------------------------------------------------------------
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0"
    "\U00002600-\U000026FF\U00002B00-\U00002BFF\U00002300-\U000023FF"
    "\U0000FE00-\U0000FE0F\U0000200D\U000020E3]"
)
FORBIDDEN_WORDS = ["说白了", "本质上", "这意味着", "意味着什么", "换句话说",
                   "不可否认", "综上所述", "总的来说", "值得注意的是", "不难发现"]
REPLACE_WORDS = {"说白了": "坦率的讲", "本质上": "说到底", "这意味着": "所以",
                 "意味着什么": "那结果会怎样", "换句话说": "你想想看"}


def clean_khazix(t: str) -> str:
    """公众号长文 L1 确定性清理：去 [话题]/hashtag/小标题/emoji/禁词/全角标点。"""
    # 1. drop [话题] lines
    t = re.sub(r"(?m)^.*\[话题\].*$", "", t)
    # 2. per-line: strip markdown heading markers; drop bare hashtag lines
    out = []
    for ln in t.split("\n"):
        s = ln.strip()
        if re.match(r"^#{1,6}\s", s):
            ln = re.sub(r"^#{1,6}\s+", "", ln)        # heading -> plain line
        elif re.match(r"^[#＃]", s) and not re.search(r"[，。；、！？,]", s):
            continue                                    # bare hashtag line -> drop
        out.append(ln)
    t = "\n".join(out)
    # 3. forbidden punctuation (full-width colon / dashes / double quotes); keep half-width colon for arXiv/urls
    t = (t.replace("：", "，").replace("——", "，").replace("—", "，")
          .replace("“", "「").replace("”", "」").replace('"', ""))
    # 4. forbidden words
    for w in FORBIDDEN_WORDS:
        t = t.replace(w, REPLACE_WORDS.get(w, ""))
    # 5. emoji
    t = EMOJI_RE.sub("", t)
    # 6. tidy punctuation/whitespace artifacts left by deletions
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"，{2,}", "，", t)
    t = re.sub(r"([。！？])\s*，", r"\1", t)
    t = re.sub(r"(?m)^，+", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def l1_audit(t: str):
    """L1 审计，返回 (word_hits, punct_hits, emoji_hits, topic_hits, hashtag_lines)。

    各命中为 dict / int，均为 0/空 才算干净。
    """
    word_hits = {w: t.count(w) for w in FORBIDDEN_WORDS if t.count(w) > 0}
    punct_hits = {p: t.count(p) for p in ["：", "——", "“", "”"] if t.count(p) > 0}
    emoji_hits = len(EMOJI_RE.findall(t))
    topic_hits = t.count("[话题]")
    hashtag_lines = len([ln for ln in t.split("\n") if re.match(r"^\s*[#＃][\w\u4e00-\u9fa5]", ln)])
    return word_hits, punct_hits, emoji_hits, topic_hits, hashtag_lines


# ------------------------------------------------------------------------------
# 公众号 HTML 渲染（markdown -> 白底图文页）。图注 captions: img 文件名 -> 中文图注。
# ------------------------------------------------------------------------------
_IMG_RE = re.compile(r'^!\[([^\]]*)\]\(([^)]*)\)$')
_IMG_INLINE_RE = re.compile(r'!\[([^\]]*)\]\(([^)]*)\)')
_STRONG_RE = re.compile(r'\*\*(.+?)\*\*')

_ARTICLE_CSS = """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:#ffffff;color:#1a1a1a;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
  font-size:16px;line-height:1.85;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.page{max-width:680px;margin:0 auto;padding:48px 20px 88px}
h1{font-size:1.5rem;line-height:1.4;font-weight:700;margin:0 0 1.5em;letter-spacing:-.01em}
p{margin:0 0 1.15em}
strong{font-weight:700}
hr{border:0;border-top:1px solid #e6e6e6;margin:1.9em 0}
figure{margin:1.7em 0}
img{display:block;max-width:100%;height:auto;border:1px solid #ececec;border-radius:3px}
figcaption{margin-top:8px;font-size:13px;line-height:1.6;color:#9a9a9a;text-align:center}
@media(max-width:520px){.page{padding:32px 16px 64px}h1{font-size:1.3rem}}
"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(s: str) -> str:
    s = _esc(s)
    s = _STRONG_RE.sub(lambda m: "<strong>%s</strong>" % m.group(1), s)
    s = _IMG_INLINE_RE.sub(lambda m: '<img src="%s" alt="%s">' % (m.group(2), _esc(m.group(1))), s)
    return s


def md_to_html(md: str, captions: Optional[Dict[str, str]] = None) -> str:
    """把公众号长文 markdown 渲染成白底图文 HTML（纯函数）。

    captions 为 {img 文件名: 中文图注}，命中时给图片加 figcaption。
    首行（首个非空文本块）作为页面标题 <h1>。
    """
    captions = captions or {}
    lines = md.split("\n")

    blocks, cur = [], []
    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if line.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append(cur)

    body = []
    first_text = True
    n_fig = 0

    for blk in blocks:
        if len(blk) == 1 and blk[0].strip() == "---":
            body.append("<hr>")
            continue

        if all(_IMG_RE.match(l.strip()) for l in blk):
            for l in blk:
                m = _IMG_RE.match(l.strip())
                alt, src = m.group(1), m.group(2)
                base = src.strip().rsplit("/", 1)[-1]
                cap = captions.get(base, "")
                if cap:
                    body.append('<figure><img src="%s" alt="%s"><figcaption>%s</figcaption></figure>'
                                % (src, _esc(cap), _esc(cap)))
                else:
                    body.append('<figure><img src="%s" alt="%s"></figure>' % (src, _esc(alt)))
                n_fig += 1
            continue

        text_buf, hard_buf = [], []
        for line in blk:
            hard = line.endswith("  ") or line.endswith(" \t")
            text_buf.append(_inline(line.rstrip()))
            hard_buf.append(hard)
        joined = text_buf[0]
        for i in range(1, len(text_buf)):
            joined += ("<br>" if hard_buf[i - 1] else " ") + text_buf[i]

        if first_text:
            body.append("<h1>%s</h1>" % joined)
            first_text = False
        else:
            body.append("<p>%s</p>" % joined)

    title_text = ""
    m = re.search(r"<h1>(.*?)</h1>", body[0]) if body else None
    if m:
        title_text = re.sub(r"<[^>]+>", "", m.group(1))

    html = (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n<main class="page">\n%s\n</main>\n</body>\n</html>\n'
    ) % (_esc(title_text), _ARTICLE_CSS, "\n".join(body))

    return html
