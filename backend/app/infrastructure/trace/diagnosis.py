"""Failure diagnosis engine.

Analyzes AnalysisTrace records to produce structured FailureDiagnosis
when an AI workflow task fails. Leverages error messages, input/output
snapshots, and trace patterns to pinpoint root causes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.trace.collector import TraceCollector
from app.infrastructure.trace.model import AnalysisTrace, TraceStatus


# ── Error type enumeration ──

ERROR_TYPE_MAP: dict[str, str] = {
    "input": "INPUT_ERROR",
    "validate": "INPUT_ERROR",
    "validation": "INPUT_ERROR",
    "tavily": "SEARCH_ERROR",
    "search": "SEARCH_ERROR",
    "rate_limit": "SEARCH_ERROR",
    "play": "SEARCH_ERROR",
    "appstore": "SEARCH_ERROR",
    "social": "SEARCH_ERROR",
    "llm": "LLM_ERROR",
    "openai": "LLM_ERROR",
    "api_error": "LLM_ERROR",
    "json_schema": "SCHEMA_ERROR",
    "schema": "SCHEMA_ERROR",
    "validationerror": "SCHEMA_ERROR",
    "timeout": "TIMEOUT",
    "time": "TIMEOUT",
    "empty": "OUTPUT_ERROR",
    "output": "OUTPUT_ERROR",
    "result": "OUTPUT_ERROR",
    "index": "LLM_ERROR",
    "keyerror": "LLM_ERROR",
    "attributeerror": "LLM_ERROR",
    "connection": "SEARCH_ERROR",
}


# ── Agent to stage mapping ──

AGENT_TO_STAGE: dict[str, str] = {
    "gate": "gate",
    "planner": "planner",
    "research": "research",
    "compare": "compare",
    "strategy": "strategy",
    "report": "report",
    "review": "review",
}

# ── Suggestion templates per error type per agent ──

SUGGESTIONS: dict[str, dict[str, str]] = {
    "search_error": {
        "research": "搜索未返回结果，建议：1) 增加搜索关键词 2) 更换搜索源 3) 检查 Tavily API 配额",
        "default": "搜索工具异常，建议检查 API key 和网络连接",
    },
    "llm_error": {
        "planner": "LLM 生成研究计划失败，建议检查 API key 和 model 配置",
        "research": "LLM 提取证据失败，可能返回了不支持的格式",
        "compare": "LLM 对比分析失败，建议简化输入数据",
        "strategy": "LLM 策略分析失败，建议增加证据数量",
        "report": "LLM 报告生成失败，建议：1) 检查 prompt 长度 2) 降低输出长度 3) 重新执行",
        "review": "LLM 审查失败，建议重试",
        "default": "LLM 调用失败，建议检查 API 配置和网络连接",
    },
    "schema_error": {
        "default": "数据格式验证失败，Agent 输出未符合预期 Schema，可能需调整 Prompt",
    },
    "input_error": {
        "gate": "输入参数不合法，请检查公司名、竞品名、产品名是否填写完整",
        "default": "输入参数异常，建议检查请求格式",
    },
    "timeout": {
        "default": "操作超时，建议：1) 减少搜索数量 2) 降低报告长度 3) 调整 timeout 配置",
    },
    "output_error": {
        "strategy": "Strategy Agent 输出为空，建议：1) 增加证据数据 2) 重新执行 Strategy Agent",
        "report": "Report Agent 输出为空，建议：1) 检查上游数据 2) 重新执行 Report Agent",
        "default": "Agent 输出为空，建议检查上游数据完整性",
    },
}


# ── Output model ──

@dataclass
class ErrorDetail:
    message: str = ""
    code: str = ""
    location: str = ""


@dataclass
class FailureDiagnosis:
    task_id: str
    failed_stage: str = ""
    failed_agent: str = ""
    error_type: str = "LLM_ERROR"
    error_detail: ErrorDetail = field(default_factory=ErrorDetail)
    root_cause: str = ""
    suggestion: str = ""
    retry_available: bool = True
    related_traces: list[str] = field(default_factory=list)
    diagnosed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "failed_stage": self.failed_stage,
            "failed_agent": self.failed_agent,
            "error_type": self.error_type,
            "error_detail": {
                "message": self.error_detail.message,
                "code": self.error_detail.code,
                "location": self.error_detail.location,
            },
            "root_cause": self.root_cause,
            "suggestion": self.suggestion,
            "retry_available": self.retry_available,
            "related_traces": self.related_traces,
            "diagnosed_at": self.diagnosed_at,
        }


# ── Engine ──

class DiagnosisEngine:
    """Rule-based diagnosis engine for failed analysis tasks.

    Analyzes failed traces to produce structured diagnoses.
    """

    def __init__(self, collector: TraceCollector):
        self.collector = collector

    def diagnose(self, task_id: str) -> FailureDiagnosis:
        """Analyze failed traces and produce a diagnosis."""
        failed_traces = self.collector.get_failed(task_id)
        diagnosis = FailureDiagnosis(
            task_id=task_id,
            diagnosed_at=datetime.now(timezone.utc).isoformat(),
        )

        if not failed_traces:
            diagnosis.root_cause = "无失败 trace 记录，任务可能在 trace 初始化前失败"
            diagnosis.error_type = "LLM_ERROR"
            diagnosis.suggestion = "请重新创建任务，如持续失败请检查服务状态"
            return diagnosis

        # Focus on the LAST failed trace (deepest failure in the chain)
        last_failed = failed_traces[-1]

        diagnosis.related_traces = [t.trace_id for t in failed_traces]
        diagnosis.failed_stage = last_failed.stage
        diagnosis.failed_agent = last_failed.agent_name

        # Error detail from trace
        diagnosis.error_detail = ErrorDetail(
            message=last_failed.error or "未知错误",
            code=last_failed.status.value,
            location=f"{last_failed.stage}/{last_failed.agent_name}" if last_failed.agent_name else last_failed.stage,
        )

        # ── Classify error type ──
        error_msg = (last_failed.error or "").lower()
        diagnosis.error_type = self._classify_error(error_msg, last_failed)

        # ── Determine root cause ──
        diagnosis.root_cause = self._determine_root_cause(
            diagnosis.error_type, last_failed, error_msg
        )

        # ── Check input/output snapshots for integrity ──
        diagnosis = self._check_snapshot_integrity(diagnosis, last_failed, failed_traces)

        # ── Generate suggestion ──
        diagnosis.suggestion = self._generate_suggestion(
            diagnosis.error_type, diagnosis.failed_agent
        )

        # ── Determine retry availability ──
        diagnosis.retry_available = self._can_retry(diagnosis.error_type, error_msg)

        return diagnosis

    def _classify_error(self, error_msg: str, trace: AnalysisTrace) -> str:
        """Classify error based on message patterns."""
        error_lower = error_msg.lower()

        for pattern, error_type in ERROR_TYPE_MAP.items():
            if pattern in error_lower:
                return error_type

        # Check snapshots for additional clues
        metadata = trace.metadata or {}

        # If input snapshot shows empty data
        inp = metadata.get("input_snapshot", {})
        if isinstance(inp, dict) and inp.get("size_chars", 0) == 0:
            return "INPUT_ERROR"

        # If output snapshot shows empty data but no error message
        out = metadata.get("output_snapshot", {})
        if isinstance(out, dict) and out.get("size_chars", 0) == 0 and not error_msg:
            return "OUTPUT_ERROR"

        return "LLM_ERROR"  # Default

    def _determine_root_cause(
        self, error_type: str, trace: AnalysisTrace, error_msg: str
    ) -> str:
        """Determine the root cause based on error type and context."""
        agent = trace.agent_name or "unknown"

        cause_map = {
            "SEARCH_ERROR": f"搜索工具 ({agent}) 调用失败: {error_msg[:150]}" if "tavily" in error_msg else f"外部数据源无结果: {error_msg[:150]}",
            "LLM_ERROR": f"LLM 调用 ({agent}) 失败: {error_msg[:150]}" if error_msg else f"LLM 调用 ({agent}) 未能返回有效结果",
            "SCHEMA_ERROR": f"{agent} Agent 输出格式不匹配预期 Schema",
            "INPUT_ERROR": f"输入参数校验失败: {error_msg[:150]}" if error_msg else "输入数据为空或格式不正确",
            "TIMEOUT": f"{agent} Agent 执行超时: {error_msg[:150]}" if error_msg else f"{agent} Agent 操作超时",
            "OUTPUT_ERROR": f"{agent} Agent 输出为空或无效",
        }

        return cause_map.get(error_type, f"未知错误: {error_msg[:150]}")

    def _check_snapshot_integrity(
        self, diagnosis: FailureDiagnosis, trace: AnalysisTrace, all_failed: list[AnalysisTrace]
    ) -> FailureDiagnosis:
        """Check input/output snapshots for data integrity issues."""
        metadata = trace.metadata or {}

        # Check for upstream failures (cascading)
        if len(all_failed) > 1:
            prev_failed = all_failed[-2] if len(all_failed) >= 2 else None
            if prev_failed and prev_failed.stage == "agent":
                diagnosis.root_cause = (
                    f"上游 Agent ({prev_failed.agent_name}) 失败导致 {trace.agent_name} 无法正常执行"
                )
                # Update suggestion to fix upstream first
                diagnosis.suggestion = (
                    f"先修复上游 {prev_failed.agent_name} Agent 的问题，然后重新执行整个流程"
                )

        # Check output snapshot integrity
        out_snap = metadata.get("output_snapshot", {})
        if isinstance(out_snap, dict):
            if out_snap.get("success") == False:
                diagnosis.error_detail.message = out_snap.get("error", diagnosis.error_detail.message)

        return diagnosis

    def _generate_suggestion(self, error_type: str, agent_name: str) -> str:
        """Generate actionable suggestions based on error type and agent."""
        key = error_type.lower()
        suggestions = SUGGESTIONS.get(key, {})
        return suggestions.get(agent_name, suggestions.get("default", "请检查相关 Agent 的输入数据和运行环境"))

    @staticmethod
    def _can_retry(error_type: str, error_msg: str) -> bool:
        """Determine if retry is safe."""
        non_retryable = {"input_error"}
        if error_type.lower() in non_retryable:
            return False
        if "rate_limit" in error_msg.lower():
            return True  # Retry after wait
        return True


# ── Convenience function ──

def diagnose_task(task_id: str, collector: TraceCollector) -> FailureDiagnosis:
    """Quick diagnosis for a task."""
    engine = DiagnosisEngine(collector)
    return engine.diagnose(task_id)
