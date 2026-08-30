# AI Paper Radar

AI 论文雷达 — 自动抓取 arXiv 最新论文，跨源增强信号，分类归档，翻译为中文，提供可浏览的 Web 界面。

## 技术栈

- 后端：Python 3.11+ / FastAPI / SQLAlchemy 2 / Alembic / SQLite（本地）或 Postgres（云端）
- 前端：React 18 / Vite / TypeScript / React Router / TanStack Query
- 外部数据源：arXiv API / Hugging Face Papers / GitHub API
- 翻译：DeepSeek（标题 + 摘要 → 中文）
- 视觉：taste-skill 反 slop 设计系统，明暗双主题

## 快速开始（本地）

### 1. 配置

```bash
cp .env.example .env
# 编辑 .env 填入你的 Token
```

环境变量：
- `HF_TOKEN` — Hugging Face 只读 Token（可选，缺失时 HF 增强跳过）
- `GITHUB_TOKEN` — GitHub PAT（可选，缺失时使用匿名限额）
- `S2_API_KEY` — Semantic Scholar Key（本阶段未启用）
- `DATABASE_URL` — 本地默认 `sqlite:///./data/paper_radar.db`；云端用 Postgres 串
- `LLM_API_BASE` / `LLM_API_KEY` / `LLM_MODEL` — 翻译用 LLM（默认 DeepSeek）
- `HF_PROXY` — 仅本地访问 HF 需要代理时填（如 `http://127.0.0.1:7890`），**云端留空**
- `SCHEDULER_ENABLED` — 进程内定时抓取开关；**云端设 `false`**，改用外部 cron
- `CORS_ORIGINS` — 允许的前端源，云端加上你的 Vercel 域名

### 2. 后端

```bash
cd PaperRadar/backend
pip install -r requirements.txt
python -m alembic upgrade head      # 本地建表（云端启动时会自动 create_all，无需此步）
uvicorn app.main:app --reload --port 8000
```

### 3. 前端

```bash
cd PaperRadar/frontend
npm install
npm run dev
```

访问 http://localhost:5173

### 4. 同步论文

同步是**后台异步**的：触发后立即返回 `running`，抓取 + 翻译在后台跑，完成后状态变 `completed`。

```
POST http://localhost:8000/api/sync/arxiv?days=1&max_results=25   # max_results 可选，限流/调试用
POST http://localhost:8000/api/sync/enrich                         # 全量补 HF/GitHub 信号
POST http://localhost:8000/api/translate/backfill?limit=20         # 分批补历史未翻译论文
```

CLI 方式：
```bash
cd PaperRadar/backend
python -m app.cli sync --days 1 --max 25
```

### 5. 运行测试

```bash
cd PaperRadar/backend
python -m pytest tests/ -v
```

## 免费部署（Vercel + Render + Neon）

四家全免费、无需信用卡。架构：前端静态托管在 Vercel，后端长驻服务在 Render，数据库用 Neon 的免费 Postgres，定时抓取用 cron-job.org 外部触发。

> 副作用须知：你的 `HF_TOKEN / GITHUB_TOKEN / LLM_API_KEY` 会存入 Render 的环境变量（正规平台、加密存储，但请知情）；Render / Neon 免费层"无人访问时休眠"，冷启动会慢几十秒，请求一来即唤醒，自用足够。

### 数据库 — Neon

1. neon.tech 注册 → New Project。
2. 复制 connection string（形如 `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`）。

### 后端 — Render

1. render.com 用 GitHub 登录 → New Web Service → 选本仓库。
2. **Root Directory** 填 `PaperRadar/backend`。
3. **Build Command** 填 `pip install -r requirements.txt`。
4. **Start Command** 留空（读 `Procfile`），或填 `uvicorn app.main:app --host 0.0.0.0 --port $PORT`。
5. Instance type 选 **Free**。
6. Environment Variables 填：
   - `HF_TOKEN`、`GITHUB_TOKEN`、`LLM_API_BASE`、`LLM_API_KEY`、`LLM_MODEL`
   - `DATABASE_URL` = 上面的 Neon 串
   - `SCHEDULER_ENABLED=false`
   - `HF_PROXY` 留空
   - `CORS_ORIGINS=["https://你的vercel域名.vercel.app"]`
7. Deploy。首次启动会自动建表（startup 时 `create_all`），无需手动迁移。
8. 记下后端地址，形如 `https://ai-paper-radar.onrender.com`。

### 前端 — Vercel

1. vercel.com 用 GitHub 登录 → New Project → 选本仓库。
2. **Root Directory** 填 `PaperRadar/frontend`，Framework Preset 选 **Vite**。
3. Environment Variables 填 `VITE_API_URL` = 后端地址（**不带** `/api`，如 `https://ai-paper-radar.onrender.com`）。
4. Deploy（`vercel.json` 已含 SPA rewrite）。

### 定时抓取 — cron-job.org

Render 免费层无内置 cron。用 cron-job.org 注册 → New cronjob → URL 填 `https://你的后端/api/sync/arxiv?days=1` → 方法 **POST** → 计划每小时 → 保存。

## 目录结构

