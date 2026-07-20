# 🤖 AI 竞品情报分析助手

> 基于 LLM Agent + RAG 的智能竞品研究系统，输入目标公司和产品，AI 自动完成全网情报收集、多维度对比分析和战略洞察报告生成。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-green.svg)](https://www.python.org/)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)

---

## 📖 项目背景

在互联网产品竞争中，竞品分析是战略决策的核心输入。但传统的竞品分析依赖人工搜索、整理、对比，耗时数天甚至数周。

**AI 竞品情报分析助手** 将这一流程自动化：只需输入目标公司和竞品信息，AI Agent 团队会自动拆解研究任务、从多渠道搜集情报、交叉验证证据可信度、生成包含 SWOT 分析和战略建议的专业报告。

## 🎯 解决的问题

| 痛点 | 传统方式 | 本产品 |
|------|----------|--------|
| 信息搜集耗时 | 人工搜索数天 | Agent 自动搜索，分钟级完成 |
| 数据源单一 | 依赖搜索引擎 | 7 个数据源并行采集 |
| 证据可信度不明 | 主观判断 | 每条结论标注验证等级 |
| 报告格式不统一 | 手动排版 | Markdown/HTML/DOCX 标准化输出 |
| 缺乏战略洞察 | 数据罗列 | SWOT 分析 + 优先级建议 |

## ✨ 产品能力

- **🏢 企业实体识别** — 自动关联企业信息、品牌名称和产品线
- **🧩 多 Agent 任务拆解** — Strategy → Research → Insight → Compare → Report → Review 六步协作管线
- **🌐 多渠道 Web 检索** — 集成 Tavily 搜索引擎，覆盖 App Store / 新闻 / 社区 / GitHub 等数据源
- **🔍 Evidence 证据校验** — 每条分析结论标注可信度（Verified / Likely / Estimated），事实审计确保报告可信
- **📊 自动生成分析报告** — Markdown / HTML / DOCX 多格式导出，含 SWOT 分析和 P0 优先级建议

## 🏗 系统架构

```
┌──────────────────────────────────────────────────────┐
│                   Browser (http://localhost:3000)     │
└──────────┬────────────────────────────────┬──────────┘
           │                                │
    ┌──────▼──────┐                  ┌─────▼───────┐
    │  Frontend   │   Proxy /api/*   │   Backend   │
    │  Next.js 15 │ ◄──────────────► │   FastAPI   │
    │  Port 3000  │                  │   Port 8000 │
    └─────────────┘                  └──────┬──────┘
                                           │
         ┌─────────────────────────────────┼──────────────┐
         │                                 │              │
  ┌──────▼──────┐   ┌───────────┐  ┌──────▼─────┐  ┌─────▼──────┐
  │  DeepSeek /  │   │  Tavily   │  │  SQLite    │  │  File      │
  │  OpenAI LLM  │   │  Search   │  │  (data/)    │  │  Store     │
  └──────────────┘   └───────────┘  └────────────┘  └────────────┘
```

## 🔄 Agent 分析流程

```
用户输入 (公司/产品/目标)
    │
    ▼
┌──────────────┐
│ ① Strategy   │  拆解研究任务，制定分析计划
└──────┬───────┘
       ▼
┌──────────────┐
│ ② Research   │  多渠道搜索 (Web/AppStore/GitHub/News/社区)
└──────┬───────┘
       ▼
┌──────────────┐
│ ③ Insight    │  证据提取、交叉验证、置信度标注
└──────┬───────┘
       ▼
┌──────────────┐
│ ④ Compare    │  多维度对比分析 (功能/UX/商业/技术/增长)
└──────┬───────┘
       ▼
┌──────────────┐
│ ⑤ Report     │  生成结构化报告 (Markdown + HTML + DOCX)
└──────┬───────┘
       ▼
┌──────────────┐
│ ⑥ Review     │  事实审计 — 检查每条结论的证据支撑
└──────────────┘
```

## 📸 Demo 截图
<img width="1440" height="706" alt="image" src="https://github.com/user-attachments/assets/c73fdd9e-e4b2-4c5f-849e-5061b3036e66" />


| 首页 Hero | 分析进度 | 分析报告 |
|-----------|----------|----------|
| ![hero](docs/screenshots/hero.png) | ![progress](docs/screenshots/progress.png) | ![report](docs/screenshots/report.png) |

## 🚀 在线 Demo

<!-- 部署后更新此地址 -->
> 在线 Demo 地址：https://tackle-ungreased-defy.ngrok-free.dev

**本地体验：**

```bash
# 1. 克隆项目
git clone https://github.com/werbem/learn.git
cd learn

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY (可选) 和 TAVILY_API_KEY (可选)
# 无 API Key 时自动运行 Demo 模式，展示抖音 vs 快手固定案例

# 3. 启动服务
docker compose up --build -d

# 4. 访问
open http://localhost:3000
```

## 🔧 技术亮点

| 技术 | 用途 |
|------|------|
| **LangGraph** | 多 Agent 工作流编排，支持流式输出和 Human-in-the-Loop |
| **FastAPI + SSE** | 后端异步处理 + 实时进度推送 |
| **Pydantic Structured Output** | LLM 输出强制结构校验，杜绝幻觉格式 |
| **Evidence 管线** | 来源路由 → 选择 → 评估 → 聚类，四级证据处理 |
| **Trace 可追溯性** | 每次 LLM 调用全链路记录，支持诊断复盘 |
| **Demo 零配置模式** | 无 API Key 时自动回退到固定案例展示 |
| **Docker Compose** | 一键部署，前后端容器化 |

## 📁 项目结构

```
.
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── config/          # 配置 (settings, constants)
│   │   ├── infrastructure/  # LLM Client / Agents / Workflow / Tools
│   │   └── interfaces/api/  # REST API 路由
│   └── Dockerfile
├── frontend/                # Next.js 前端
│   ├── app/                 # 页面路由
│   ├── components/          # UI 组件
│   └── lib/                 # API 客户端
├── docker-compose.yml       # 一键部署
└── .env.example             # 环境变量模板
```

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)

---

*Built with ❤️ by AI Agents*
