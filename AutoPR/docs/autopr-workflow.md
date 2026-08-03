# AutoPR 工作流程图

> 入口：`run.py --input-dir <projects> --output-dir <out>`（CLI）或 `app.py`（Gradio 网页）。
> 每个项目子文件夹含一个 PDF，全流程异步，支持并发与断点续跑（输出目录已存在则跳过）。

```mermaid
flowchart TD
    START([输入目录 / 上传 PDF]) --> INFER{平台推断}
    INFER -- "文件夹名纯数字 → twitter/en" --> SP
    INFER -- "文件夹名含字母 → xiaohongshu/zh" --> SP
    INFER -- "--platform 显式指定" --> SP
    INFER -- "wechat（公众号长文，强制 zh）" --> SP

    subgraph S1 [Stage 1 · 文本提取 text_pipeline]
        SP[遍历项目子文件夹<br/>读取 project.pdf] --> PDF2HTML[PDF → HTML<br/>pdf2html]
        PDF2HTML --> HTML2TXT[HTML → TXT<br/>html2txt]
        HTML2TXT --> TXT[(paper.txt)]
    end

    TXT --> FMT{post_format?}
    FMT -- "text_only" --> SKIP2[跳过视觉阶段]
    FMT -- "rich / description_only" --> S2

    subgraph S2 [Stage 2 · 视觉定位+裁剪 figure_vision_pipeline · YOLO-free]
        RENDER[逐页渲染 PNG<br/>144 dpi] --> LOCATE[视觉模型返回 JSON<br/>bbox + type + label + desc]
        LOCATE --> CROP[PIL 按 bbox 裁剪独立 PNG]
        CROP --> ITEMS[items 列表<br/>type: table / flow / figure]
    end

    ITEMS --> BF{--beautify-figures?<br/>默认开}
    SKIP2 --> S3
    BF -- "关" --> S3
    BF -- "开" --> S25

    subgraph S25 [Stage 2.5 · 配图美化 beautify_figures]
        S25A{type?}
        S25A -- "flow" --> ANDO[安多 skill 重画<br/>Atlas gpt-image-2 生图<br/>2048x1152 · quality=low]
        S25A -- "table / figure" --> EXTRACT[qwen 视觉读原图<br/>提取结构化数据 JSON]
        EXTRACT --> CFG[写 config.json]
        CFG --> BUILD[lieflat-charts<br/>node build.mjs 生成 HTML]
        BUILD --> SHOT[Playwright 截图 PNG]
        ANDO --> REPLACE[原地替换 item_path]
        SHOT --> REPLACE
        REPLACE -- "失败则保留原图" --> S3
    end

    subgraph S3 [Stage 3 · 结构化草稿 generate_text_blog]
        LEN{文本超阈值?}
        TXT --> LEN
        LEN -- "是" --> SUM[分层摘要 summarize_long_text]
        LEN -- "否" --> DRAFT
        SUM --> DRAFT[BlogGeneratorAgent<br/>生成结构化草稿 blog_draft]
        DRAFT --> BD[(blog_draft + 源文本)]
    end
    S25 --> S3

    subgraph S4 [Stage 4 · 平台终稿 generate_final_post]
        PROMPT[按 platform × format × language<br/>选择集成 prompt] --> DESC{已有 vision items?}
        DESC -- "有（precomputed_items）" --> INTEG
        DESC -- "无（assets_dir 路径）" --> VD[vision 模型描述图片<br/>FigureDescriberAgent]
        VD --> CACHE[描述缓存<br/>cache-dir/hash/model.json]
        CACHE -->         INTEG[BlogIntegratorAgent<br/>草稿 + 图片描述 → 占位符<br/>FIGURE-PLACEHOLDER-N]
        INTEG --> HTMLIMG[替换占位符 → 内嵌 &lt;img&gt;<br/>配图插入正文对应位置]
    end
    S3 --> S4

    HTMLIMG --> WX{platform = wechat?}
    WX -- "是" --> CLEAN[卡兹克 L1 清理<br/>clean_khazix + l1_audit 审计]
    WX -- "否" --> MD2HTML
    CLEAN --> MD2HTML[md_to_html 渲染<br/>markdown + 配图 → 白底图文 HTML]
    MD2HTML --> PACK[打包最终成品<br/>单文件 final.html<br/>配图 base64 内嵌正文位置]
    PACK --> QC[humanizer-zh 只读质检<br/>humanizer_report.md]
    QC --> DONE([输出项目目录<br/>final.html + img/ 素材])
    DONE --> END([清理 .temp 临时目录<br/>→ 结束])
```

## 关键分支与配置

| 维度 | 说明 |
|---|---|
| 平台推断 | 目录名纯数字→twitter/en；含字母→xiaohongshu/zh；`--platform` 可显式覆盖；wechat 强制中文长文路径 |
| 配图美化 | `--beautify-figures`（默认开）/ `--no-beautify-figures`；flow 图走 Atlas 生图，table/figure 走 lieflat-charts 重构；失败保留原图 |
| 后处理（wechat） | 卡兹克 L1 清理 + 违禁词审计 + 可选 humanizer-zh 只读质检（`--skip-humanizer-qc` 跳过） |
| 断点续跑 | 输出目录已存在且非空则跳过该项目 |
| 并发 | `--concurrency` 控制并行项目数，信号量限流 |
| 消融/基线 | `--ablation <mode>` / `--baseline-mode <mode>` 切换实验分支，输出带 `_ablation_*` / `_baseline_*` 后缀 |
| API | text/vision 默认共用 key（`--text-api-key` → `--vision-api-key` 回退），Base 默认 OpenAI；qwen3.8-max-preview 默认模型；Atlas 生图 key 走 `--atlas-key` 或 `ATLASCLOUD_API_KEY` |
