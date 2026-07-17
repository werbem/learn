"""Report Agent — formats analysis results into structured reports.

遵循「互联网产品竞品分析模板」的 10 大分析维度 + SWOT + 战略建议。
不重新分析，只负责排版。

Supported formats: Markdown, HTML, Word (.docx)
"""

from __future__ import annotations

import os
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
from app.infrastructure.tools.export_tool import (
    HTMLBuilder,
    MarkdownBuilder,
    WordBuilder,
)


# ═════════════════════════════════════════════════
#  Data Extraction Helpers (read-only, no analysis)
# ═════════════════════════════════════════════════

def _ev(eb: EvidenceBundleDTO, category: str, max_items: int = 10) -> list[str]:
    """Extract evidence content strings by category — for inline citations."""
    texts: list[str] = []
    for item in eb.evidence_items:
        if item.category == category and item.content:
            texts.append(item.content)
            if len(texts) >= max_items:
                break
    return texts


def _fmt(items: list[str], max_chars: int = 300) -> str:
    """Format evidence items as a single block quote string."""
    if not items:
        return "暂无公开数据"
    joined = "。".join(i.strip().rstrip("。") for i in items if i.strip())
    return joined[:max_chars] + ("..." if len(joined) > max_chars else "")


def _cvg(val: Any) -> str:
    """Convert a value to a coverage symbol string."""
    if isinstance(val, str):
        val = val.lower()
        if val in ("full", "yes", "true", "✅"):
            return "✅"
        if val in ("partial", "limited"):
            return "🟡"
        return "❌"
    if isinstance(val, bool):
        return "✅" if val else "❌"
    return str(val) if val else "❌"


def _safe(val: Any, default: str = "暂无数据") -> str:
    """Return value or default."""
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def _obj_val(obj: dict | Any, key: str, default: str = "暂无数据") -> str:
    """Safely access dict or object attribute."""
    if isinstance(obj, dict):
        return _safe(obj.get(key), default)
    return _safe(getattr(obj, key, None), default)


# ═════════════════════════════════════════════════
#  Section Builders
# ═════════════════════════════════════════════════

SECTION_META: list[dict[str, str]] = [
    {"id": "positioning", "title": "产品概览与定位"},
    {"id": "users", "title": "目标用户与画像"},
    {"id": "features", "title": "核心功能对比"},
    {"id": "ux", "title": "用户体验与设计"},
    {"id": "business", "title": "商业模式与收费"},
    {"id": "technology", "title": "技术架构与能力"},
    {"id": "growth", "title": "增长策略与市场"},
    {"id": "competitive_landscape", "title": "竞争格局"},
    {"id": "risks", "title": "风险评估"},
    {"id": "swot_section", "title": "SWOT 分析"},
    {"id": "strategy", "title": "战略建议"},
    {"id": "roadmap", "title": "实施路线图"},
]


def _build_positioning(
    md: MarkdownBuilder,
    html: HTMLBuilder,
    word: WordBuilder,
    eb: EvidenceBundleDTO,
    gap: GapAnalysis,
) -> None:
    """Section 1: 产品概览与定位"""
    pos = gap.positioning or {}
    our = eb.our_company
    comp = eb.competitor_company

    our_pos = _obj_val(pos, "our_positioning", our.positioning or "暂无")
    comp_pos = _obj_val(pos, "competitor_positioning", comp.positioning or "暂无")
    diff = _obj_val(pos, "positioning_diff", "未明确对比")

    for builder in [md, html, word]:
        if isinstance(builder, MarkdownBuilder):
            builder.h2("一、产品概览与定位")
        elif isinstance(builder, HTMLBuilder):
            builder.h2("一、产品概览与定位", sid="positioning")
        else:
            word.add_h2("一、产品概览与定位")

    # Company overview table
    headers = ["维度", our.name or "我方", comp.name or "竞品"]
    rows = [
        ["产品定位", our_pos, comp_pos],
        ["核心价值主张", _safe(our.description), _safe(comp.description)],
        ["商业模式", _safe(our.business_model), _safe(comp.business_model)],
        ["覆盖市场", _safe(our.market_focus), _safe(comp.market_focus)],
        ["定位差异", diff, "—"],
    ]

    for builder in [md, html, word]:
        if True:  # table() available on all builders
            builder.table(headers, rows)


