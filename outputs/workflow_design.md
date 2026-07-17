# AI 竞品分析助手 — AI Workflow Design（LangGraph 范式）

> 基于上一轮 Architecture Design
> 设计范式：**LangGraph**（有状态图 + 节点 + 条件边 + Checkpoint）

---

## 1. State 定义

全局 State 是所有 Agent 节点的共享上下文。LangGraph 中 State 是 TypedDict，每个节点读取并更新 State 中的部分字段。

### 1.1 顶层 State 结构

```typescript
interface WorkflowState {
  // ── 任务元信息（不变） ──
  task_id: string;                    // UUID，任务唯一标识
  created_at: string;                 // ISO 8601
  updated_at: string;

  // ── 用户输入（Gate → Planner 消费） ──
  user_input: UserInput;              // 原始用户输入
  validated_input: ValidatedInput;    // Gate 校验后

  // ── 执行上下文（Orchestrator 管理） ──
  current_phase: Phase;               // 当前阶段枚举
  phase_history: Array<PhaseRecord>;  // 完整执行轨迹
  progress: number;                   // 0.00 ~ 100.00

  // ── Agent 产出（累积，只增不减） ──
  research_plan: ResearchPlan | null;         // Planner 输出
  evidence_bundle: EvidenceBundle | null;     // Research 输出
  gap_analysis: GapAnalysis | null;           // Compare 输出
  strategic_insights: StrategicInsights | null; // Strategy 输出
  report_document: ReportDocument | null;     // Report 输出
  review_result: ReviewResult | null;         // Review 输出

  // ── 错误与重试 ──
  errors: Array<ErrorRecord>;         // 错误日志
  retry_counts: Record<string, number>; // { node_name: count }

  // ── 流式事件缓冲区 ──
  stream_events: Array<StreamEvent>;  // 按序累积

  // ── Human-in-the-Loop ──
  human_checkpoints: Array<HumanCheckpoint>;
  pending_human_decision: HumanDecisionRequest | null;

  // ── 最终产出 ──
  final_report: {
    markdown: string | null;
    word_url: string | null;
    html: string | null;
  };

  // ── 元数据 ──
  total_duration_ms: number;
  llm_token_usage: {
    total_prompt_tokens: number;
    total_completion_tokens: number;
  };
  version: string;                    // "v1"
}
```

### 1.2 子类型定义

```typescript
type Phase =
  | "initialized"
  | "validating"
  | "validated"
  | "validation_failed"
  | "planning"
  | "planned"
  | "researching"
  | "researched"
  | "comparing"
  | "compared"
  | "strategizing"
  | "strategized"
  | "reporting"
  | "reported"
  | "reviewing"
  | "reviewed"
  | "review_failed"
  | "finalizing"
  | "completed"
  | "failed"
  | "cancelled";

interface PhaseRecord {
  phase: Phase;
  entered_at: string;
  duration_ms: number;
  status: "running" | "completed" | "failed" | "skipped";
  error?: ErrorInfo;
}

interface ErrorInfo {
  code: string;           // "TIMEOUT" | "RATE_LIMIT" | "LLM_ERROR" | "NO_DATA" | "PARSE_ERROR" | "VALIDATION_ERROR"
  message: string;
  node: string;
  timestamp: string;
  retryable: boolean;
}

interface ErrorRecord extends ErrorInfo {
  retry_count: number;
  resolved: boolean;
}

interface StreamEvent {
  type: StreamEventType;
  phase: Phase;
  data: unknown;
  timestamp: string;
  sequence: number;
}

type StreamEventType =
  | "phase_entered"
  | "phase_completed"
  | "phase_failed"
  | "progress_update"
  | "agent_heartbeat"
  | "intermediate_result"
  | "llm_token"
  | "human_checkpoint_requested"
  | "human_decision_received"
  | "error"
  | "warning";

interface HumanCheckpoint {
  checkpoint_id: string;
  node: string;
  requested_at: string;
  context: {
    available_data: string[];     // 可供人工审核的数据摘要
    required_decision: string;     // 需要人类决定的 question
    options: Array<{               // 可选方案
      label: string;
      value: string;
      impact: string;
    }>;
  };
  decision: HumanDecision | null;
  resolved_at: string | null;
}

interface HumanDecisionRequest {
  checkpoint_id: string;
  question: string;
  context: Record<string, unknown>;
  timeout_minutes: number;        // 超时后走默认路径
  options: Array<{
    id: string;
    label: string;
    description: string;
    default: boolean;
  }>;
}

type HumanDecision = {
  option_id: string;
  comment?: string;
  decided_at: string;
};
```

### 1.3 Agent I/O State 引用（来自 Architecture Design）

State 中的 `research_plan`、`evidence_bundle`、`gap_analysis`、`strategic_insights`、`report_document`、`review_result` 的 Schema 定义已在 Architecture Design 第 7 节中完成。Workflow 层仅引用它们作为 State 字段，不重新定义结构。

---

## 2. 图结构总览

