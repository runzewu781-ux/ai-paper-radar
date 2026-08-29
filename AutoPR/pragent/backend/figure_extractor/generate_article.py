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
import os
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
    sys = ('你是编辑。你的唯一任务是在草稿中自然插入必要的图表引用，不扩写事实。'
           '保持原有观点、数字、限定词和文风，不新增机构、方法机制、时间、因果、效果或外部背景。'
           '引用格式严格为 Figure N 或 Table N，只能引用下列存在的编号。直接输出终稿全文。')
    user = '可用图表：' + json.dumps(avail, ensure_ascii=False) + '\n\n草稿：\n' + draft
    async with setup_client(api_key, api_base) as c:
        return await call_text_llm_api(c, sys, user, model)


def _resolve_llm_runtime() -> tuple[str, str, str]:
    """Resolve the LLM endpoint without copying Antigravity secrets into the repo.

    Explicit environment variables win.  When they are absent, reuse the local
    Antigravity Tools OpenAI-compatible proxy configuration.  The proxy key
    stays in Antigravity's own config file and is only read at runtime.
    """
    key = os.getenv("BAILIAN_KEY", "").strip()
    base = os.getenv("BAILIAN_BASE", "").strip()
    model = os.getenv("AUTOPR_MODEL", "").strip() or "gemini-3.7-flash"

    if key:
        return key, base or "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1", model

    cfg_path = None
    explicit_cfg = os.getenv("AUTOPR_ANTIGRAVITY_CONFIG", "").strip()
    if explicit_cfg:
        candidate = Path(explicit_cfg)
        if candidate.exists():
            cfg_path = candidate

    if cfg_path is None:
        # AgentDock command sessions can intentionally omit HOME/USERPROFILE.
        # Walk upward from stable local paths so Windows user-home discovery
        # does not depend on those environment variables.
        seeds = [Path.cwd(), Path(__file__).resolve()]
        for seed in seeds:
            for parent in (seed, *seed.parents):
                candidate = parent / ".antigravity_tools" / "gui_config.json"
                if candidate.exists():
                    cfg_path = candidate
                    break
            if cfg_path is not None:
                break

    if cfg_path is None and os.name == "nt":
        matches = list(Path("C:/Users").glob("*/.antigravity_tools/gui_config.json"))
        if len(matches) == 1:
            cfg_path = matches[0]

    if cfg_path is not None and cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            proxy = cfg.get("proxy") or {}
            proxy_key = str(proxy.get("api_key") or "").strip()
            port = int(proxy.get("port") or 8045)
            if proxy_key:
                return proxy_key, f"http://127.0.0.1:{port}/v1", model
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Failed to read Antigravity Tools config: {exc}") from exc

    raise RuntimeError(
        "No LLM credentials available. Set BAILIAN_KEY or configure Antigravity Tools."
    )


def _require_llm_text(stage: str, text: Optional[str]) -> str:
    value = (text or "").strip()
    if not value or value.lower().startswith("error:"):
        raise RuntimeError(f"{stage} failed: {value or 'empty model response'}")
    return value


_NUMBER_RE = re.compile(r'(?<![A-Za-z0-9])(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:[%％])?')
_HYPE_TITLE_RE = re.compile(r'(爆款|吊打|碾压|震惊|炸裂|革命性|颠覆|秒杀|封神|史上最|彻底改变)')


def _numeric_atoms(text: str) -> set[str]:
    """Return normalized Arabic-number atoms for a conservative source check."""
    atoms = set()
    for token in _NUMBER_RE.findall(text or ""):
        token = token.replace(",", "").replace("％", "%")
        atoms.add(token)
        atoms.add(token.rstrip("%"))
    return atoms


def _unsupported_numbers(article: str, evidence: str) -> list[str]:
    source_atoms = _numeric_atoms(evidence)
    unsupported = []
    for token in _NUMBER_RE.findall(article or ""):
        normalized = token.replace(",", "").replace("％", "%")
        if normalized not in source_atoms and normalized.rstrip("%") not in source_atoms:
            unsupported.append(token)
    return sorted(set(unsupported))