def _build_users(
    md: MarkdownBuilder,
    html: HTMLBuilder,
    word: WordBuilder,
    eb: EvidenceBundleDTO,
    gap: GapAnalysis,
) -> None:
    """Section 2: 目标用户与画像"""
    ev = _ev(eb, "users")
    users = gap.users or {}

    headers = ["维度", "我方", "竞品"]
    rows = [
        ["核心用户群", _safe(users.get("our_core_users", "核心产品用户")),
         _safe(users.get("competitor_core_users", "核心产品用户"))],
        ["用户规模", _safe(users.get("our_scale", "待确认")),
         _safe(users.get("competitor_scale", "待确认"))],
    ]

    for builder in [md, html, word]:
        if isinstance(builder, MarkdownBuilder):
            builder.h2("二、目标用户与画像")
            builder.table(headers, rows)
            if ev:
                builder.para(f"用户评价摘要：{_fmt(ev)}")
        elif isinstance(builder, HTMLBuilder):
            builder.h2("二、目标用户与画像", sid="users")
            builder.table(headers, rows)
            if ev:
                builder.para(f"用户评价摘要：{_fmt(ev)}")
        else:
            word.add_h2("二、目标用户与画像")
            word.add_table(headers, rows)
            if ev:
                word.add_quote(f"用户评价摘要：{_fmt(ev)}")


def _build_features(
    md: MarkdownBuilder,
    html: HTMLBuilder,
    word: WordBuilder,
    eb: EvidenceBundleDTO,
    gap: GapAnalysis,
) -> None:
    """Section 3: 核心功能对比"""
    feats = gap.features or {}
    matrix = feats.get("feature_matrix", [])
    our_unique = feats.get("unique_our_features", [])
    comp_unique = feats.get("unique_competitor_features", [])
    ev = _ev(eb, "features")

    for builder in [md, html, word]:
        if isinstance(builder, MarkdownBuilder):
            builder.h2("三、核心功能对比")
        elif isinstance(builder, HTMLBuilder):
            builder.h2("三、核心功能对比", sid="features")
        else:
            word.add_h2("三、核心功能对比")

    # Feature matrix table
    headers = ["功能模块", "功能名称", "我方覆盖", "竞品覆盖"]
    if matrix:
        rows = []
        for f in matrix:
            rows.append([
                f.get("category", ""),
                f.get("feature_name", ""),
                _cvg(f.get("our_coverage", "")),
                _cvg(f.get("competitor_coverage", "")),
            ])
        for builder in [md, html, word]:
            if True:  # table() available on all builders
                builder.table(headers, rows)
    else:
        for builder in [md, html, word]:
            if hasattr(builder, 'para'):
                builder.para("功能对比矩阵待 Compare Agent 提供详细数据。")

    # Unique features
    if our_unique or comp_unique:
        lines = [f"我方独有：{'、'.join(our_unique)}" if our_unique else "",
                 f"竞品独有：{'、'.join(comp_unique)}" if comp_unique else ""]
        for builder in [md, html, word]:
            builder.bullets([l for l in lines if l])

    if ev:
        for builder in [md, html, word]:
            builder.para(f"功能证据：{_fmt(ev)}")

    for builder in [md, html, word]:
        builder.image_placeholder("功能覆盖雷达图")