```
                    ┌──────────────┐
                    │    START     │
                    │ (user_input) │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ validate_inp │ ← Gate Agent
                    │   ut_node    │
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              │                         │
         [valid]                   [invalid]
              │                         │
       ┌──────▼───────┐         ┌──────▼───────┐
       │  plan_node   │         │  fail_node   │
       │ (Planner)    │         │ (终端,400)   │
       └──────┬───────┘         └──────────────┘
              │
       ┌──────▼───────┐
       │ research_node│ ← Research Agent
       │ (sub-graph)  │
       └──────┬───────┘
              │
       ┌──────▼───────┐
       │ compare_node │ ← Compare Agent
       └──────┬───────┘
              │
       ┌──────▼───────┐
       │ strategy_node│ ← Strategy Agent
       │  ◄── HITL   │ ← Human: 审核证据 & 调整策略方向
       └──────┬───────┘
              │
       ┌──────▼───────┐
       │  report_node │ ← Report Agent
       │  ◄── HITL   │ ← Human: 选择模板 / 章节
       └──────┬───────┘
              │
       ┌──────▼───────┐
       │  review_node │ ← Review Agent
       └──────┬───────┘
              │
    ┌─────────┴──────────┐
    │                    │
 [passed]           [failed]
    │                    │
    │            ┌───────▼────────┐
    │            │ retry_counter  │
    │            │ (max_iter=3)   │
    │            └───────┬────────┘
    │                    │
    │           ┌────────┴────────┐
    │           │                 │
    │      [< 3 retries]    [>= 3 retries]
    │           │                 │
    │           ▼                 ▼
    │     back to          ┌──────────────┐
    │    report_node       │  fail_node   │
    │                      │ (终端,失败)  │
    └──────────────────────┴──────────────┘
                           │
                    ┌──────▼───────┐
                    │finalize_node │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │     END      │
                    │ (completed)  │
                    └──────────────┘
```

---

## 3. 每个节点的详细设计

### 3.1 `validate_input_node`（Gate Agent）

| 属性 | 定义 |
|------|------|
| **功能** | 校验用户输入合法性 |
| **调用 Tool** | `SchemaValidator.validate()` — 纯本地函数，不调用 LLM |
| **同步/异步** | 同步，毫秒级完成 |

#### Input（从 State 读取）

```typescript
// 读取：state.user_input
interface GateNodeInput {
  user_input: {
    our_company: string;
    competitor_company: string;
    product: string;
    objective: string;
    optional?: {
      industry?: string;
      region?: string;
      product_type?: string;
      product_stage?: string;
      additional_context?: string;
    };
  };
}
```

#### Output（写入 State）

```typescript
// 写入：state.validated_input, state.current_phase
// 条件边依据：state.current_phase === "validated" | "validation_failed"

interface GateNodeOutput {
  validated_input: {
    is_valid: boolean;
    clean_values: {
      our_company: string;
      competitor_company: string;
      product: string;
      objective: "product_improvement" | "go_to_market" | "investment_due_diligence"
                 | "competitive_defense" | "positioning_switch" | "partnership_evaluation"
                 | "feature_benchmark";
      optional?: { /* 同上，清洗后 */ };
    };
    issues: Array<{
      field: string;
      message: string;
      severity: "error" | "warning";
    }>;
  };
  current_phase: "validated" | "validation_failed";
}
```

#### 校验规则

```
必填字段不能为空    → is_valid = false
objective 必须在枚举中 → is_valid = false
公司名 != 产品名（避免混淆） → warning
竞品 != 我方相同名称  → warning
```

#### 条件分支

```
condition: state.validated_input.is_valid
  ├── true  → 进入 plan_node (Phase → "planning")
  └── false → 进入 fail_node (Phase → "validation_failed")
```

---

### 3.2 `plan_node`（Planner Agent）

| 属性 | 定义 |
|------|------|
| **功能** | 理解分析目标 → 拆解维度 → 生成 Research Plan |
| **调用 LLM** | ✅ 一次 LLM 调用 |
| **调用 Tool** | 无外部 Tool，纯 LLM + 结构化解析 |

#### Input

```typescript
interface PlanNodeInput {
  // 从 state.validated_input 读取
  our_company: string;
  competitor_company: string;
  product: string;
  objective: string;
  optional_context?: string;
}
```

#### Output

```typescript
// 写入：state.research_plan, state.phase_history

interface PlanNodeOutput {
  research_plan: {
    objective: string;                              // 标准化后的目标
    analysis_scope: Array<                          // 需要分析的维度
      "positioning" | "users" | "features" | "ux" | "business"
      | "technology" | "growth" | "competitive_landscape"
      | "risks" | "strategy"
    >;
    research_tasks: Array<{                         // 搜索任务列表
      task_id: string;
      source_type: "web" | "app_store" | "social" | "news" | "github" | "ai_search";
      keywords: string[];
      priority: 1 | 2 | 3 | 4 | 5;
      dependencies: string[];                       // 前置 task_id
    }>;
    required_sources: string[];
    workflow: string[];                             // 推荐 Agent 顺序
    estimated_complexity: "simple" | "moderate" | "complex";
  };
  phase_record: {
    phase: "planned";
    duration_ms: number;
    status: "completed";
  };
}
```

