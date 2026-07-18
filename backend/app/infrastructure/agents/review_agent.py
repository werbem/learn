"""Review Agent — LLM-powered quality assurance.

Checks report quality across 7 dimensions:
  evidence_consistency, hallucination, logic_consistency,
  completeness, recommendation_quality, data_quality, writing_quality

Does NOT regenerate content. Only flags issues.
"""

from __future__ import annotations

import json
import re

from app.application.dto.agent_dto import (
    ReviewInput,
    ReviewIssue,
    ReviewOutput,
    ReviewResult,
)
from app.config.constants import Phase
from app.infrastructure.agents.base import AgentContext, AgentResult, BaseAgent
from app.infrastructure.agents.review_prompt import (
    SYSTEM_PROMPT,
    build_review_prompt,
)
from app.infrastructure.llm.client import llm_client


class ReviewAgent(BaseAgent[ReviewInput, ReviewOutput]):

    @property
    def agent_name(self) -> str:
        return "review"

    @property
    def phase(self) -> Phase:
        return Phase.REVIEWING

    async def arun(self, ctx: AgentContext, input_data: ReviewInput) -> AgentResult:
        report_data = input_data.report_document
        eb = input_data.evidence_bundle

        # ── Extract Markdown report ──
        report_md = report_data.formats.markdown or ""
        if not report_md:
            return AgentResult(
                success=False,
                error="报告为空，无法审查",
            )

        # ── Serialize evidence for LLM ──
        evidence_items = []
        for item in eb.evidence_items[:30]:
            evidence_items.append({
                "id": item.id,
                "source": item.source,
                "title": item.title,
                "summary": item.content[:150] if item.content else "",
            })
        evidence_json = json.dumps(evidence_items, ensure_ascii=False, indent=2)

        # ── Call LLM ──
        try:
            result = await llm_client.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=build_review_prompt(
                    markdown_report=report_md,
                    objective=input_data.objective,
                    evidence_json=evidence_json,
                ),
                response_model=None,
                temperature=0.3,
            )
        except Exception as e:
            return AgentResult(
                success=False,
                error=f"LLM 调用失败: {e}",
            )

        # ── Parse JSON ──
        data = self._parse_json(result.content or "")
        if not data:
            return AgentResult(
                success=False,
                error="LLM 返回格式异常",
            )

        # ── Map to DTOs ──
        score = max(0, min(100, int(data.get("score", 75))))
        status = data.get("status", "PASS")
        checks_raw = data.get("checks", {})
        issues_raw = data.get("issues", [])
        suggestions = data.get("suggestions", [])

        # Map checks
        check_summary = {}
        checks_flat = {
            "completeness": False,
            "logic": False,
            "sources": False,
            "duplication": False,
            "format": False,
            "neutrality": False,
            "actionability": False,
        }

        # Map 7 dimensions to existing check keys
        for dim, key in [
            ("completeness", "completeness"),
            ("logic_consistency", "logic"),
            ("evidence_consistency", "sources"),
            ("writing_quality", "duplication"),
            ("hallucination", "neutrality"),
            ("data_quality", "format"),
            ("recommendation_quality", "actionability"),
        ]:
            check = checks_raw.get(dim, {})
            passed = check.get("passed", True) if isinstance(check, dict) else True
            checks_flat[key] = passed
            check_summary[dim] = passed

        # Map issues
        issues: list[ReviewIssue] = []
        high_count = data.get("high_count", 0)
        medium_count = data.get("medium_count", 0)
        low_count = data.get("low_count", 0)

        for issue in issues_raw:
            if not isinstance(issue, dict):
                continue
            sev_map = {"HIGH": "critical", "MEDIUM": "major", "LOW": "minor"}
            severity = sev_map.get(issue.get("severity", "").upper(), "minor")
            issues.append(ReviewIssue(
                severity=severity,
                category=issue.get("category", ""),
                section=issue.get("section", "") or issue.get("location", ""),
                description=issue.get("description", "") or issue.get("issue", ""),
                suggestion=issue.get("suggestion", ""),
            ))

        # Count from issues if not provided
        if not high_count and not medium_count and not low_count and issues:
            high_count = sum(1 for i in issues if i.severity == "critical")
            medium_count = sum(1 for i in issues if i.severity == "major")
            low_count = sum(1 for i in issues if i.severity == "minor")

        # Determine final status
        passed_for_output = status == "PASS" and high_count == 0

        # Create revision suggestions from suggestions + issues
        revision_suggestions: list[dict] = []
        for s in suggestions:
            if isinstance(s, str):
                revision_suggestions.append({"suggestion": s})
            elif isinstance(s, dict):
                revision_suggestions.append(s)

        review_result = ReviewResult(
            passed=passed_for_output,
            score=score,
            checks=checks_flat,
            issues=issues,
            revision_suggestions=revision_suggestions,
            passed_for_output=passed_for_output,
        )

        output = ReviewOutput(
            review_result=review_result,
            passed_for_output=passed_for_output,
            score=score,
            check_summary=check_summary,
            issue_count={
                "critical": high_count,
                "major": medium_count,
                "minor": low_count,
                "suggestion": data.get("low_count", 0),
            },
        )

        return AgentResult(success=True, output=output)

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        """Parse JSON from LLM response, handling code fences and truncation."""
        text = raw.strip()
        if not text:
            return None

        # Strip code fences
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        # Try direct parse
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

        # Fallback: regex search for JSON
        try:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                data = json.loads(m.group())
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, Exception):
            pass

        return None
