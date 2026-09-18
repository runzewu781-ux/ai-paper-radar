# AutoPR — 来源与改造说明（UPSTREAM）

> 本目录**不是原创代码**，而是对上游开源项目的**本地改造版**，以普通子目录形式纳入本仓库
> （copy-in，**非** git submodule / subtree，故不携带上游 `.git` 历史）。

## 上游来源

- 仓库：<https://github.com/LightChen233/AutoPR>
- 论文：*AutoPR: Let's Automate Your Academic Promotion!* — arXiv:2510.09558
- 本改造基于的上游提交：`7f464f2cc64da2bbbb722249db538d7d1aa78263`（2025-10-16，"update TEXT_GENERATOR_PROMPT_CHINESE"）
- 上游作用：把一篇同行评审论文 PDF，自动转成适配社交平台的带配图推文；
  内部是多 Agent 流水线 —— `BlogGeneratorAgent`（写初稿）/ `FigureDescriberAgent`（看图描述）/
  `BlogIntegratorAgent`（整合成稿）。

## 许可证

遵循上游 **MIT License**，Copyright (c) 2025 Qiguang Chen。完整许可文本见同目录 `LICENSE`。
本改造在 MIT 条款下进行，保留上述版权声明。

## 本目录相对上游的改造（modification set）

1. **运行时统一走 Antigravity 本地代理 + `gemini-3.7-flash`**：`_resolve_llm_runtime()` 优先读
   `BAILIAN_KEY`（阿里云百炼 Token Plan，OpenAI 兼容协议），读不到则回退到本机
   `~/.antigravity_tools/gui_config.json`，走 `http://127.0.0.1:8045/v1`。
   **`.env` 含密钥，不入库**，需自行按 `.env.example` 与本文档配置。
2. **新增 YOLO-free 视觉链路** `pragent/paper_processing/figure_vision_pipeline.py`：用视觉模型对每页整图直读图表
   （并发、本地零推理），替代原 DocLayout-YOLO 的 CPU 版面检测（无 NVIDIA 卡时该步是分钟级瓶颈）。
   整页渲染图作为配图占位，描述写入 `precomputed_items[*].description`，供下游美化 skill 替换。
3. **移除 YOLO 依赖**：删除 `pragent/paper_processing/yolo.py` 与 `pragent/paper_processing/figure_table_pipeline.py`；
   `requirements.txt` 注释掉 `doclayout_yolo`；上游 `README.md` 的"下载 YOLO 权重"准备段已相应改写。
4. **新增 `research_brief` 证据溯源模块**（`pragent/paper_processing/research_brief/`）：
   把每一条论断绑定到**原文具体页码 + bbox 坐标 + `text_hash` 防篡改**，为事实门与数字核验提供凭据。
   配套测试见 `tests/test_research_brief.py` 与 `tests/test_research_brief_semantic.py`。
5. **新管线入口收敛为单一 CLI**：`pragent/quality/generate_article.py`，9 阶段端到端直出中文公众号长文
   （文本抽取 → 图表抽取分类 → 公众号初稿 → 引文编织 → 全文事实守恒 → 本地检测器 QA ×3 →
   选择性降 AI 味 → 二次事实审计）。
6. **视觉支路 `max_pages` 限页参数**：长论文可只读前 N 页以控时控费；不传则读全部页（忠实原行为）。

> **已移除**：上游的 `pragent/run.py`（batch/baseline 双路径）、`app.py`（Gradio Web UI）、
> `script/run_generation.sh`，以及 `blog_pipeline.py` 的
> `generate_final_post` / `generate_baseline_post` / `generate_wechat_post`
> 和 `prompts.py` 的 `XIAOHONGSHU_*`（Twitter / 小红书分平台适配）。
> 删除前的完整状态存档于 git tag **`legacy-pipeline-final`**，需要回溯可
> `git checkout legacy-pipeline-final -- <path>`。

## 运行方式

- 依赖：在 `AutoPR/` 下建独立虚拟环境后 `pip install -r requirements.txt`
  （`doclayout_yolo` 已注释，无需 YOLO 权重）。
- 端到端生成：`python pragent/quality/generate_article.py <pdf> <out>`（默认 `gemini-3.7-flash`）。

## 硬约束 / 已知坑

- **Windows 控制台编码**：上游 `tqdm.write` 含 `✓` 等 Unicode，GBK 控制台会抛 `UnicodeEncodeError` 带崩流程；
  启动前设 `set PYTHONIOENCODING=utf-8`（或 `PYTHONIOENCODING=utf-8 python ...`）。
- **`--model-path` 已不存在**：YOLO 版面检测整条链路已移除，不要照抄旧命令。
- 本仓库**不含**密钥与模型权重；端到端实测产物见仓库根的 `output*/`（被 `.gitignore` 排除，未入库）。