#### 边

```
无条件边：plan_node → research_node（始终执行）
```

---

### 3.3 `research_node`（Research Agent）— 子图

Research 内部是一个 **嵌套 Sub-Graph**，包含并行搜索子节点。

#### 3.3.1 子图结构

```
                    ┌───────────────┐
                    │   dispatch_   │
                    │  research_tasks│
                    └───────┬───────┘
                            │
              ┌─────────────┼──────────────┐
              │             │              │
       ┌──────▼──────┐ ┌───▼────┐  ┌─────▼─────┐
       │ web_search  │ │ app_store│  │ social_    │
       │ subtask     │ │ subtask │  │ search_sub │
       └──────┬──────┘ └───┬────┘  └─────┬─────┘
              │             │              │
       ┌──────▼──────┐ ┌───▼────┐  ┌─────▼─────┐
       │ news_search │ │github_  │  │ ai_search  │
       │ subtask     │ │search   │  │ subtask    │
       └──────┬──────┘ └───┬────┘  └─────┬─────┘
              │             │              │
              └─────────────┼──────────────┘
                            │
                     ┌──────▼──────┐
                     │  aggregate_ │
                     │    evidence  │
                     │（去重+评分） │
                     └──────┬──────┘
                            │
                     ┌──────▼──────┐
                     │  quality_   │
                     │    check    │
                     └──────┬──────┘
                            │
                   ┌────────┴────────┐
                   │                 │
              [sufficient]     [insufficient]
                   │                 │
                   │           ┌─────▼──────┐
                   │           │ fallback_  │
                   │           │  strategy  │
                   │           └─────┬──────┘
                   │                 │
                   └────────┬────────┘
                            │
                     ┌──────▼──────┐
                     │ research_   │
                     │  complete   │
                     └─────────────┘
```

#### 3.3.2 主节点 Input

```typescript
interface ResearchNodeInput {
  // 从 state.research_plan 读取
  research_plan: {
    research_tasks: Array<{
      task_id: string;
      source_type: string;
      keywords: string[];
      priority: number;
      dependencies: string[];
    }>;
  };
  // 上下文
  our_company: string;
  competitor_company: string;
  product: string;
}
```

#### 3.3.3 子节点设计

| 子节点 | Input | 调用 Tool | Output |
|--------|-------|-----------|--------|
| **`dispatch_research_tasks`** | 从 research_plan 读取 task list | 无（仅拆分任务） | `subtasks: Array<{ task_id, source_type, keywords, status: "pending" }>` |
| **`web_search_subtask`** | `{ keywords, our_company, competitor, product }` | `WebSearch.search()` + `WebScraper.fetch()` | `{ source_type: "web", items: RawEvidence[], status: "success"|"failed" }` |
| **`app_store_subtask`** | `{ product_names }` | `AppStoreScraper.fetch()` | `{ source_type: "app_store", items: RawEvidence[] }` |
| **`social_search_subtask`** | `{ keywords, platforms: ["zhihu", "xiaohongshu"] }` | `SocialScraper.fetch()` | `{ source_type: "social", items: RawEvidence[] }` |
| **`news_search_subtask`** | `{ keywords }` | `NewsAPI.search()` | `{ source_type: "news", items: RawEvidence[] }` |
| **`github_search_subtask`** | `{ company_names }` | `GitHubScraper.search()` | `{ source_type: "github", items: RawEvidence[] }` |
| **`ai_search_subtask`** | `{ structured_questions }` | `AISearch.query()` | `{ source_type: "ai_search", items: RawEvidence[] }` |
| **`aggregate_evidence`** | 所有子节点输出 | `Deduplicator.deduplicate()` + `ConfidenceScorer.score()` | `aggregated: EvidenceBundle` |
| **`quality_check`** | aggregated EvidenceBundle | 无（仅检查覆盖率和置信度） | `quality: { sufficient: boolean, coverage: %, avg_confidence: % }` |
| **`fallback_strategy`** | `{ missing_areas, original_plan }` | `LLM.chat()` — 生成补充搜索策略 | `supplement_tasks: ResearchTask[]` → 重新 dispatch |

#### 3.3.4 子图内条件分支

```
condition: quality_check.quality.sufficient
  ├── true  → research_complete 节点
  └── false → fallback_strategy → 重新 dispatch（最多 1 次 fallback）
```

#### 3.3.5 Research 节点最终 Output（写入 State）

```typescript
// 写入：state.evidence_bundle, state.current_phase → "researched"

interface ResearchNodeOutput {
  evidence_bundle: EvidenceBundle;   // Schema 见 Architecture Design 7.3
  quality_report: {
    sources_attempted: number;
    sources_succeeded: number;
    total_evidence_items: number;
    coverage_by_dimension: Record<string, number>;  // % 每维度覆盖率
    avg_confidence: number;
    fallback_used: boolean;
    missing_data_warnings: string[];
  };
}
```

---

