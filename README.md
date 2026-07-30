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
cd backend
pip install -r requirements.txt
python -m alembic upgrade head      # 本地建表（云端启动时会自动 create_all，无需此步）
uvicorn app.main:app --reload --port 8000
```

### 3. 前端

```bash
cd frontend
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
cd backend
python -m app.cli sync --days 1 --max 25
```

### 5. 运行测试

```bash
cd backend
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
2. **Root Directory** 填 `backend`。
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
2. **Root Directory** 填 `frontend`，Framework Preset 选 **Vite**。
3. Environment Variables 填 `VITE_API_URL` = 后端地址（**不带** `/api`，如 `https://ai-paper-radar.onrender.com`）。
4. Deploy（`vercel.json` 已含 SPA rewrite）。

### 定时抓取 — cron-job.org

Render 免费层无内置 cron。用 cron-job.org 注册 → New cronjob → URL 填 `https://你的后端/api/sync/arxiv?days=1` → 方法 **POST** → 计划每小时 → 保存。

## 目录结构

```
backend/
  app/
    api/routes.py          # FastAPI 路由
    core/config.py         # Pydantic Settings
    db/session.py          # SQLAlchemy 引擎（SQLite/Postgres 双轨）
    models/entities.py     # 7 张表
    schemas/paper.py       # Pydantic 模型
    services/
      sources/             # arXiv / HF / GitHub 适配器
      ingestion/           # 去重 + 同步编排（增量分类/翻译）
      classification/      # 规则分类 + 人工覆盖
      ranking/             # 关注度计算
      translation.py       # 标题/摘要中文翻译
      scheduler.py         # 进程内定时（云端关闭）
    cli.py                 # 命令行入口
  tests/                   # 34 个单元/集成测试
  alembic/                 # 数据库迁移（本地用）
  Procfile                 # Render 启动命令

frontend/
  src/
    api/client.ts          # API 层（VITE_API_URL 可配）
    types/index.ts         # TypeScript 类型
    components/            # Layout, PaperCard, Reveal
    pages/                 # 6 个页面
  vercel.json              # Vercel SPA rewrite
```

## 功能状态

| 功能 | 状态 |
|------|------|
| arXiv 抓取（cs.AI/CL/LG/CV） | ✅ |
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