def _build_business(
    md: MarkdownBuilder,
    html: HTMLBuilder,
    word: WordBuilder,
    eb: EvidenceBundleDTO,
    gap: GapAnalysis,
) -> None:
    """Section 5: 商业模式与收费"""
    biz = gap.business or {}
    ev = _ev(eb, "business")

    headers = ["维度", "我方", "竞品"]
    rows = [
        ["盈利模式", _safe(biz.get("our_model", "待确认")), _safe(biz.get("competitor_model", "待确认"))],
        ["定价策略", _safe(biz.get("our_pricing", "待确认")), _safe(biz.get("competitor_pricing", "待确认"))],
    ]

    for builder in [md, html, word]:
        if isinstance(builder, MarkdownBuilder):
            builder.h2("五、商业模式与收费")
            builder.table(headers, rows)
        elif isinstance(builder, HTMLBuilder):
            builder.h2("五、商业模式与收费", sid="business")
            builder.table(headers, rows)
        else:
            word.add_h2("五、商业模式与收费")
            word.add_table(headers, rows)


def _build_tech(
    md: MarkdownBuilder,
    html: HTMLBuilder,
    word: WordBuilder,
    eb: EvidenceBundleDTO,
) -> None:
    """Section 6: 技术架构与能力"""
    ev = _ev(eb, "technology")
    ai_ev = _ev(eb, "technology")

    for builder in [md, html, word]:
        if isinstance(builder, MarkdownBuilder):
            builder.h2("六、技术架构与能力")
        elif isinstance(builder, HTMLBuilder):
            builder.h2("六、技术架构与能力", sid="technology")
        else:
            word.add_h2("六、技术架构与能力")

    if ev:
        for builder in [md, html, word]:
            builder.para(f"技术能力概览：{_fmt(ev)}")
    else:
        for builder in [md, html, word]:
            builder.para("暂无公开技术架构数据。")

    has_ai = any("AI" in e.content for e in eb.evidence_items if e.content)
    if has_ai:
        for builder in [md, html, word]:
            builder.para("* 检测到 AI 相关功能/能力描述")


def _build_growth(
    md: MarkdownBuilder,
    html: HTMLBuilder,
    word: WordBuilder,
    eb: EvidenceBundleDTO,
    gap: GapAnalysis,
) -> None:
    """Section 7: 增长策略与市场"""
    growth = gap.growth or {}
    ev = _ev(eb, "growth")

    headers = ["维度", "我方", "竞品"]
    rows = [
        ["增长策略", _safe(growth.get("our_strategy", "待确认")),
         _safe(growth.get("competitor_strategy", "待确认"))],
    ]

    for builder in [md, html, word]:
        if isinstance(builder, MarkdownBuilder):
            builder.h2("七、增长策略与市场")
            builder.table(headers, rows)
        elif isinstance(builder, HTMLBuilder):
            builder.h2("七、增长策略与市场", sid="growth")
            builder.table(headers, rows)
        else:
            word.add_h2("七、增长策略与市场")
            word.add_table(headers, rows)

    if ev:
        for builder in [md, html, word]:
            builder.quote(f"市场信号：{_fmt(ev, 500)}")


def _build_competitive_landscape(
    md: MarkdownBuilder,
    html: HTMLBuilder,
    word: WordBuilder,
    eb: EvidenceBundleDTO,
    gap: GapAnalysis,
) -> None:
    """Section 8: 竞争格局"""
    gaps_data = gap.gaps or {}
    ev = _ev(eb, "competitive_landscape")

    for builder in [md, html, word]:
        if isinstance(builder, MarkdownBuilder):
            builder.h2("八、竞争格局")
        elif isinstance(builder, HTMLBuilder):
            builder.h2("八、竞争格局", sid="competitive_landscape")
        else:
            word.add_h2("八、竞争格局")

    # Format gaps as evidence
    sections_to_render = []
    for key, label in [("competitive_advantages", "竞争优势"),
                       ("competitive_disadvantages", "竞争劣势"),
                       ("capability_gaps", "能力差距")]:
        items = gaps_data.get(key, [])
        if items:
            lines = []
            for item in items:
                desc = item.get("description", "") if isinstance(item, dict) else str(item)
                imp = item.get("impact", "") if isinstance(item, dict) else ""
                lines.append(f"- {desc}" + (f"（影响：{imp}）" if imp else ""))
            if lines:
                sections_to_render.append(f"**{label}**\n" + "\n".join(lines))

    for builder in [md, html, word]:
        if sections_to_render:
            builder.para("\n\n".join(sections_to_render))
        if ev:
            builder.quote(f"竞争格局数据：{_fmt(ev, 500)}")