### 3.4 `compare_node`（Compare Agent）

| 属性 | 定义 |
|------|------|
| **功能** | 基于 Evidence，按维度对比差异 |
| **调用 LLM** | ✅ 一次 LLM 调用（多维度对比） |
| **约束** | 不能给建议，不能输出 SWOT，不能输出 Roadmap |

#### Input

```typescript
interface CompareNodeInput {
  // 从 state.evidence_bundle 读取
  evidence_bundle: EvidenceBundle;
  // 读取 Planner 的分析范围
  analysis_scope: string[];
  // 上下文
  our_company: string;
  competitor_company: string;
  product: string;
}
```

#### Output

```typescript
// 写入：state.gap_analysis, state.current_phase → "compared"

interface CompareNodeOutput {
  gap_analysis: GapAnalysis;         // Schema 见 Architecture Design 7.4
  // 附加元数据
  dimensions_analyzed: string[];
  dimensions_skipped: string[];      // 因证据不足跳过
  evidence_references_count: number;
}
```

#### 边

```
无条件边：compare_node → strategy_node（始终执行）
```

---

### 3.5 `strategy_node`（Strategy Agent）

| 属性 | 定义 |
|------|------|
| **功能** | SWOT → 机会 → 风险 → 产品建议 → Roadmap |
| **调用 LLM** | ✅ 一次 LLM 调用（较长的链式推理） |
| **HITL 预留** | **Level 1：Pass-through 模式**（默认）→ 自动执行 <br>**Level 2：Review Mode** → 暂停等待人类审核 Compare 结果后继续 |

#### Input

```typescript
interface StrategyNodeInput {
  // 从 state.gap_analysis 读取
  gap_analysis: GapAnalysis;
  // 可引用原始证据
  evidence_bundle: EvidenceBundle;
  // 上下文
  objective: string;
  product: string;
}
```

#### Output

```typescript
// 写入：state.strategic_insights, state.current_phase → "strategized"

interface StrategyNodeOutput {
  strategic_insights: StrategicInsights; // Schema 见 Architecture Design 7.5
  // 可信度自评
  confidence_summary: {
    overall: "high" | "medium" | "low";
    weaknesses: string[];
    data_gaps: string[];
  };
}
```

#### 边

```
无条件边：strategy_node → [HITL Checkpoint] → report_node
```

---

### 3.6 `report_node`（Report Agent）

| 属性 | 定义 |
|------|------|
| **功能** | 聚合 Research + Compare + Strategy → 按模板 → Markdown / HTML / Word |
| **调用 LLM** | ✅ 一次 LLM 调用（组装内容） |
| **调用 Tool** | `MarkdownRenderer.render()`、`HTMLRenderer.render()`、`WordExporter.export()` |
| **HITL 预留** | **Level 1：Default Template**（默认）→ 使用标准模板 <br>**Level 2：Custom Template** → 暂停让人类选择模板版本或调整章节顺序 |

#### Input

```typescript
interface ReportNodeInput {
  // 聚合所有先前结果
  evidence_bundle: EvidenceBundle;
  gap_analysis: GapAnalysis;
  strategic_insights: StrategicInsights;
  // 配置
  template_version: string;        // 默认 "v1"
  output_formats: Array<"markdown" | "html" | "docx">;  // 默认 ["markdown", "docx"]
  // 上下文
  objective: string;
  product: string;
  our_company: string;
  competitor_company: string;
}
```

#### Output

```typescript
// 写入：state.report_document, state.current_phase → "reported"

interface ReportNodeOutput {
  report_document: {
    formats: {
      markdown: string;             // 完整 Markdown
      html?: string;                // HTML 渲染
      docx_url?: string;            // Word 文件 URL
    };
    sections: Array<{
      title: string;
      content: string;
      order: number;
      word_count: number;
    }>;
    metadata: {
      total_word_count: number;
      generated_at: string;
      sources_count: number;
      template_used: string;
      llm_prompt_tokens: number;
      llm_completion_tokens: number;
    };
  };
}
```

#### 边

```
无条件边：report_node → review_node（始终执行）
```

---

### 3.7 `review_node`（Review Agent）

| 属性 | 定义 |
|------|------|
| **功能** | 完整性 / 逻辑 / 引用 / 重复 / 格式 / 中立性检查 |
| **调用 LLM** | ✅ 一次 LLM 调用（逐项检查）|
| **调用 Tool** | `TextAnalyzer.check_duplicates()`、`LinkValidator.validate()` |

#### Input

```typescript
interface ReviewNodeInput {
  // 从 state.report_document 读取
  report_document: ReportDocument;
  // 引用原始 evidence 做交叉核验
  evidence_bundle: EvidenceBundle;
  // 上下文
  objective: string;
  template_version: string;
}
```

#### Output