def _json_object(text: str) -> dict:
    match = re.search(r'\{[\s\S]*\}', text or "")
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _manifest_evidence(manifest: dict) -> str:
    lines = []
    for item in manifest.get("items", []):
        lines.append(f"{item.get('kind', 'figure').title()} {item.get('number')}: {item.get('caption', '')}")
    return "\n".join(lines)


def _title_and_body(article: str) -> tuple[str, str]:
    """Use an explicit Markdown heading when present without duplicating it."""
    lines = article.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        heading = re.match(r'^#{1,6}\s+(.+?)\s*$', stripped)
        if heading:
            title = heading.group(1).strip()
            body_lines = lines[:index] + lines[index + 1:]
            return title or "科普文章", "\n".join(body_lines).strip()
        return stripped, article
    return "科普文章", article


async def _ground_and_verify_article(
    article: str,
    source_text: str,
    manifest: dict,
    api_key: str,
    api_base: str,
    model: str,
) -> tuple[str, dict]:
    """Ground the article in the paper, then independently audit unsupported claims."""
    evidence = source_text + "\n\n===== FIGURE/TABLE CAPTIONS =====\n" + _manifest_evidence(manifest)
    ground_system = (
        "你是科研传播稿的事实编辑。只做事实守恒修订，不做降AI味或风格重写。"
        "逐句核对论文原文和图表题注：任何事实、数字、机构、方法步骤、时间、比较、因果、性能和功能描述，"
        "若证据中没有明确支持，就删除或改成明确的主观感受/不确定表述。"
        "不得使用常识、外部知识或自行推断来补洞。精确保留原文中的数字、单位、比较对象与限定词。"
        "保留已有 Figure N / Table N 引用，不创建不存在的编号。第一行若为Markdown标题则保留。"
        "直接输出修订后的完整文章，不解释。"
    )
    ground_user = f"===== 论文证据 =====\n{evidence}\n\n===== 待核验文章 =====\n{article}"
    async with setup_client(api_key, api_base) as client:
        grounded = await call_text_llm_api(client, ground_system, ground_user, model)
    grounded = _require_llm_text("stage3.6 fact grounding", grounded)

    first_nonempty = next((line.strip() for line in grounded.splitlines() if line.strip()), "")
    if first_nonempty.startswith("#") and _HYPE_TITLE_RE.search(first_nonempty):
        title_system = (
            "你是科研标题编辑。把给定标题改成中性、准确、具体的中文Markdown一级标题。"
            "禁止爆款、吊打、碾压、震惊、炸裂、革命性、颠覆、秒杀等无法由论文直接证明的传播性词汇。"
            "只使用论文证据中能确认的任务、方法、对象或主要结果。只输出一行：# 标题。"
        )
        title_user = f"论文证据：\n{evidence}\n\n原标题：\n{first_nonempty}"
        async with setup_client(api_key, api_base) as client:
            safe_title = await call_text_llm_api(client, title_system, title_user, model)
        safe_title = _require_llm_text("stage3.6 title grounding", safe_title).splitlines()[0].strip()
        if not safe_title.startswith("#"):
            safe_title = "# " + safe_title.lstrip("# ")
        if _HYPE_TITLE_RE.search(safe_title):
            raise RuntimeError("stage3.6 title grounding retained unsupported hype wording")
        lines = grounded.splitlines()
        for index, line in enumerate(lines):
            if line.strip():
                lines[index] = safe_title
                break
        grounded = "\n".join(lines)

    unsupported_numbers = _unsupported_numbers(grounded, evidence)
    if unsupported_numbers:
        repair_system = (
            "你是事实修复编辑。下面文章包含无法在论文证据中逐字找到对应数值的数字。"
            "删除或改写相关断言，不得换成另一个猜测数字；其他已被证据支持的内容尽量不动。"
            "直接输出完整修订文章。"
        )
        repair_user = (
            "无法核验的数字：" + json.dumps(unsupported_numbers, ensure_ascii=False)
            + f"\n\n===== 论文证据 =====\n{evidence}\n\n===== 文章 =====\n{grounded}"
        )
        async with setup_client(api_key, api_base) as client:
            grounded = await call_text_llm_api(client, repair_system, repair_user, model)
        grounded = _require_llm_text("stage3.6 numeric repair", grounded)
        unsupported_numbers = _unsupported_numbers(grounded, evidence)
        if unsupported_numbers:
            raise RuntimeError(
                "stage3.6 fact grounding left unsupported numbers: " + ", ".join(unsupported_numbers)
            )

    audit_system = (
        "你是严格的科研事实审计器。只判断文章中的可核查事实是否被给定论文证据明确支持。"
        "主观感受可以存在，但不能伪装成论文事实。不得使用外部知识。"
        "返回严格JSON：{\"ok\": bool, \"unsupported\": [str], \"notes\": str}。"
        "unsupported只列出具体、可定位且证据不支持的断言；不要因为措辞不同就误报。"
    )
    audit_user = f"===== 论文证据 =====\n{evidence}\n\n===== 文章 =====\n{grounded}"
    async with setup_client(api_key, api_base) as client:
        audit_raw = await call_text_llm_api(client, audit_system, audit_user, model)
    audit = _json_object(_require_llm_text("stage3.6 fact audit", audit_raw))
    if not audit or audit.get("ok") is not True:
        claims = audit.get("unsupported") if isinstance(audit.get("unsupported"), list) else []
        if claims:
            repair_system = (
                "你是科研事实编辑。根据审计结果最小化修改文章：删除或收敛所有被列出的无证据断言，"
                "不得添加新的事实。直接输出完整文章。"
            )
            repair_user = (
                "审计发现：" + json.dumps(claims, ensure_ascii=False)
                + f"\n\n===== 论文证据 =====\n{evidence}\n\n===== 文章 =====\n{grounded}"
            )
            async with setup_client(api_key, api_base) as client:
                grounded = await call_text_llm_api(client, repair_system, repair_user, model)
            grounded = _require_llm_text("stage3.6 claim repair", grounded)

            async with setup_client(api_key, api_base) as client:
                audit_raw = await call_text_llm_api(
                    client, audit_system,
                    f"===== 论文证据 =====\n{evidence}\n\n===== 文章 =====\n{grounded}", model,
                )
            audit = _json_object(_require_llm_text("stage3.6 fact re-audit", audit_raw))

    if not audit or audit.get("ok") is not True:
        raise RuntimeError(
            "stage3.6 fact audit failed: "
            + json.dumps(audit.get("unsupported", []) if audit else [], ensure_ascii=False)
        )
    return grounded, audit


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
    base_prompt = (
        base_prompt
        + "\n\n===== 输出与事实约束 =====\n"
        + "优先使用论文原文中的明确证据。第一行必须是 Markdown 一级标题（# 标题），标题也不得超出论文证据。"
        + "不要把推测、常识或你对图形的猜测写成论文事实。"
    )
    if style_guide:
        base_prompt = base_prompt + "\n\n===== 强制遵循的文风指南 =====\n" + style_guide
    draft, source_for_generation = await generate_text_blog(
        txt_path=str(txt), api_key=api_key, text_api_base=api_base, model=model,
        language='zh', disable_qwen_thinking=False,
        ablation_mode='none',
        draft_prompt_override=base_prompt,
    )
    draft = _require_llm_text("stage3 draft generation", draft)
    (out / "draft.md").write_text(draft, encoding="utf-8")
    print("[stage3] draft chars =", len(draft))

    # --- Stage 3.5: 织入图表引用 ---
    article = await _weave_citations(draft, manifest, api_key, api_base, model)
    article = _require_llm_text("stage3.5 citation weaving", article)

    # --- Stage 3.6: 全文事实守恒 ---
    # The fact gate always sees the full extracted paper, not merely the draft
    # context/digest.  This catches unsupported mechanisms and numerical claims
    # before they can reach reconstruction or final publishing.
    full_source = txt.read_text(encoding="utf-8", errors="replace")
    article, fact_audit = await _ground_and_verify_article(
        article, full_source, manifest, api_key, api_base, model
    )
    (out / "article.md").write_text(article, encoding="utf-8")
    (out / "fact_audit.json").write_text(
        json.dumps(fact_audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    refs_f = sorted({int(x) for x in re.findall(r'Figure\s*(\d+)', article)})
    refs_t = sorted({int(x) for x in re.findall(r'Table\s*(\d+)', article)})
    print("[stage3.6] fact audit=PASS refs figure=%s table=%s" % (refs_f, refs_t))

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
            path, msg, meta = await rebuild_chart(
                str(img), str(out_html), api_key, api_base, model,
                caption=p.get('caption', ''),
            )
            if path:
                recon[key] = {'type': 'lieflat', 'html_path': path, 'height': 520,
                              'explanation_zh': meta.get('explanation_zh', '')}
                print("[stage4] ok", key, msg)
            else:
                # A faithful original crop is preferable to a lossy or invalid
                # scientific reconstruction. Record this as an explicit safe
                # fallback instead of leaving an ambiguous failed slot.
                recon[key] = {
                    'type': 'image',
                    'path': str(img),
                    'badge': '原图 · 安全回退',
                    'explanation_zh': meta.get('explanation_zh', ''),
                    'fallback_reason': msg,
                }
                print("[stage4] safe-fallback", key, msg)
        else:
            from PIL import Image
            st = await R.describe_structure(Image.open(str(img)), api_key, api_base, model)
            redraw = flow_redraws.get(str(p['number']))
            if redraw and Path(redraw).exists():
                recon[key] = {'type': 'image', 'path': str(Path(redraw)),
                              'badge': '流程图 · 结构重绘',
                              'explanation_zh': (st or {}).get('explanation_zh', '')}
                print("[stage4] flow redraw", key)
            else:
                recon[key] = {'type': 'image', 'path': str(img),
                              'badge': '原图 · 裁剪',
                              'explanation_zh': (st or {}).get('explanation_zh', '')}
                print("[stage4] flow fallback-crop", key)

    (out / "recon.json").write_text(json.dumps(recon, ensure_ascii=False), encoding="utf-8")

    # --- Stage 5: 排版输出 ---
    title, article_body = _title_and_body(article)
    final = render_final_html(article_body, manifest, str(figs), str(out / "final.html"),
                              reconstructed=recon, title=title)
    print("[stage5] final ->", final)
    return {
        "txt": str(txt), "figs": str(figs), "draft": str(out / "draft.md"),
        "article": str(out / "article.md"), "fact_audit": str(out / "fact_audit.json"),
        "recon": str(out / "recon.json"),
        "final": final,
    }


async def _main():
    import argparse
    ap = argparse.ArgumentParser(description="端到端科普文章生成")
    ap.add_argument("pdf", help="PDF 路径")
    ap.add_argument("out", help="输出目录")
    ap.add_argument("--model", default=None,
                    help="模型 ID；默认读取 AUTOPR_MODEL，未设置时使用 gemini-3.7-flash")
    ap.add_argument("--flow-redraw", action="append", default=[], metavar="NUM=PATH",
                    help="流程图重绘，如 4=C:/x/fig4.png")
    ap.add_argument("--style", default=None, metavar="style.json",
                    help="文风蒸馏产物(style_distill 输出)，注入生成提示词")
    args = ap.parse_args()
    key, base, default_model = _resolve_llm_runtime()
    model = args.model or default_model
    redraws = {}
    for item in args.flow_redraw:
        num, path = item.split("=", 1)
        redraws[num] = path
    style_guide = None
    if args.style:
        data = json.loads(Path(args.style).read_text(encoding="utf-8"))
        style_guide = data.get("style_guide")
    print(f"[runtime] model={model} base={base} credential=resolved")
    await generate_article(args.pdf, args.out, key, base, model,
                           flow_redraws=redraws, style_guide=style_guide)


if __name__ == "__main__":
    asyncio.run(_main())
