"""端到端科普文章生成编排器。

把 AutoPR 新图表工作流串成一条可复现的命令：
  PDF -> 文本提取 -> 图表提取+分类 -> 公众号草稿 -> 织入引用 ->
  按类型重构（数据图 lieflat / 流程图结构重绘）-> 排版输出 final.html

说明：
- 数据图（data_chart/table）自动走 lieflat（qwen 提取中文数据 + build.mjs 生成 HTML）。
- 流程图（flow_diagram/other）的结构理解+中文解释自动生成；重绘图由调用方通过
  `flow_redraws` 提供（Atlas 由 agent 生成），未提供则回退原图但保留中文注解。
"""
import asyncio
import json
import re
from pathlib import Path
from typing import Dict, Optional

from . import run_extraction
from . import reconstruct as R
from .chart_rebuild import rebuild_chart
from .render_final import render_final_html

try:
    from ..agents import setup_client, call_text_llm_api
    from ..blog_pipeline import generate_text_blog
    from ..prompts_wechat import WECHAT_DRAFT_PROMPT_CHINESE
    from ..text_pipeline import pipeline as run_text_extraction
except ImportError:  # 相对导入兜底
    from pragent.backend.agents import setup_client, call_text_llm_api
    from pragent.backend.blog_pipeline import generate_text_blog
    from pragent.backend.prompts_wechat import WECHAT_DRAFT_PROMPT_CHINESE
    from pragent.backend.text_pipeline import pipeline as run_text_extraction


async def _weave_citations(draft: str, manifest: dict, api_key: str, api_base: str, model: str) -> str:
    avail = [{'n': it['number'], 'kind': it['kind'], 'type': it['visual_type'],
              'cap': it['caption'][:50]} for it in manifest.get('items', [])]
    sys = ('你是编辑。把草稿改写为终稿：保持文风，在恰当位置自然插入对图表的显式引用，'
           '格式严格为 Figure N 或 Table N。只能引用下列存在的编号。直接输出终稿全文。')
    user = '可用图表：' + json.dumps(avail, ensure_ascii=False) + '\n\n草稿：\n' + draft
    async with setup_client(api_key, api_base) as c:
        return await call_text_llm_api(c, sys, user, model)