```typescript
// 写入：state.review_result, state.current_phase → "reviewed" | "review_failed"

interface ReviewNodeOutput {
  review_result: ReviewResult;       // Schema 见 Architecture Design 7.7
  // 简化版检查摘要
  passed_for_output: boolean;
  score: number;                     // 0-100
  check_summary: {
    completeness: boolean;
    logic: boolean;
    sources: boolean;
    duplication: boolean;
    format: boolean;
    neutrality: boolean;
    actionability: boolean;
  };
  issue_count: {
    critical: number;
    major: number;
    minor: number;
    suggestion: number;
  };
}
```

#### 条件分支

```
condition: review_result.passed_for_output
  ├── true  → finalize_node
  └── false → [检查 retry_counts["review_retry"]]
                ├── < 3 → report_node（退回修订）
                └── >= 3 → fail_node
```

---

### 3.8 `finalize_node`

| 属性 | 定义 |
|------|------|
| **功能** | 最终处理：持久化、生成下载链接、清理临时数据 |
| **调用 Tool** | `DB.save_report()`、`ObjectStore.upload()` |

#### Input

```typescript
interface FinalizeNodeInput {
  report_document: ReportDocument;
  task_id: string;
  // 完整执行轨迹
  phase_history: PhaseRecord[];
  total_duration_ms: number;
  llm_token_usage: object;
}
```

#### Output

```typescript
// 写入：state.final_report, state.current_phase → "completed"

interface FinalizeNodeOutput {
  final_report: {
    markdown: string;
    word_url: string | null;
    html: string | null;
  };
  execution_summary: {
    total_duration_ms: number;
    agents_executed: number;
    tokens_used: number;
    retries_used: number;
    human_interventions: number;
  };
}
```

#### 边

```
无条件边：finalize_node → END
```

---

### 3.9 `fail_node`（终端节点）

| 属性 | 定义 |
|------|------|
| **功能** | 处理所有不可恢复的错误，生成友好错误信息 |

#### Input

```typescript
interface FailNodeInput {
  errors: ErrorRecord[];
  current_phase: Phase;
  context: {
    stage: string;                  // 哪个节点失败
    code: string;                   // 错误码
    message: string;                // 用户可读
    retryable: boolean;
  };
}
```

#### Output

```typescript
// 写入：state.current_phase → "failed" | "validation_failed"

interface FailNodeOutput {
  error_response: {
    code: string;
    message: string;                // 用户友好的中文错误
    detail: string;                 // 技术细节（内部日志）
    suggestion: string;             // 用户下一步操作建议
    failed_at_phase: string;
    partial_report_available: boolean;  // 是否有部分结果可查看
  };
}
```

#### 边

```
无条件边：fail_node → END
```

---

## 4. 完整的图定义（Graph Definition）

```typescript
// ——— 节点注册 ———
const graph = new StateGraph<WorkflowState>({
  channels: {
    user_input:       { reducer: "replace" },
    validated_input:  { reducer: "replace" },
    research_plan:    { reducer: "replace" },
    evidence_bundle:  { reducer: "replace" },
    gap_analysis:     { reducer: "replace" },
    strategic_insights: { reducer: "replace" },
    report_document:  { reducer: "replace" },
    review_result:    { reducer: "replace" },
    current_phase:    { reducer: "replace" },
    phase_history:    { reducer: "push" },
    progress:         { reducer: "replace" },
    errors:           { reducer: "push" },
    retry_counts:     { reducer: "update" },
    stream_events:    { reducer: "push" },
    // ... 其余字段
  }
});

// ——— 节点注册 ———
graph.addNode("validate_input_node", validateInputFn);
graph.addNode("plan_node", planFn);
graph.addNode("research_node", researchSubGraph);     // 子图
graph.addNode("compare_node", compareFn);
graph.addNode("strategy_node", strategyFn);
graph.addNode("report_node", reportFn);
graph.addNode("review_node", reviewFn);
graph.addNode("finalize_node", finalizeFn);
graph.addNode("fail_node", failFn);

// ——— 边 ———
// START → validate
graph.setEntryPoint("validate_input_node");

// validate → 分支
graph.addConditionalEdges("validate_input_node", (state) => {
  if (state.validated_input.is_valid) return "plan_node";
  return "fail_node";
});

// 主线
graph.addEdge("plan_node", "research_node");
graph.addEdge("research_node", "compare_node");
graph.addEdge("compare_node", "strategy_node");
graph.addEdge("strategy_node", "report_node");
graph.addEdge("report_node", "review_node");

// review → 分支
graph.addConditionalEdges("review_node", (state) => {
  if (state.review_result.passed_for_output) return "finalize_node";
  const retryCount = state.retry_counts["report_retry"] || 0;
  if (retryCount < 3) return "report_node";         // 退回修订
  return "fail_node";
});

graph.addEdge("finalize_node", END);
graph.addEdge("fail_node", END);
```

---

## 5. 条件分支总表

| 源节点 | 条件依据 | 目标 1 | 目标 2 | 目标 3 |
|--------|----------|--------|--------|--------|
| `validate_input_node` | `state.validated_input.is_valid` | `plan_node` (true) | `fail_node` (false) | — |
| `research_node` (子图) | `quality_check.sufficient` | `research_complete` (true) | `fallback_strategy` (false) | — |
| `review_node` | `state.review_result.passed_for_output` | `finalize_node` (true) | `report_node` (< 3 retries) | `fail_node` (>= 3 retries) |
| `retry_counter` | `retry_counts["report_retry"]` | `report_node` (< 3) | `fail_node` (>= 3) | — |

