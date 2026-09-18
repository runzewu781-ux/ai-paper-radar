# AI Paper Radar (智能论文雷达与学术科普生产系统)

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT" />
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-18-61DAFB.svg?logo=react&logoColor=black" alt="React 18" />
  <img src="https://img.shields.io/badge/Vite-5-646CFF.svg?logo=vite&logoColor=white" alt="Vite" />
  <img src="https://img.shields.io/badge/Agent-Multi--Agent%20Pipeline-8B5CF6.svg" alt="Multi-Agent" />
</p>

一套集**前沿论文实时情报监控、跨源信号增强、学术图表高精度解析，与多 Agent 自动化科普/推文内容生成**于一体的全链路生产系统。

---

## 核心系统架构

整个仓库由三大核心模块协同构成：

```
ai-paper-radar/
├── PaperRadar/               # 模块一：AI 论文情报雷达 (监控 / 抓取 / 分类 / Web 浏览)
│   ├── backend/              # FastAPI 异步后台 + SQLite/Postgres + 定时抓取引擎
│   └── frontend/             # React 18 + Vite + TailwindCSS 现代化明暗双主题界面
├── AutoPR/                   # 模块二：论文深度多 Agent 科普与推文生成管线
│   ├── pragent/              # 视觉排版解析、图表切片抽取、学术简报与推文生成器
│   ├── app.py                # Gradio 交互式生成界面
│   └── run_wechat_article.py # 微信深度长文 / 自媒体推文批量排版出口
├── Lieflat-Charts-Skill/     # 模块三：图表与数据可视化增强技能库
├── start_all.bat             # Windows 一键全服务启动脚本 (后端:8000 + 前端:5173 + AutoPR:7860)
└── LICENSE                   # MIT 开源许可证
```

---

## 功能特性

### 1. 论文情报雷达 (PaperRadar)
- **多源数据融合**：自动抓取 arXiv 最新发布论文，交叉关联 Hugging Face Papers 讨论热度与配套 GitHub 开源仓库 Star 指标。
- **自动结构化与中文翻译**：调用大模型自动将论文标题与核心摘要翻译为精炼中文，拒绝机械机翻。
- **后台异步同步与调度**：支持进程内定时抓取与云端外部 Webhook / Cron 调度，拉取与翻译全程后台异步执行，不阻塞主线程。
- **现代化阅读体验**：基于 React 18 与反审美疲劳设计系统构建，原生支持明暗双主题切换与移动端响应式布局。

### 2. 多 Agent 学术科普生产管线 (AutoPR)
- **纯视觉整页直读**：采用现代多模态视觉模型直接解析论文排版，移除对重型目标检测权重（如 YOLO）的依赖，轻量且高保真。
- **学术图表精准切分与关联**：自动定位并提取论文关键实验图表（Figures & Tables），精准匹配图表说明（Captions）与上下文佐证。
- **多 Agent 分工协同**：
  - **研究简报 Agent**：梳理背景、核心假设、推导过程与消融实验。
  - **视觉提炼 Agent**：提取核心结构图，自动生成通俗易懂的图表解析。
  - **自媒体排版 Agent**：输出适配小红书、Twitter/X、微信公众号的结构化图文长文。

---

## 快速上手

### 方式一：Windows 一键快速启动（推荐）

在本地环境配置好后，直接双击运行根目录的：
```bat
start_all.bat
```
脚本将一键同时拉起三大服务：
- **论文雷达 Web 界面**：`http://127.0.0.1:5173`
- **AutoPR 科普生成界面**：`http://127.0.0.1:7860`
- **后端 API 文档 (Swagger)**：`http://127.0.0.1:8000/docs`

---

### 方式二：手动分步启动

#### 1. 环境变量配置
复制配置模板并填入相应 API 密钥：
```bash
cp .env.example .env
```
主要配置项说明：
- `LLM_API_KEY` / `LLM_API_BASE` / `LLM_MODEL`：大语言模型接口（默认支持 DeepSeek、Qwen、OpenAI 等标准兼容接口）
- `HF_TOKEN`：Hugging Face 访问凭证（可选，用于拉取 HF 论文热度）
- `GITHUB_TOKEN`：GitHub 访问凭证（可选，用于查询配套代码库 Star 数）
- `DATABASE_URL`：本地数据库连接串（默认 SQLite：`sqlite:///./data/paper_radar.db`）

#### 2. 启动 PaperRadar 后端
```bash
cd PaperRadar/backend
pip install -r requirements.txt
python -m alembic upgrade head      # 初始化数据库表结构
uvicorn app.main:app --reload --port 8000
```

#### 3. 启动 PaperRadar 前端
```bash
cd PaperRadar/frontend
npm install
npm run dev
```
浏览器访问 `http://localhost:5173`。

#### 4. 启动 AutoPR 多 Agent 生成界面
```bash
cd AutoPR
pip install -r requirements.txt
python app.py
```
浏览器访问 `http://localhost:7860`。

---

## 常用 API 与数据同步命令

### 手动触发论文同步（CLI 方式）
```bash
cd PaperRadar/backend
python -m app.cli sync --days 1 --max 25
```

### 接口异步触发（HTTP POST）
```bash
# 抓取最近 1 天内的 arXiv 论文（限流/测试用）
curl -X POST "http://localhost:8000/api/sync/arxiv?days=1&max_results=25"

# 全量补充 HuggingFace 与 GitHub 开源指标
curl -X POST "http://localhost:8000/api/sync/enrich"

# 批量补充历史未翻译论文
curl -X POST "http://localhost:8000/api/translate/backfill?limit=20"
```

---

## 云端全免费部署指南 (Vercel + Render + Neon)

本系统可完全基于免费额度实现零成本云端部署：
- **数据库**：使用 [Neon](https://neon.tech) 免费 Serverless Postgres。
- **后端服务**：使用 [Render](https://render.com) Web Service（指定根目录为 `PaperRadar/backend`）。
- **前端页面**：使用 [Vercel](https://vercel.com) 静态托管（指定根目录为 `PaperRadar/frontend`）。
- **定时同步**：在 Render 环境变量中关闭进程内调度（`SCHEDULER_ENABLED=false`），利用 [cron-job.org](https://cron-job.org) 每天定时调用 `/api/sync/arxiv` 接口。

---

## 开源协议

本项目采用 [MIT License](LICENSE) 授权许可。包含商业使用、修改与分发在内的所有使用均自由开放。
其中 `AutoPR/` 模块包含来自开源社区 [LightChen233/AutoPR](https://github.com/LightChen233/AutoPR) 的改造引用代码，同样遵循 MIT 许可。