def _build_risks(
    md: MarkdownBuilder,
    html: HTMLBuilder,
    word: WordBuilder,
    insights: StrategicInsights,
) -> None:
    """Section 9: 风险评估"""
    for builder in [md, html, word]:
        if isinstance(builder, MarkdownBuilder):
            builder.h2("九、风险评估")
        elif isinstance(builder, HTMLBuilder):
            builder.h2("九、风险评估", sid="risks")
        else:
            word.add_h2("九、风险评估")

    if insights.risks:
        headers = ["风险", "描述", "概率", "影响", "应对措施"]
        rows = []
        for r in insights.risks:
            rows.append([
                r.title, r.description[:60],
                r.probability, r.impact, r.mitigation,
            ])
        for builder in [md, html, word]:
            if True:  # table() available on all builders
                builder.table(headers, rows)
    else:
        for builder in [md, html, word]:
            builder.para("Strategy Agent 未识别出明确风险。")


def _build_swot(
    md: MarkdownBuilder,
    html: HTMLBuilder,
    word: WordBuilder,
    insights: StrategicInsights,
) -> None:
    """Section 10: SWOT 分析"""
    swot = insights.swot

    for builder in [md, html, word]:
        if isinstance(builder, MarkdownBuilder):
            builder.h2("十、SWOT 分析")
        elif isinstance(builder, HTMLBuilder):
            builder.h2("十、SWOT 分析", sid="swot")
        else:
            word.add_h2("十、SWOT 分析")

    # SWOT Matrix
    def fmt_swot(items: list) -> list[str]:
        return [f"- {i.item}" if hasattr(i, 'item') else f"- {i}" for i in (items or [])]

    s_items = fmt_swot(swot.strengths) if hasattr(swot, 'strengths') else []
    w_items = fmt_swot(swot.weaknesses) if hasattr(swot, 'weaknesses') else []
    o_items = fmt_swot(swot.opportunities) if hasattr(swot, 'opportunities') else []
    t_items = fmt_swot(swot.threats) if hasattr(swot, 'threats') else []

    s_text = "\n".join(s_items) if s_items else "- 暂无数据"
    w_text = "\n".join(w_items) if w_items else "- 暂无数据"
    o_text = "\n".join(o_items) if o_items else "- 暂无数据"
    t_text = "\n".join(t_items) if t_items else "- 暂无数据"

    swot_md = (
        f"| | **优势 (S)** | **劣势 (W)** |\n"
        f"|---|----|----|\n"
        f"| **机会 (O)** | SO 策略：利用优势抓住机会 | WO 策略：改善劣势抓住机会 |\n"
        f"| **威胁 (T)** | ST 策略：利用优势应对威胁 | WT 策略：减少劣势规避威胁 |\n\n"
        f"**优势 (S)**\n{s_text}\n\n"
        f"**劣势 (W)**\n{w_text}\n\n"
        f"**机会 (O)**\n{o_text}\n\n"
        f"**威胁 (T)**\n{t_text}"
    )

    if md:
        md.para(swot_md)

    if html:
        html.para(swot_md.replace("\n", "<br>"))

    if word:
        word.add_para("优势 (S)")
        word.add_bullets([i.strip("- ").strip() for i in s_items])
        word.add_para("劣势 (W)")
        word.add_bullets([i.strip("- ").strip() for i in w_items])
        word.add_para("机会 (O)")
        word.add_bullets([i.strip("- ").strip() for i in o_items])
        word.add_para("威胁 (T)")
        word.add_bullets([i.strip("- ").strip() for i in t_items])