---

## 6. Error Handling

### 6.1 错误分类体系

```typescript
type ErrorCategory =
  | "INPUT_ERROR"       // 输入校验失败 → 不可恢复，直接返回 400
  | "LLM_ERROR"         // LLM 调用失败（超时、解析失败、内容拒绝）
  | "TOOL_ERROR"        // 外部 Tool 调用失败（搜索 API 500、网络断开）
  | "RATE_LIMIT"        // 被数据源限流
  | "TIMEOUT"           // 超过单节点超时限制
  | "NO_DATA"           // 搜索无结果
  | "PARSE_ERROR"       // LLM 输出结构化解析失败
  | "STATE_CORRUPTION"  // State 数据一致性异常
  | "CANCELLED"         // 用户取消
```

### 6.2 每个节点的错误处理策略

| 节点 | 错误类型 | 行为 | 恢复策略 |
|------|----------|------|----------|
| **validate_input_node** | INPUT_ERROR | → fail_node（400） | 不可恢复 |
| **plan_node** | LLM_ERROR | 重试（最多 2 次） | 简化 Prompt 重试 |
| | PARSE_ERROR | 重试（最多 2 次） | 调整 output format instruction |
| **research_node** (子节点) | TOOL_ERROR | 标记该源为 failed，继续其他源 | Graceful Degradation |
| | RATE_LIMIT | 退避 30s 后重试（最多 2 次） | Exponential Backoff |
| | TIMEOUT | 标记该源为 timeout，继续其他源 | 降级为非必需源 |
| | NO_DATA | 标记该维度为 no_data | 报告中标注"暂无公开数据" |
| **compare_node** | LLM_ERROR | 重试（最多 2 次） | 分批对比，减少单次输入量 |
| | PARSE_ERROR | 重试（最多 2 次） | 约束 output format |
| **strategy_node** | LLM_ERROR | 重试（最多 2 次） | 分段推理 |
| | PARSE_ERROR | 重试（最多 2 次） | 约束 output format |
| **report_node** | LLM_ERROR | 重试（最多 2 次） | 分章节生成 |
| | TOOL_ERROR (Word) | 跳过 Word 导出 | 仅输出 Markdown |
| **review_node** | LLM_ERROR | 重试（最多 2 次） | 按单项检查逐个重试 |
| **finalize_node** | DB_ERROR | 重试（最多 3 次） | 写入本地临时文件 |

### 6.3 错误恢复流程图

```
Node Start
  │
  ├── try { execute node logic }
  │
  ├── catch (error)
  │     │
  │     ├── error.category === "RATE_LIMIT"
  │     │     └── wait(backoff_ms) → retry (max 2)
  │     │
  │     ├── error.category === "TIMEOUT" || "LLM_ERROR" || "PARSE_ERROR"
  │     │     └── retry (max 2) → simplify input → retry (max 1)
  │     │
  │     ├── error.category === "TOOL_ERROR"
  │     │     └── mark source as degraded → continue
  │     │
  │     ├── error.category === "NO_DATA"
  │     │     └── mark dimension as no_data → continue
  │     │
  │     ├── error.category === "STATE_CORRUPTION"
  │     │     └── → fail_node (不可恢复)
  │     │
  │     └── error.category === "CANCELLED"
  │           └── → fail_node (用户主动取消)
  │
  └── after all retries exhausted
        └── push to state.errors → → fail_node
```

### 6.4 全局超时

```
─ 单节点软超时：  30s  → 触发重试
─ 单节点硬超时：  60s  → 节点失败
─ 整体流程超时：  5min → 强制终止 → fail_node
                  （对齐 PRD：3 分钟内生成报告，预留冗余）
─ 用户取消：      任何阶段 → 立即终止 → fail_node (CANCELLED)
```

---

## 7. Retry Strategy

### 7.1 重试策略总表

| 层级 | 重试对象 | 最大次数 | 退避策略 | 退避公式 |
|------|---------|----------|---------|----------|
| **L1** | LLM 调用 | 3 | Exponential Backoff + Jitter | `min(2^retry * 1000 + random(0,1000), 15000)ms` |
| **L2** | Agent 节点 | 2 | Fixed Interval | 5000ms |
| **L3** | Review 失败退回 Report | 3 (累计) | Fixed Interval | 10000ms（给 LLM 冷却时间）|
| **L4** | DB/Tool 调用 | 3 | Exponential Backoff | `min(2^retry * 500, 10000)ms` |
| **L5** | 整体流程 | 1 | N/A（用户手动重试） | 用户点击"重新生成" |

### 7.2 重试计数器定义

