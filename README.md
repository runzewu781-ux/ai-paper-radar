# AI Paper Radar

AI 论文雷达 — 自动抓取 arXiv 最新论文，跨源增强信号，分类归档，提供可浏览的 Web 界面。

## 技术栈

- 后端：Python 3.11+ / FastAPI / SQLAlchemy 2 / Alembic / SQLite
- 前端：React 18 / Vite / TypeScript / React Router / TanStack Query
- 外部数据源：arXiv API / Hugging Face Papers / GitHub API

## 快速开始

### 1. 配置

```bash
cp .env.example .env
# 编辑 .env 填入你的 Token
```

环境变量：
- `HF_TOKEN` — Hugging Face 只读 Token（可选，缺失时 HF 增强跳过）
- `GITHUB_TOKEN` — GitHub PAT（可选，缺失时使用匿名限额）
- `S2_API_KEY` — Semantic Scholar Key（本阶段未启用）
- `DATABASE_URL` — SQLite 路径，默认 `sqlite:///./data/paper_radar.db`

### 2. 后端

```bash
cd backend
pip install -r requirements.txt
python -m alembic upgrade head
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

CLI 方式：
```bash
cd backend
python -m app.cli sync --days 1 --max 25
```

API 方式：
```
POST http://localhost:8000/api/sync/arxiv?days=7
POST http://localhost:8000/api/sync/enrich
```

### 5. 运行测试

```bash
cd backend
python -m pytest tests/ -v
```

## 目录结构

```
backend/
  app/
    api/routes.py          # FastAPI 路由
    core/config.py         # Pydantic Settings
    db/session.py          # SQLAlchemy 引擎
    models/entities.py     # 7 张表
    schemas/paper.py       # Pydantic 模型
    services/
      sources/             # arXiv / HF / GitHub 适配器
      ingestion/           # 去重 + 同步编排
      classification/      # 规则分类 + 人工覆盖
      ranking/             # 关注度计算
    cli.py                 # 命令行入口
  tests/                   # 34 个单元/集成测试
  alembic/                 # 数据库迁移

frontend/
  src/
    api/client.ts          # API 层
    types/index.ts         # TypeScript 类型
    components/            # Layout, PaperCard
    pages/                 # 6 个页面
```

## 功能状态

| 功能 | 状态 |
|------|------|
| arXiv 抓取（cs.AI/CL/LG/CV） | ✅ |
| 跨分类/跨版本去重 | ✅ |
| HF Daily Papers 增强 | ✅（需网络可达） |
| GitHub 仓库信号 | ✅（仅可靠 URL） |
| Semantic Scholar | ⏸ 等 API Key |
| 10 领域规则分类 | ✅ |
| 人工分类不被覆盖 | ✅ |
| 关注度透明计算 | ✅ |
| 论文列表/筛选/搜索 | ✅ |
| 论文详情 + 信号展示 | ✅ |
| 编辑工作台（状态流转） | ✅ |
| 重复同步不重复插入 | ✅ |
| 单源失败不中断主流程 | ✅ |

## 已知限制

- HF API 在部分网络环境下需要代理
- Semantic Scholar 本阶段未启用
- 分类为纯规则引擎，无 LLM 分类
- 前端为功能型界面，未做视觉设计
- 无自动定时同步
- 无用户认证

## 下一阶段建议

1. 接入 Semantic Scholar（等 Key）
2. 加入 LLM 分类器（可替换规则引擎）
3. 中文标题/摘要生成
4. 公众号文章生成模块
5. 配图 + 排版
6. 定时调度器
7. 视觉设计升级