def _build_strategy(
    md: MarkdownBuilder,
    html: HTMLBuilder,
    word: WordBuilder,
    insights: StrategicInsights,
) -> None:
    """Section 11: 战略建议"""
    for builder in [md, html, word]:
        if isinstance(builder, MarkdownBuilder):
            builder.h2("十一、战略建议")
        elif isinstance(builder, HTMLBuilder):
            builder.h2("十一、战略建议", sid="strategy")
        else:
            word.add_h2("十一、战略建议")

    if not insights.recommendations:
        for builder in [md, html, word]:
            builder.para("Strategy Agent 未生成具体建议。")
        return

    headers = ["优先级", "行动项", "时间线", "KPI"]
    p_map = {"p0": "P0-紧急", "p1": "P1-重要", "p2": "P2-一般", "p3": "P3-可选"}
    t_map = {"immediate": "立即", "short_term": "短期(1-3月)", "medium_term": "中期(3-6月)", "long_term": "长期(6-12月)"}
    rows = []
    for r in insights.recommendations[:10]:
        rows.append([
            p_map.get(r.priority, r.priority),
            r.action[:80],
            t_map.get(r.timeline, r.timeline),
            _safe(r.kpi, "待定义"),
        ])

    for builder in [md, html, word]:
        if True:  # table() available on all builders
            builder.table(headers, rows)

    # Evidence references
    citations = []
    for r in insights.recommendations[:5]:
        if r.evidence_refs:
            refs = "; ".join(r.evidence_refs[:3])
            citations.append(f"- {r.action[:50]} → {refs}")
    if citations:
        for builder in [md, html, word]:
            builder.para("**证据引用**")
            builder.bullets(citations)


def _build_roadmap(
    md: MarkdownBuilder,
    html: HTMLBuilder,
    word: WordBuilder,
    insights: StrategicInsights,
) -> None:
    """Section 12: 实施路线图"""
    for builder in [md, html, word]:
        if isinstance(builder, MarkdownBuilder):
            builder.h2("十二、实施路线图")
        elif isinstance(builder, HTMLBuilder):
            builder.h2("十二、实施路线图", sid="roadmap")
        else:
            word.add_h2("十二、实施路线图")

    phases = insights.roadmap.get("phases", []) if insights.roadmap else []
    if not phases:
        for builder in [md, html, word]:
            builder.para("Strategy Agent 未输出路线图。")
        return

    for phase in phases:
        name = phase.get("phase", "未命名阶段")
        dur = phase.get("duration", "")
        initiatives = phase.get("initiatives", [])
        criteria = phase.get("success_criteria", [])

        for builder in [md, html, word]:
            if isinstance(builder, (MarkdownBuilder, HTMLBuilder)):
                builder.h3(f"{name}（{dur}）" if dur else name)
                if initiatives:
                    builder.bullets(initiatives)
                if criteria:
                    builder.para(f"**成功标准**")
                    builder.bullets(criteria)
            else:
                word.add_h3(f"{name}（{dur}）" if dur else name)
                if initiatives:
                    word.add_bullets(initiatives)
                if criteria:
                    word.add_para("成功标准")
                    word.add_bullets(criteria)


# ═════════════════════════════════════════════════
#  Main Report Agent
# ═════════════════════════════════════════════════