仓库现在按能力分成三大块：**PaperRadar（文章雷达）**、**AutoPR（论文科普生产）**、**Lieflat-Charts-Skill（图表 Skill 接入口）**。AutoPR 内部再按生产职责拆分，避免写作、排版、降噪、解析逻辑继续混在同一目录。

```text
ai-paper-radar/
├─ PaperRadar/                         # 文章雷达
│  ├─ backend/                         # FastAPI / 数据源 / 分类 / 排名 / 数据库
│  └─ frontend/                        # React / Vite Web UI
│
├─ AutoPR/                             # 论文 -> 科普文章生产
│  ├─ samples/                         # 样品产出区
│  │  └─ generated/                    # 本地 PDF / HTML / ZIP / 实验结果（Git 忽略）
│  ├─ pragent/
│  │  ├─ writing/                      # 写作区：公众号 prompt、长文生成、风格蒸馏
│  │  ├─ layout/                       # 排版区：最终 HTML、图表视觉编排、结构图渲染
│  │  ├─ ai_denoise/                   # AI 降噪区：AI-tone 检测、选择性改写、文本清理
│  │  ├─ paper_processing/             # 论文解析区：PDF/HTML/Text、Figure/Table 提取
│  │  ├─ quality/                      # 质量审计区：事实门、数字核验、生成总验收
│  │  ├─ core/                         # 公共基础：模型 client / Agent 基础能力
│  │  └─ run.py                        # CLI 入口
│  ├─ eval/                            # PRBench / 评测体系
│  ├─ docs/                            # AutoPR 文档
│  ├─ assets/                          # 静态资源
│  └─ script/                          # 辅助脚本
│
├─ Lieflat-Charts-Skill/               # Lieflat 独立 Skill 接入口（不复制源码）
│  └─ README.md                        # 指向独立仓库与 AgentDock Skill URI
│
├─ .env.example
├─ .gitignore
└─ README.md
```

这里额外补出的 **论文解析区** 和 **质量审计区** 是必要的：前者负责把 PDF 变成可写作证据，后者负责事实与生成质量，不应混入“排版”或“AI 降噪”。`core` 只放跨区共享基础设施，不作为业务产出区。

本地生成物统一进入 `AutoPR/samples/generated/`；写作语料 `AutoPR/style_corpus/` 仍保持本地且 Git 忽略。Lieflat 保持独立仓库/独立 Skill，AutoPR 只消费其已验证输出，避免出现两份源码漂移。

## 功能状态

| 功能 | 状态 |
|------|------|
| arXiv 抓取（cs.AI/CL/LG/CV） | ✅ |
| arXiv 关键词搜索（按相关度） | ✅ |
| 跨分类/跨版本去重 | ✅ |
| HF Daily Papers 增强 + HF 推荐标记 | ✅（需网络可达） |
| GitHub 仓库信号 | ✅（仅可靠 URL） |
| Semantic Scholar | ⏸ 等 API Key |
| 10 领域规则分类 | ✅ |
| 人工分类不被覆盖 | ✅ |
| 关注度透明计算 | ✅ |
| 中文标题 + 摘要翻译 | ✅ |
| 论文时间区间 + 发布时间 | ✅ |
| 论文列表/筛选/搜索 | ✅ |
| 论文详情 + 信号展示 | ✅ |
| 编辑工作台（状态流转） | ✅ |
| 增量分类/翻译（不扫全库） | ✅ |
| 后台异步同步 + 补翻译 | ✅ |
| 明暗双主题视觉（反 slop） | ✅ |
| 进程内定时 / 云端外部 cron | ✅ |
| 重复同步不重复插入 | ✅ |
| 单源失败不中断主流程 | ✅ |

## 已知限制

- HF API 在本地部分网络需代理（`HF_PROXY`），云端直连通常可达
- Semantic Scholar 本阶段未启用
- 分类为纯规则引擎，无 LLM 分类
- 无用户认证
- 免费层后端/数据库会休眠，冷启动慢

## 下一阶段建议

1. 接入 Semantic Scholar（等 Key）
2. 加入 LLM 分类器（可替换规则引擎）
3. 一句话结论（one_line_zh）生成
4. 公众号文章生成模块
5. 配图 + 排版
6. 长尾论文发现算法

## AutoPR 多 Agent 推文生成（引用 + 改造）

`AutoPR/` 目录是上游 [LightChen233/AutoPR](https://github.com/LightChen233/AutoPR)（论文 arXiv:2510.09558）的**本地改造版**，以普通子目录形式纳入本仓库（**非** git submodule）。它把一篇论文 PDF 自动写成带配图的小红书 / Twitter 推文，内部是多 Agent 流水线（写初稿 / 看图描述 / 整合成稿）。

相对上游的改造：接入阿里云百炼（`qwen3.8-max-preview` 文本 + 视觉）、用视觉模型整页直读图表替代 DocLayout-YOLO（移除 YOLO 依赖与权重）、三个入口切到新视觉链路、Gradio 预填配置。来源、改造清单与许可（上游 MIT）详见 [`AutoPR/UPSTREAM.md`](AutoPR/UPSTREAM.md)。

> 实测：用 `2510.09558` PDF 端到端跑通，产出见本地 `autopr_test_output/post.md`（该产物目录被 `.gitignore` 排除，未入库）。