async def generate_article(
    pdf_path: str,
    output_dir: str,
    api_key: str,
    api_base: str,
    model: str = "qwen3.8-max-preview",
    dpi: int = 200,
    flow_redraws: Optional[Dict[str, str]] = None,
    draft_prompt_override: Optional[str] = None,
    style_guide: Optional[str] = None,
    skip_classify: bool = False,
) -> Dict[str, str]:
    """运行完整管线，返回各阶段产物路径。"""
    pdf_path = Path(pdf_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    flow_redraws = flow_redraws or {}

    # --- Stage 1: 文本提取 ---
    txt = out / "paper.txt"
    await run_text_extraction(str(pdf_path), str(txt))
    print("[stage1] text ->", txt)

    # --- Stage 2: 图表提取 + 分类 ---
    figs = out / "figs"
    summary = await run_extraction(str(pdf_path), str(figs), dpi=dpi,
                                   api_key=api_key, api_base=api_base, model=model,
                                   skip_classify=skip_classify)
    print("[stage2] extraction ->", summary)
    manifest = R.load_manifest(str(figs / "manifest.json"))

    # --- Stage 3: 公众号草稿 ---
    base_prompt = draft_prompt_override or WECHAT_DRAFT_PROMPT_CHINESE
    if style_guide:
        base_prompt = base_prompt + "\n\n===== 强制遵循的文风指南 =====\n" + style_guide
    draft, _src = await generate_text_blog(
        txt_path=str(txt), api_key=api_key, text_api_base=api_base, model=model,
        language='zh', disable_qwen_thinking=False,
        ablation_mode='no_hierarchical_summary',
        draft_prompt_override=base_prompt,
    )
    (out / "draft.md").write_text(draft or "", encoding="utf-8")
    print("[stage3] draft chars =", len(draft or ""))

    # --- Stage 3.5: 织入图表引用 ---
    article = await _weave_citations(draft, manifest, api_key, api_base, model)
    (out / "article.md").write_text(article, encoding="utf-8")
    refs_f = sorted({int(x) for x in re.findall(r'Figure\s*(\d+)', article)})
    refs_t = sorted({int(x) for x in re.findall(r'Table\s*(\d+)', article)})
    print("[stage3.5] refs figure=%s table=%s" % (refs_f, refs_t))

    # --- Stage 4: 按需重构（lieflat 自动 + 流程图准备） ---
    plan = R.plan_reconstruction(manifest, article)
    recon: Dict[str, dict] = {}
    lf_dir = out / "lieflat"
    lf_dir.mkdir(parents=True, exist_ok=True)
    for p in plan:
        key = "%s_%s" % (p['kind'], p['number'])
        if key in recon:
            continue
        img = figs / p['file']
        if not img.exists():
            continue
        if p['skill'] == 'lieflat-charts':
            out_html = lf_dir / ("%s.html" % key)
            if out_html.exists():
                recon[key] = {'type': 'lieflat', 'html_path': str(out_html), 'height': 520}
                print("[stage4] skip", key)
                continue
            path, msg, meta = await rebuild_chart(str(img), str(out_html), api_key, api_base, model)
            if path:
                recon[key] = {'type': 'lieflat', 'html_path': path, 'height': 520,
                              'explanation_zh': meta.get('explanation_zh', '')}
                print("[stage4] ok", key, msg)
            else:
                print("[stage4] FAIL", key, msg)
        else:
            from PIL import Image
            st = await R.describe_structure(Image.open(str(img)), api_key, api_base, model)
            redraw = flow_redraws.get(str(p['number']))
            if redraw and Path(redraw).exists():
                recon[key] = {'type': 'image', 'path': str(Path(redraw)),
                              'explanation_zh': (st or {}).get('explanation_zh', '')}
                print("[stage4] flow redraw", key)
            else:
                recon[key] = {'type': 'image', 'path': str(img),
                              'explanation_zh': (st or {}).get('explanation_zh', '')}
                print("[stage4] flow fallback-crop", key)

    (out / "recon.json").write_text(json.dumps(recon, ensure_ascii=False), encoding="utf-8")

    # --- Stage 5: 排版输出 ---
    title = next((l.strip() for l in article.split('\n') if l.strip()), "科普文章")
    final = render_final_html(article, manifest, str(figs), str(out / "final.html"),
                              reconstructed=recon, title=title)
    print("[stage5] final ->", final)
    return {
        "txt": str(txt), "figs": str(figs), "draft": str(out / "draft.md"),
        "article": str(out / "article.md"), "recon": str(out / "recon.json"),
        "final": final,
    }


async def _main():
    import argparse, os
    ap = argparse.ArgumentParser(description="端到端科普文章生成")
    ap.add_argument("pdf", help="PDF 路径")
    ap.add_argument("out", help="输出目录")
    ap.add_argument("--model", default="qwen3.8-max-preview")
    ap.add_argument("--flow-redraw", action="append", default=[], metavar="NUM=PATH",
                    help="流程图重绘，如 4=C:/x/fig4.png")
    ap.add_argument("--style", default=None, metavar="style.json",
                    help="文风蒸馏产物(style_distill 输出)，注入生成提示词")
    args = ap.parse_args()
    key = os.getenv("BAILIAN_KEY", "")
    base = os.getenv("BAILIAN_BASE", "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    redraws = {}
    for item in args.flow_redraw:
        num, path = item.split("=", 1)
        redraws[num] = path
    style_guide = None
    if args.style:
        data = json.loads(Path(args.style).read_text(encoding="utf-8"))
        style_guide = data.get("style_guide")
    await generate_article(args.pdf, args.out, key, base, args.model,
                           flow_redraws=redraws, style_guide=style_guide)


if __name__ == "__main__":
    asyncio.run(_main())