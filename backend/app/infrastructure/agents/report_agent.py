"""Report Agent — LLM-powered structured report generation.

Uses real LLM to organize evidence, gap analysis, and strategy insights
into a well-formatted competitive analysis report.

Formats: Markdown (LLM), HTML + Word (export tools)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any

from app.application.dto.agent_dto import (
    EvidenceBundleDTO,
    GapAnalysis,
    ReportDocument,
    ReportFormatsDTO,
    ReportInput,
    ReportOutput,
    ReportSectionDTO,
    StrategicInsights,
)
from app.config.constants import Phase
from app.config.settings import settings
from app.infrastructure.agents.base import AgentContext, AgentResult, BaseAgent
from app.infrastructure.agents.report_prompt import (
    SYSTEM_PROMPT,
    build_report_prompt,
)
from app.infrastructure.llm.client import llm_client
from app.infrastructure.tools.export_tool import (
    HTMLBuilder,
    MarkdownBuilder,
    WordBuilder,
)

# ── Report section definitions (for SectionDTO extraction) ──
SECTION_DEFS = [
    ("一、Executive Summary", "executive_summary"),
    ("二、产品概览与定位", "positioning"),
    ("三、目标用户与画像", "users"),
    ("四、核心功能对比", "features"),
    ("五、用户体验与设计", "ux"),
    ("六、商业模式与收费", "business"),
    ("七、技术架构与能力", "technology"),
    ("八、增长策略与市场", "growth"),
    ("九、竞争格局", "competitive_landscape"),
    ("十、SWOT 分析", "swot_section"),
    ("十一、关键指标对比", "metrics"),
    ("十二、战略建议", "strategy"),
    ("十三、实施路线图", "roadmap"),
]


class ReportAgent(BaseAgent[ReportInput, ReportOutput]):

    @property
    def agent_name(self) -> str:
        return "report"

    @property
    def phase(self) -> Phase:
        return Phase.REPORTING

    async def arun(self, ctx: AgentContext, input_data: ReportInput) -> AgentResult:
        eb = input_data.evidence_bundle
        gap = input_data.gap_analysis
        insights = input_data.strategic_insights

        # ── Serialize input data for LLM ──
        evidence_json = self._serialize_evidence(eb)
        gap_json = self._serialize_gap(gap)
        strategy_json = self._serialize_strategy(insights)

        # ── Call LLM ──
        try:
            result = await llm_client.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=build_report_prompt(
                    our_company=input_data.our_company,
                    competitor_company=input_data.competitor_company,
                    product=input_data.product,
                    objective=input_data.objective,
                    evidence_json=evidence_json,
                    gap_json=gap_json,
                    strategy_json=strategy_json,
                ),
                response_model=None,
                temperature=0.5,
            )
        except Exception as e:
            return AgentResult(
                success=False,
                error=f"LLM 调用失败: {e}",
            )

        markdown_content = (result.content or "").strip()
        if not markdown_content or markdown_content.startswith("["):
            return AgentResult(
                success=False,
                error=f"LLM 返回空或异常: {markdown_content[:200]}",
            )

        # ── Strip code fences if present ──
        if markdown_content.startswith("```"):
            markdown_content = markdown_content.split("\n", 1)[-1]
        if markdown_content.endswith("```"):
            markdown_content = markdown_content.rsplit("```", 1)[0]
        markdown_content = markdown_content.strip()

        # ── Generate HTML ──
        html_content = self._markdown_to_html(markdown_content, input_data)

        # ── Generate Word (.docx) ──
        word_path = ""
        if "docx" in input_data.output_formats:
            word_path = self._save_word(markdown_content, input_data)

        # ── Extract sections ──
        sections = self._extract_sections(markdown_content)

        # ── Build output ──
        total_words = len(markdown_content.replace("\n", ""))
        now = datetime.utcnow().isoformat()

        doc = ReportDocument(
            formats=ReportFormatsDTO(
                markdown=markdown_content,
                html=html_content,
                docx_url=word_path if word_path and os.path.exists(word_path) else None,
            ),
            sections=sections,
            metadata={
                "total_word_count": total_words,
                "generated_at": now,
                "sources_count": len(eb.sources_used),
                "template_used": input_data.template_version or "v1",
                "llm_prompt_tokens": result.prompt_tokens,
                "llm_completion_tokens": result.completion_tokens,
            },
        )

        output = ReportOutput(report_document=doc)
        return AgentResult(success=True, output=output)

    # ── Serialization helpers ──

    @staticmethod
    def _serialize_evidence(eb: EvidenceBundleDTO) -> str:
        """Serialize evidence items to JSON for LLM prompt."""
        items = []
        for item in eb.evidence_items[:30]:  # top 30 evidence items
            items.append({
                "id": item.id,
                "title": item.title,
                "source": item.source,
                "url": item.url,
                "dimension": item.category,
                "content": item.content[:300],  # truncate long content
                "confidence": item.confidence,
                "date": item.date,
            })
        return json.dumps(items, ensure_ascii=False, indent=2)

    @staticmethod
    def _serialize_gap(gap: GapAnalysis) -> str:
        """Serialize gap analysis to JSON for LLM prompt."""
        pos = gap.positioning or {}
        fm = gap.features.get("feature_matrix", []) if gap.features else []
        caps = gap.gaps.get("capability_gaps", []) if gap.gaps else []
        advs = gap.gaps.get("competitive_advantages", []) if gap.gaps else []
        disadvs = gap.gaps.get("competitive_disadvantages", []) if gap.gaps else []

        return json.dumps({
            "positioning": {
                "our_positioning": pos.get("our_positioning", ""),
                "competitor_positioning": pos.get("competitor_positioning", ""),
                "positioning_diff": pos.get("positioning_diff", ""),
            },
            "feature_matrix": [
                {"feature": f.get("feature_name", ""),
                 "our_score": f.get("our_score", "N/A"),
                 "competitor_score": f.get("competitor_score", "N/A"),
                 "evidence_refs": f.get("evidence_refs", [])}
                for f in fm[:10]
            ],
            "capability_gaps": [
                {"description": c.get("description", ""),
                 "evidence_refs": c.get("evidence_refs", [])}
                for c in caps[:5]
            ],
            "advantages": [
                {"description": a.get("description", ""),
                 "evidence_refs": a.get("evidence_refs", [])}
                for a in advs[:3]
            ],
            "disadvantages": [
                {"description": d.get("description", ""),
                 "evidence_refs": d.get("evidence_refs", [])}
                for d in disadvs[:3]
            ],
        }, ensure_ascii=False, indent=2)

    @staticmethod
    def _serialize_strategy(insights: StrategicInsights) -> str:
        """Serialize strategy insights to JSON for LLM prompt."""
        swot = insights.swot or insights
        opps = insights.opportunities or []
        risks = insights.risks or []
        recs = insights.recommendations or []
        roadmap = insights.roadmap or {}

        def _swot_list(items):
            result = []
            for i in items[:5]:
                if isinstance(i, dict):
                    result.append({"conclusion": i.get("item", ""), "evidence_refs": i.get("evidence_refs", []),
                                   "confidence": i.get("confidence", "medium")})
                else:
                    result.append({"conclusion": getattr(i, "item", ""),
                                   "evidence_refs": getattr(i, "evidence_refs", []),
                                   "confidence": getattr(i, "confidence", "medium")})
            return result

        return json.dumps({
            "swot": {
                "strengths": _swot_list(swot.get("strengths", []) if isinstance(swot, dict) else getattr(swot, "strengths", [])),
                "weaknesses": _swot_list(swot.get("weaknesses", []) if isinstance(swot, dict) else getattr(swot, "weaknesses", [])),
                "opportunities": _swot_list(swot.get("opportunities", []) if isinstance(swot, dict) else getattr(swot, "opportunities", [])),
                "threats": _swot_list(swot.get("threats", []) if isinstance(swot, dict) else getattr(swot, "threats", [])),
            },
            "opportunities": [
                {"title": o.get("title", "") if isinstance(o, dict) else getattr(o, "title", ""),
                 "description": (o.get("description", "") if isinstance(o, dict) else getattr(o, "description", ""))[:200],
                 "impact": o.get("impact", "medium") if isinstance(o, dict) else getattr(o, "impact", "medium")}
                for o in (opps[:5] if isinstance(opps, list) else [])
            ],
            "risks": [
                {"title": r.get("title", "") if isinstance(r, dict) else getattr(r, "title", ""),
                 "probability": r.get("probability", "medium") if isinstance(r, dict) else getattr(r, "probability", "medium"),
                 "mitigation": (r.get("mitigation", "") if isinstance(r, dict) else getattr(r, "mitigation", ""))[:100]}
                for r in (risks[:3] if isinstance(risks, list) else [])
            ],
            "recommendations": [
                {"action": r.get("action", "") if isinstance(r, dict) else getattr(r, "action", ""),
                 "rationale": (r.get("rationale", "") if isinstance(r, dict) else getattr(r, "rationale", ""))[:150],
                 "expected_value": r.get("expected_value", "") if isinstance(r, dict) else getattr(r, "expected_value", ""),
                 "priority": r.get("priority", "p2") if isinstance(r, dict) else getattr(r, "priority", "p2")}
                for r in (recs[:5] if isinstance(recs, list) else [])
            ],
            "roadmap": {
                "phases": [
                    {"phase": p.get("phase", ""),
                     "initiatives": p.get("initiatives", [])[:5]}
                    for p in (roadmap.get("phases", []) if isinstance(roadmap, dict) else [])
                ]
            },
        }, ensure_ascii=False, indent=2)

    # ── HTML conversion ──

    @staticmethod
    def _markdown_to_html(md_text: str, input_data: ReportInput) -> str:
        """Convert Markdown to self-contained HTML page using builders."""
        html = HTMLBuilder()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        html.cover(
            input_data.our_company,
            input_data.competitor_company,
            input_data.product,
            now,
        )

        # Simple Markdown → HTML conversion for the body
        lines = md_text.split("\n")
        in_table = False
        table_headers: list[str] = []
        table_rows: list[list[str]] = []

        for line in lines:
            stripped = line.strip()

            # Skip the cover/title part already handled by html.cover()
            if stripped.startswith("# ") and "竞品分析报告" in stripped:
                continue
            if stripped.startswith("> **我方**"):
                continue
            if stripped.startswith("---"):
                if in_table:
                    if table_headers and table_rows:
                        html.table(table_headers, table_rows)
                    table_headers = []
                    table_rows = []
                    in_table = False
                html.separator()
                continue

            # Tables
            if "|" in stripped and not stripped.startswith(">"):
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                if all(c == "---" or c == "------" or re.match(r"^-+:?-*$", c) for c in cells):
                    # Separator row — skip
                    continue
                if not in_table:
                    table_headers = cells
                    in_table = True
                else:
                    table_rows.append(cells)
                continue
            else:
                if in_table:
                    if table_headers and table_rows:
                        html.table(table_headers, table_rows)
                    table_headers = []
                    table_rows = []
                    in_table = False

            # Headings
            if stripped.startswith("## "):
                heading = stripped[3:]
                sid = heading_to_id(heading)
                html.h2(heading, sid=sid)
            elif stripped.startswith("### "):
                heading = stripped[4:]
                html.h3(heading)
            elif stripped.startswith("# "):
                heading = stripped[2:]
                html.h1(heading)
            elif stripped.startswith("> "):
                html.quote(stripped[2:])
            elif stripped.startswith("- "):
                html.bullet([stripped[2:]])
            elif stripped:
                # Inline formatting
                formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
                formatted = re.sub(r"\[(E\d+)\]", r'<code>\1</code>', formatted)
                html.para(formatted)

        # Close any remaining table
        if in_table and table_headers and table_rows:
            html.table(table_headers, table_rows)

        return html.build()

    # ── Word generation ──

    @staticmethod
    def _save_word(md_text: str, input_data: ReportInput) -> str:
        """Save Word (.docx) from Markdown content."""
        word = WordBuilder()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        word.add_title("互联网产品竞品分析报告")
        word.add_meta(f"我方：{input_data.our_company} | 竞品：{input_data.competitor_company} | 产品：{input_data.product}")
        word.add_meta(f"生成日期：{now}")
        word.page_break()

        lines = md_text.split("\n")
        for line in lines:
            stripped = line.strip()

            # Skip cover elements
            if stripped.startswith("# ") and "竞品分析报告" in stripped:
                continue
            if stripped.startswith("> **我方**"):
                continue
            if not stripped:
                continue

            if stripped.startswith("## "):
                word.add_h2(stripped[3:])
            elif stripped.startswith("### "):
                word.add_h3(stripped[4:])
            elif stripped.startswith("# "):
                word.add_h1(stripped[2:])
            elif stripped.startswith("---"):
                word.add_para("")
            elif stripped.startswith("> "):
                word.quote(stripped[2:])
            elif stripped.startswith("- "):
                word.add_bullets([stripped[2:]])
            elif stripped.startswith("| ") or "|" in stripped:
                continue  # Skip tables in Word for now
            else:
                word.add_para(stripped)

        data_dir = settings.data_dir
        word_dir = data_dir / "word_outputs"
        word_path = str(word_dir / f"report_{uuid.uuid4().hex[:12]}.docx")
        return word.save(word_path)

    # ── Section extraction ──

    @staticmethod
    def _extract_sections(md_text: str) -> list[ReportSectionDTO]:
        """Extract report sections from Markdown for structured output."""
        sections: list[ReportSectionDTO] = []
        order = 0

        for section_title, section_id in SECTION_DEFS:
            order += 1
            # Find section content
            pattern = rf"## {re.escape(section_title)}"
            match = re.search(pattern, md_text)
            if match:
                start = match.start()
                # Find next ## section or end
                next_match = re.search(r"\n## ", md_text[start + len(section_title):])
                if next_match:
                    content = md_text[start:start + len(section_title) + next_match.start()]
                else:
                    content = md_text[start:]
                word_count = len(content.replace("\n", ""))
            else:
                content = f"[{section_title}] 暂无内容"
                word_count = 0

            sections.append(ReportSectionDTO(
                title=section_title,
                content=content[:2000],  # truncate for DTO
                order=order,
                word_count=word_count,
            ))

        return sections


def heading_to_id(heading: str) -> str:
    """Convert a Chinese heading to an HTML-safe ID."""
    # Map known headings to IDs
    id_map = {
        "目录": "toc",
        "一、Executive Summary": "executive_summary",
        "二、产品概览与定位": "positioning",
        "三、目标用户与画像": "users",
        "四、核心功能对比": "features",
        "五、用户体验与设计": "ux",
        "六、商业模式与收费": "business",
        "七、技术架构与能力": "technology",
        "八、增长策略与市场": "growth",
        "九、竞争格局": "competitive_landscape",
        "十、SWOT 分析": "swot_section",
        "十一、关键指标对比": "metrics",
        "十二、战略建议": "strategy",
        "十三、实施路线图": "roadmap",
        "附录": "appendix",
    }
    return id_map.get(heading, "section")