```typescript
// state.retry_counts 的结构
interface RetryCounts {
  // LLM 级别
  "llm:plan_node": number;           // default 0
  "llm:research_fallback": number;   // default 0
  "llm:compare_node": number;        // default 0
  "llm:strategy_node": number;       // default 0
  "llm:report_node": number;         // default 0
  "llm:review_node": number;         // default 0

  // 节点级别
  "node:plan_node": number;
  "node:research_node": number;
  "node:compare_node": number;
  "node:strategy_node": number;
  "node:report_node": number;
  "node:review_node": number;
  "node:finalize_node": number;

  // Review 退回级别
  "report_retry": number;            // Review 不过退回 Report 的累计次数
}
```

### 7.3 重试副作用

每次重试时同步更新以下 State：

```typescript
// 写入到一个 ErrorRecord
{
  code: "LLM_ERROR" | "TIMEOUT" | "RATE_LIMIT" | ...,
  message: string,
  node: "report_node",
  timestamp: ISO8601,
  retryable: true,
  retry_count: 2,         // 第几次重试
  resolved: false
}
```

---

## 8. Streaming Strategy

### 8.1 流式事件通道设计

```
Frontend ←── SSE (Server-Sent Events) ──── Backend
           ←── 或 WebSocket ───────────────
           URL: GET /api/reports/:task_id/stream
```

### 8.2 事件类型与触发时机

| 事件类型 | 触发时机 | Payload | 前端行为 |
|----------|---------|---------|---------|
| `phase.entered` | 进入新节点时 | `{ phase: "researching", label: "正在收集公开信息..." }` | 更新阶段指示器 |
| `phase.completed` | 节点完成时 | `{ phase: "researched", duration_ms: 12345 }` | 更新进度条 |
| `phase.failed` | 节点失败时 | `{ phase: "researching", error: "...", retrying: true }` | 显示重试状态 |
| `progress.update` | 子任务完成时 | `{ progress: 45.5, label: "正在分析竞品功能..." }` | 更新百分比 |
| `agent.heartbeat` | 每 5 秒（LLM 调用中） | `{ phase: "strategizing", message: "正在推理 SWOT..." }` | 保持连接活跃 |
| `intermediate.result` | 关键子结果生成时 | `{ type: "search_result", source: "zhihu", items_count: 12 }` | 可选展示中间结果 |
| `llm.token` | **仅 Report 节点** | `{ content: "新增" }` | 实时打字机效果（仅报告正文）|
| `human.checkpoint.required` | 需要人类决策时 | `{ checkpoint_id, question, options }` | 暂停，弹出决策对话框 |
| `human.decision.received` | 收到人类决策时 | `{ checkpoint_id, decision: "..." }` | 继续流程 |
| `error` | 非致命错误 | `{ code: "RATE_LIMIT", message: "小红书限流，已跳过" }` | 显示警告（不阻塞） |
| `warning` | 数据质量问题 | `{ dimension: "business", message: "商业模式数据较少" }` | 显示提示标记 |
| `completed` | 流程完成 | `{ report_id, formats: [...] }` | 跳转报告页 |
| `failed` | 流程失败 | `{ code, message, suggestion }` | 显示错误页 |

### 8.3 流式事件队列管理

```typescript
interface StreamManager {
  // 事件缓冲
  event_queue: StreamEvent[];
  flush_interval_ms: 200;           // 200ms 批量推送

  // 推送方式
  transport: "sse" | "websocket";

  // 连接管理
  connected_clients: Map<string, ClientConnection>;
  max_connections_per_task: 1;

  // 客户端断线重连
  replay_on_reconnect: true;         // 重新推送历史事件
  event_history_ttl_minutes: 30;     // 事件保留 30 分钟
}
```

### 8.4 前端进度映射

```
进度百分比           ── 映射到 ──    Phase
0% ~ 5%             ──            validating / planned
5% ~ 25%            ──            researching（含子任务逐步累加）
25% ~ 45%           ──            comparing
45% ~ 65%           ──            strategizing
65% ~ 85%           ──            reporting
85% ~ 95%           ──            reviewing
95% ~ 100%          ──            finalizing
```

Research 子任务内部的进度分配：

```
总 progress 区间：5% → 25%（20% 跨度）
分配方式：
  web_search_subtask:    30% 权重（6% 进度）
  app_store_subtask:     15% 权重（3% 进度）
  social_search_subtask: 20% 权重（4% 进度）
  news_search_subtask:   15% 权重（3% 进度）
  github_search_subtask: 5% 权重（1% 进度）
  ai_search_subtask:     15% 权重（3% 进度）
  aggregate + quality:   预留缓冲
```

---

## 9. Human-in-the-Loop 预留位置

### 9.1 两个 HITL Checkpoint

#### Checkpoint A：Strategy 之前（证据审核）

```
位置：compare_node → strategy_node 之间
节点名称：human_checkpoint_strategy

触发条件：
  Level 1 (默认)：自动跳过，不暂停
  Level 2 (可选)：state.human_checkpoints 中有 pending 请求时暂停

人类可做的决策：
  1. 「证据充分，继续分析」 → 默认，自动通过
  2. 「补充分析维度」 → 添加分析维度，重新触发 Research
  3. 「调整分析重点」 → 修改 objective → 重新 Planner
  4. 「查看原始证据」 → 透传证据摘要给前端，人类确认后继续

暂停 UI：
  前端弹出侧边栏，展示：
  - 已收集的证据摘要（按维度分组）
  - 每维度的可信度评分
  - 缺失数据的维度标记
  - 四个决策按钮
```