class ReportAgent(BaseAgent[ReportInput, ReportOutput]):
    """Report Agent — formats analysis results into structured reports.

    Workflow:
      1. Extract data from all prior agents (no re-analysis)
      2. Build section content per template dimensions
      3. Generate Markdown, HTML, and Word formats
    """

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
        our = input_data.our_company
        comp = input_data.competitor_company
        prod = input_data.product

        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ── Build sections ──
        md = MarkdownBuilder()
        html = HTMLBuilder()
        word = WordBuilder()

        # Cover page
        md.h1("互联网产品竞品分析报告")
        md.quote(f"我方：{our} | 竞品：{comp} | 产品：{prod} | 生成日期：{now}")
        md.separator()

        html.cover(our, comp, prod, now)

        word.add_title("互联网产品竞品分析报告")
        word.add_meta(f"我方：{our} | 竞品：{comp} | 产品：{prod}")
        word.add_meta(f"生成日期：{now}")
        word.add_para("")
        word.page_break()

        # Table of Contents
        toc_items = [(s["id"], s["title"]) for s in SECTION_META]
        md.h2("目录")
        for sid, title in toc_items:
            md.para(f"- [{title}](#{sid})")
        md.separator()

        html.toc(toc_items)

        word_h2 = word.doc.add_heading("目录", level=1)
        for _, title in toc_items:
            word.add_para(f"  {title}")
        word.page_break()

        # ── Render each section ──
        # Section 1: Positioning
        _build_positioning(md, html, word, eb, gap)

        # Section 2: Users
        _build_users(md, html, word, eb, gap)

        # Section 3: Features
        _build_features(md, html, word, eb, gap)

        # Section 4: UX
        ux_ev = _ev(eb, "ux")
        for builder in [md, html, word]:
            if isinstance(builder, MarkdownBuilder):
                builder.h2("四、用户体验与设计")
            elif isinstance(builder, HTMLBuilder):
                builder.h2("四、用户体验与设计", sid="ux")
            else:
                word.add_h2("四、用户体验与设计")
            if ux_ev:
                builder.para(f"用户反馈摘要：{_fmt(ux_ev)}")
            else:
                builder.para("暂无公开的用户体验评价数据。")

        # Section 5: Business
        _build_business(md, html, word, eb, gap)

        # Section 6: Tech
        _build_tech(md, html, word, eb)

        # Section 7: Growth
        _build_growth(md, html, word, eb, gap)

        # Section 8: Competitive Landscape
        _build_competitive_landscape(md, html, word, eb, gap)

        # Section 9: Risks
        _build_risks(md, html, word, insights)

        # Section 10: SWOT
        _build_swot(md, html, word, insights)

        # Section 11: Strategy
        _build_strategy(md, html, word, insights)

        # Section 12: Roadmap
        _build_roadmap(md, html, word, insights)

        # ── Appendix ──
        qs = eb.quality_score or {}
        sources_text = "; ".join(
            _safe(s.get("type", s)) for s in eb.sources_used if isinstance(s, dict)
        ) or "待补充"
        appendix_md = (
            f"**数据来源**：{sources_text}\n\n"
            f"**证据质量评分**：总体 {qs.get('overall', 'N/A')}% | "
            f"覆盖率 {qs.get('coverage', 'N/A')}% | "
            f"新鲜度 {qs.get('freshness', 'N/A')}%\n\n"
            f"*报告由 AI 竞品分析助手自动生成，数据来源已标注可信度。*"
        )

        md.separator()
        md.h2("附录")
        md.para(appendix_md)

        html.separator()
        html.h2("附录")
        html.para(appendix_md)

        word.add_para("")
        word.add_h2("附录")
        word.add_para(appendix_md)

        # ── Build section metadata ──
        section_dtos: list[ReportSectionDTO] = []
        md_text = md.build()
        html_text = html.build()

        for meta in SECTION_META:
            # Extract section content from full markdown
            sec_id = meta["id"]
            section_dtos.append(ReportSectionDTO(
                title=meta["title"],
                content=f"[{sec_id}] 详见完整报告",
                order=SECTION_META.index(meta) + 1,
                word_count=0,
            ))

        # ── Save Word document ──
        word_path = ""
        if "docx" in input_data.output_formats:
            data_dir = settings.data_dir
            word_dir = data_dir / "word_outputs"
            word_path = str(word_dir / f"report_{uuid.uuid4().hex[:12]}.docx")
            word.save(word_path)

        # ── Build output ──
        total_words = len(md_text.replace("\n", ""))

        doc = ReportDocument(
            formats=ReportFormatsDTO(
                markdown=md_text,
                html=html_text,
                docx_url=word_path if word_path and os.path.exists(word_path) else None,
            ),
            sections=section_dtos,
            metadata={
                "total_word_count": total_words,
                "generated_at": now,
                "sources_count": len(eb.sources_used),
                "template_used": input_data.template_version or "v1",
                "llm_prompt_tokens": 0,
                "llm_completion_tokens": 0,
            },
        )

        output = ReportOutput(report_document=doc)
        return AgentResult(success=True, output=output)
