# AutoPR — 来源与改造说明（UPSTREAM）

> 本目录**不是原创代码**，而是对上游开源项目的**本地改造版**，以普通子目录形式纳入本仓库
> （copy-in，**非** git submodule / subtree，故不携带上游 `.git` 历史）。

## 上游来源

- 仓库：<https://github.com/LightChen233/AutoPR>
- 论文：*AutoPR: Let's Automate Your Academic Promotion!* — arXiv:2510.09558
- 本改造基于的上游提交：`7f464f2cc64da2bbbb722249db538d7d1aa78263`（2025-10-16，"update TEXT_GENERATOR_PROMPT_CHINESE"）
- 上游作用：把一篇同行评审论文 PDF，自动转成适配社交平台（Twitter / 小红书）的带配图推文；
  内部是多 Agent 流水线 —— `BlogGeneratorAgent`（写初稿）/ `FigureDescriberAgent`（看图描述）/
  `BlogIntegratorAgent`（整合成稿）。

## 许可证

遵循上游 **MIT License**，Copyright (c) 2025 Qiguang Chen。完整许可文本见同目录 `LICENSE`。
本改造在 MIT 条款下进行，保留上述版权声明。

## 本目录相对上游的改造（modification set）

1. **接入阿里云百炼 Token Plan**：运行时统一用 `qwen3.8-max-preview`（文本 + 视觉，OpenAI 兼容协议）。
   配置走 `.env`（`OPENAI_API_BASE` + 百炼 Token Plan 专属 `OPENAI_API_KEY`，密钥格式见阿里云文档）；**`.env` 含密钥，不入库**，
   需自行按 `.env.example` 与本文档配置。
2. **新增 YOLO-free 视觉链路** `pragent/paper_processing/figure_vision_pipeline.py`：用视觉模型对每页整图直读图表
   （并发、本地零推理），替代原 DocLayout-YOLO 的 CPU 版面检测（无 NVIDIA 卡时该步是分钟级瓶颈）。
   整页渲染图作为配图占位，描述写入 `precomputed_items[*].description`，供下游美化 skill 替换。
3. **移除 YOLO 依赖**：删除 `pragent/paper_processing/yolo.py` 与 `pragent/paper_processing/figure_table_pipeline.py`；
   `requirements.txt` 注释掉 `doclayout_yolo`；`pragent/run.py` 去掉 `--model-path` 参数；上游 `README.md`
   的"下载 YOLO 权重"准备段已相应改写。
4. **三入口切换到新视觉链路**：`app.py`（Gradio）、`pragent/run.py`（batch + baseline 两路径）；
   `pragent/writing/blog_pipeline.py` 的 `generate_final_post` / `generate_baseline_post` 新增
   `precomputed_items` 注入参数（旧 CLI/评测路径默认 `None`，行为不变）。
5. **Gradio 界面预填**：`app.py` 启动时 `load_dotenv` 并把百炼 Base URL / Key / 模型名预填进 Advanced Settings。
6. **视觉支路 `max_pages` 限页参数**：长论文可只读前 N 页以控时控费；不传则读全部页（忠实原行为）。

## 运行方式

- 依赖：在 `AutoPR/` 下建独立虚拟环境后 `pip install -r requirements.txt`
  （`doclayout_yolo` 已注释，无需 YOLO 权重）。
- Gradio 界面：`python app.py`，浏览器打开 `http://127.0.0.1:7860`，上传 PDF 生成推文。
- 命令行批量：`python pragent/run.py --input-dir <含 paper.pdf 的文件夹> --output-dir <out> --text-model qwen3.8-max-preview --vision-model qwen3.8-max-preview`。

## 硬约束 / 已知坑

- `qwen3.8-max-preview` **锁死思考模式**：传 `enable_thinking=false` 会直接 400，故 CLI **禁止**加
  `--disable-qwen-thinking`，保持默认即可。
- **Windows 控制台编码**：上游 `tqdm.write` 含 `✓` 等 Unicode，GBK 控制台会抛 `UnicodeEncodeError` 带崩流程；
  启动前设 `set PYTHONIOENCODING=utf-8`（或 `PYTHONIOENCODING=utf-8 python ...`）。
- 本仓库**不含**密钥与模型权重；端到端实测产物（推文 + 占位配图）见仓库根的 `autopr_test_output/`（该目录被 `.gitignore` 排除，未入库）。