#### Checkpoint B：Report 之前（模板选择）

```
位置：strategy_node → report_node 之间
节点名称：human_checkpoint_report

触发条件：
  Level 1 (默认)：使用默认模板（v1）
  Level 2 (可选)：暂停让人类选择

人类可做的决策：
  1. 「使用默认模板」 → 自动继续
  2. 「选择模板版本」 → 从预置模板列表中选择
  3. 「自定义报告章节」 → 选择包含/排除哪些分析维度
  4. 「添加备注」 → 在报告中插入人工注记

暂停 UI：
  前端弹出模板选择器：
  - 模板版本选择（v1 / v2...）
  - 章节开关（10 个维度的 checkbox）
  - 自定义备注输入框
```

### 9.2 Checkpoint State 设计

```typescript
// 在 WorkflowState 中已预留：
state.human_checkpoints: HumanCheckpoint[];
state.pending_human_decision: HumanDecisionRequest | null;

// 当节点运行到 Checkpoint 时：
async function humanCheckpointNode(state: WorkflowState) {
  if (state.human_checkpoints.length === 0) {
    // Level 1：自动通过
    return { next: auto_next_node };
  }

  // Level 2：创建决策请求
  const request: HumanDecisionRequest = {
    checkpoint_id: uuid(),
    question: "证据收集完成，是否继续竞品分析？",
    context: { /* evidence summary */ },
    timeout_minutes: 10,            // 10分钟无响应 → 自动走默认路径
    options: [
      { id: "proceed", label: "继续分析", description: "按原计划进行", default: true },
      { id: "supplement", label: "补充搜索", description: "针对缺失维度补充数据" },
      { id: "adjust_scope", label: "调整分析范围", description: "修改 analysis_scope" },
    ]
  };

  state.pending_human_decision = request;

  // 暂停执行，等待外部事件
  // ... Graph 在此 suspend，由外部 WebSocket 消息 resume
  return GRAPH.SUSPEND;
}

// 外部收到人类决策后：
function onHumanDecision(taskId: string, decision: HumanDecision) {
  const state = loadState(taskId);
  state.pending_human_decision = null;
  state.human_checkpoints.push({
    checkpoint_id: decision.checkpoint_id,
    node: state.current_phase,
    requested_at: "...",
    context: { /* ... */ },
    decision: decision,
    resolved_at: now(),
  });

  // 根据决策路由到不同节点
  switch (decision.option_id) {
    case "proceed":      return resumeGraph(taskId, "strategy_node");
    case "supplement":   return resumeGraph(taskId, "research_node");
    case "adjust_scope": return resumeGraph(taskId, "plan_node");
  }
}

// 超时处理：
// 10 分钟无响应 → 自动选择 default: true 的选项 → 继续执行
```

### 9.3 HITL 数据流

```
Frontend                    Backend                        Graph
   │                          │                              │
   │  POST /api/reports       │                              │
   │─────────────────────────>│                              │
   │                          │  创建任务, 开始 Graph         │
   │                          │──────────────────────────────│
   │                          │                              │
   │                          │  ... nodes execute ...       │
   │                          │                              │
   │                          │  到达 HITL Checkpoint        │
   │                          │◄─────────────────────────────│
   │                          │                              │
   │  SSE: human.checkpoint   │                              │
   │<─────────────────────────│                              │
   │                          │                              │
   │  ┌──────────────────┐    │                              │
   │  │ 用户看到对话框    │    │                              │
   │  │ 选择"补充搜索"   │    │                              │
   │  └────────┬─────────┘    │                              │
   │           │              │                              │
   │  PATCH /api/tasks/:id/decision                         │
   │  { checkpoint_id, option_id: "supplement", comment }   │
   │─────────────────────────>│                              │
   │                          │  resumeGraph("research_node")│
   │                          │──────────────────────────────│
   │                          │                              │
```

---

## 10. Workflow 执行引擎摘要

```
┌──────────────────────────────────────────────────────────────────┐
│                   Workflow Execution Contract                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Input:  UserInput (JSON)                                         │
│  Output: ReportDocument + ExecutionSummary (JSON)                 │
│  Max Duration: 5 minutes                                          │
│  Max Retries: 3 per critical node, 1 for finalize                 │
│  Streaming: SSE on GET /api/reports/:id/stream                    │
│  State Persistence: PostgreSQL + Redis                            │
│  State Checkpoints: After every node (for resume on crash)        │
│  HITL Checkpoints: 2 (evidence review, template selection)        │
│  Error Recovery: Graceful degradation + Exponential backoff       │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

*文档版本：v1.0 | 生成日期：2026-07-17 | 基于 Architecture Design v1.0*
*设计范式：LangGraph StateGraph + SubGraph + Conditional Edges*
