# AI 竞品分析助手

> 基于 AI Agent 的互联网产品竞品分析报告自动生成系统

## 项目概述

AI 竞品分析助手是一款智能化竞品分析工具。用户输入我方公司、竞品公司、分析产品和分析目标后，系统通过 **多个 AI Agent 协同工作**，自动执行以下流程：

1. **Gate Agent** — 输入验证与清洗
2. **Planner Agent** — 生成研究计划
3. **Research Agent** — 多源证据采集（官网、新闻、App Store、社交等）
4. **Compare Agent** — 竞品维度对比与差距分析
5. **Strategy Agent** — SWOT 分析、战略建议、路线图
6. **Report Agent** — 生成 Markdown / HTML / Word 格式报告
7. **Review Agent** — 质量审查与反馈

## 技术栈

| 层 | 技术 |
|---|---|
| **后端** | Python 3.13+, FastAPI, LangGraph, Pydantic, SQLAlchemy |
| **前端** | React 19, Next.js 15, TypeScript, Tailwind CSS 4, Shadcn UI |
| **工作流引擎** | LangGraph StateGraph |
| **数据库** | SQLite (开发) / PostgreSQL (生产) |
| **容器化** | Docker + Docker Compose |

## 项目结构

```
competitive-analysis/
├── backend/                  # Python FastAPI 后端
│   ├── app/
│   │   ├── application/      # 应用层：DTO、服务接口
│   │   ├── config/           # 配置：Settings、Constants
│   │   ├── domain/           # 领域层：实体、领域服务
│   │   ├── infrastructure/   # 基础设施：Agent、LLM、Tool、Workflow、Persistence
│   │   └── interfaces/       # 接口层：API 路由、Schema
│   ├── tests/                # 测试
│   └── Dockerfile
├── frontend/                 # Next.js 前端
│   ├── app/                  # 页面路由
│   │   ├── page.tsx          # 首页 — 分析表单
│   │   ├── analysis/[id]/    # 分析过程页
│   │   └── report/[id]/      # 报告展示页
│   ├── components/           # UI 组件
│   ├── lib/                  # API 客户端、工具函数
│   └── types/                # TypeScript 类型定义
├── outputs/                  # 架构设计文档
├── data/                     # 运行时数据
├── docker-compose.yml        # Docker 编排
├── Makefile                  # 常用命令
├── start.sh                  # 一键启动脚本
└── README.md
```

## 快速开始

### 前置条件

- **Python** 3.12+
- **Node.js** 22+
- **pnpm** (corepack enabled)

```bash
# 启用 corepack（用于 pnpm）
corepack enable
```

### 本地开发

**方式 1：一键启动（推荐）**
```bash
chmod +x start.sh
./start.sh
```

**方式 2：分别启动**

终端 1 — 后端：
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

终端 2 — 前端：
```bash
cd frontend
pnpm install
pnpm dev
```

**方式 3：Makefile**
```bash
make install    # 安装所有依赖
make dev        # 同时启动前后端
```

### 访问

- **前端**: http://localhost:3000
- **后端 API**: http://localhost:8000/api
- **API 文档**: http://localhost:8000/docs

## 使用流程

1. 打开首页 `http://localhost:3000`
2. 填写"我方公司"、"竞品公司"、"分析产品"和"分析目标"
3. 点击"开始分析"，进入分析过程页面
4. 等待 AI Agent 完成 7 个阶段的自动分析
5. 查看生成的竞品分析报告（支持 Markdown / HTML / Word 格式）

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/reports` | 创建竞品分析任务 |
| `GET` | `/api/reports/{taskId}` | 获取分析报告 |
| `GET` | `/api/reports` | 列出所有报告 |
| `GET` | `/api/tasks/{taskId}/progress` | 获取任务进度 |
| `PATCH` | `/api/tasks/{taskId}/decision` | 人工决策（HITL） |
| `GET` | `/api/health` | 健康检查 |

## Agent 工作流

```
用户输入 → Gate(验证) → Planner(计划) → Research(采集)
    → Compare(对比) → Strategy(分析) → Report(生成)
    → Review(审查) → Finalize(产出)
                              ↓
                    Need More Research?
                              ↓
                    返回用户补充信息
```

每个 Agent 的详细设计见 `outputs/` 目录。

## Docker 部署

```bash
# 构建并启动
docker compose up --build -d

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

## LLM 配置

默认使用 Mock Provider（返回模拟数据）。要连接真实 LLM：

```bash
export LLM_PROVIDER=openai
export LLM_API_KEY=sk-xxx
export LLM_MODEL=gpt-4o
```

或在 `backend/.env` 中配置。

## 项目状态

- [x] 架构设计
- [x] 后端项目骨架（DDD 目录结构、FastAPI、LangGraph Workflow）
- [x] 所有 Agent 实现
- [x] 前端三页面（首页、分析中、报告页）
- [x] Docker 容器化
- [x] 端到端流程验证

## 许可证

MIT
