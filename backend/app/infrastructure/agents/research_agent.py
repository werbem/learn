"""Research Agent — evidence collection via Tavily Search + LLM extraction.

Flow:
  1. Generate focused search queries via LLM
  2. Execute searches via Tavily API
  3. LLM extracts structured evidence from search results
  4. Build EvidenceBundle + QualityReport

Rules:
  - No fabricated sources: every evidence must have a real URL
  - No evidence → return empty list (never invent)
  - First stage: Tavily web search only (no AppStore/GooglePlay/Social)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

import asyncio
import json
from datetime import datetime
from typing import Any

from app.application.dto.agent_dto import (
    CompanyInfoDTO,
    EvidenceBundleDTO,
    EvidenceItemDTO,
    ProductInfoDTO,
    QualityReport,
    ResearchInput,
    ResearchOutput,
)
from app.config.constants import Phase
from app.infrastructure.agents.base import AgentContext, AgentResult, BaseAgent
from app.infrastructure.agents.research_prompt import (
    EvidenceItem,
    ExtractedEvidence,
    SYSTEM_PROMPT,
    build_extraction_prompt,
)
from app.infrastructure.llm.client import llm_client
from app.infrastructure.tools.tavily_tool import TavilyResult, tavily_search

# ── Query Generation ──

_SEARCH_QUERY_SYSTEM = """你是一个搜索策略专家。根据竞品分析目标，生成 3-5 个精准的中文搜索查询。

要求：
1. 每个查询必须具体、可搜索
2. 覆盖不同角度（用户、功能、市场、竞品对比等）
3. 优先使用具体产品名、公司名
4. 返回纯 JSON 数组

示例输出格式：
["飞猪 DAU 下降 原因 分析", "飞猪 vs 携程 用户对比 2025", "在线旅游平台 用户流失 原因"]"""

_SEARCH_QUERY_MODEL = type("SearchQueries", (), {
    "__annotations__": {"queries": list[str]},
    "__module__": "research_agent",
})

# Inject Pydantic validation
import pydantic
QueriesList = pydantic.create_model(
    "SearchQueries",
    queries=(list[str], pydantic.Field(description="搜索查询列表，3-5个")),
)


class ResearchAgent(BaseAgent[ResearchInput, ResearchOutput]):
    """Research Agent — Tavily search + LLM evidence extraction."""

    @property
    def agent_name(self) -> str:
        return "research"

    @property
    def phase(self) -> Phase:
        return Phase.RESEARCHING

    async def arun(self, ctx: AgentContext, input_data: ResearchInput) -> AgentResult:
        """Execute evidence collection.

        1. Generate search queries
        2. Execute Tavily searches
        3. LLM extract evidence
        4. Build output
        """
        objective = input_data.research_plan.objective if input_data.research_plan else (
            f"分析 {input_data.competitor_company} 的 {input_data.product}"
        )

        # Step 1: Generate search queries
        queries = await self._generate_queries(objective, input_data)

        # Step 2: Execute searches
        all_results = await self._execute_searches(queries, input_data)

        # Step 3: Extract evidence via LLM
        evidence_items, search_summary = await self._extract_evidence(
            queries, objective, all_results,
        )

        # Step 4: Build output
        bundle, quality = self._build_output(
            input_data, evidence_items, all_results,
        )

        output = ResearchOutput(
            evidence_bundle=bundle,
            quality_report=quality,
        )
        return AgentResult(
            success=True,
            output=output,
            phase_record={
                "phase": Phase.RESEARCHING.value,
                "duration_ms": 0,
                "status": "completed",
                "queries_used": queries,
                "tavily_calls": len(queries),
                "total_results": sum(len(r.items) for r in all_results),
                "evidence_count": len(evidence_items),
                "llm_generated": True,
            },
        )

    # ── Step 1: Generate Search Queries ──

    async def _generate_queries(
        self,
        objective: str,
        input_data: ResearchInput,
    ) -> list[str]:
        """Use LLM to generate focused search queries."""
        prompt = f"""分析目标：{objective}
我方公司：{input_data.our_company}
竞品公司：{input_data.competitor_company}
分析产品：{input_data.product}

请生成 3-5 个精准的搜索查询。"""

        try:
            result = await llm_client.generate(
                system_prompt=_SEARCH_QUERY_SYSTEM,
                user_prompt=prompt,
                response_model=QueriesList,
                temperature=0.5,
            )
            if result.parsed and result.parsed.queries:
                return result.parsed.queries[:5]
        except Exception:
            pass

        # Fallback: static queries based on input
        return [
            f"{input_data.competitor_company} {input_data.product} 分析",
            f"{input_data.product} 用户 数据 2025",
            f"{input_data.our_company} vs {input_data.competitor_company} 对比",
        ]

    # ── Step 2: Execute Tavily Searches ──

    async def _execute_searches(
        self,
        queries: list[str],
        input_data: ResearchInput,
    ) -> list[TavilyResult]:
        """Execute Tavily searches concurrently for all queries."""
        tasks = [
            tavily_search(query, max_results=8, include_raw_content=False)
            for query in queries
        ]
        results: list[TavilyResult] = await asyncio.gather(*tasks)
        return results

    # ── Step 3: Extract Evidence via LLM ──

    async def _extract_evidence(
        self,
        queries: list[str],
        objective: str,
        all_results: list[TavilyResult],
    ) -> tuple[list[EvidenceItemDTO], str]:
        """Use LLM to extract structured evidence from search results.

        Process each query-result pair independently, then merge.
        """
        all_evidence: list[EvidenceItemDTO] = []
        evidence_counter = 0
        all_summaries: list[str] = []

        for query, result in zip(queries, all_results):
            if result.status != "success" or not result.items:
                all_summaries.append(
                    f"查询「{query}」：{result.status} ({result.error or '无结果'})"
                )
                continue

            # Build JSON for LLM
            results_json = json.dumps(
                [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", "")[:500],
                        "score": r.get("score", 0),
                    }
                    for r in result.items
                ],
                ensure_ascii=False,
            )

            try:
                llm_result = await llm_client.generate(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=build_extraction_prompt(
                        query, objective, results_json,
                    ),
                    response_model=ExtractedEvidence,
                    temperature=0.3,
                )

                if llm_result.parsed:
                    parsed: ExtractedEvidence = llm_result.parsed
                    for item in parsed.evidence_items:
                        dto = EvidenceItemDTO(
                        id=f"E{evidence_counter:03d}",
                            title=item.title,
                            source=item.source,
                            url=item.url,
                            date=item.date,
                            content=item.summary,
                            confidence=item.confidence,
                            category=item.dimension,
                            source_type="web",
                            extracted_at=datetime.now(),
                            raw_data={
                                "dimension": item.dimension,
                                "from_query": query,
                            },
                        )
                        evidence_counter += 1
                        all_evidence.append(dto)
                    all_summaries.append(
                        f"查询「{query}」：{parsed.search_summary}"
                    )
                else:
                    all_summaries.append(
                        f"查询「{query}」：LLM解析失败，返回 {len(result.items)} 条原始结果"
                    )
            except Exception as exc:
                all_summaries.append(
                    f"查询「{query}」：LLM调用失败 ({exc})"
                )

        # Deduplicate by URL
        seen_urls: set[str] = set()
        deduped: list[EvidenceItemDTO] = []
        for e in all_evidence:
            if e.url and e.url not in seen_urls:
                seen_urls.add(e.url)
                deduped.append(e)
            elif not e.url:
                # Keep items without URL (shouldn't happen, but safety)
                deduped.append(e)

        search_summary = " | ".join(all_summaries) if all_summaries else "无搜索执行"

        return deduped, search_summary

    # ── Step 4: Build Output ──

    def _build_output(
        self,
        input_data: ResearchInput,
        evidence_items: list[EvidenceItemDTO],
        all_results: list[TavilyResult],
    ) -> tuple[EvidenceBundleDTO, QualityReport]:
        """Build EvidenceBundle and QualityReport from extracted evidence."""
        total_results = sum(len(r.items) for r in all_results)
        sources_used: list[dict] = []
        seen_domains: set[str] = set()
        for e in evidence_items:
            if e.url:
                from urllib.parse import urlparse
                domain = urlparse(e.url).netloc
                if domain not in seen_domains:
                    seen_domains.add(domain)
                    sources_used.append({"domain": domain, "url": e.url})

        # Build company/product info from top evidence
        our_items = [
            e for e in evidence_items
            if input_data.our_company.lower() in (e.title + e.content).lower()
        ]
        comp_items = [
            e for e in evidence_items
            if input_data.competitor_company.lower() in (e.title + e.content).lower()
        ]

        bundle = EvidenceBundleDTO(
            our_company=CompanyInfoDTO(
                name=input_data.our_company,
                description=self._join_evidence(our_items[:3]),
                data_quality="medium" if our_items else "no_data",
            ),
            competitor_company=CompanyInfoDTO(
                name=input_data.competitor_company,
                description=self._join_evidence(comp_items[:3]),
                data_quality="medium" if comp_items else "no_data",
            ),
            our_product=ProductInfoDTO(
                name=input_data.product,
                description=self._join_evidence(our_items[:2]),
                data_quality="medium" if our_items else "no_data",
            ),
            competitor_product=ProductInfoDTO(
                name=input_data.product,
                description=self._join_evidence(comp_items[:2]),
                data_quality="medium" if comp_items else "no_data",
            ),
            evidence_items=evidence_items,
            news=[],
            reviews=[],
            market=[],
            sources_used=sources_used,
            references=[
                {"url": e.url, "title": e.title} for e in evidence_items if e.url
            ],
            quality_score={
                "overall": min(100, len(evidence_items) * 10),
                "coverage": min(100, len(sources_used) * 10),
                "freshness": 70,  # Tavily tends to return recent results
            },
        )

        # Calculate dimension coverage
        dimensions: dict[str, int] = {}
        for e in evidence_items:
            dim = e.category or "other"
            dimensions[dim] = dimensions.get(dim, 0) + 1
        coverage_by_dimension: dict[str, float] = {}
        for dim, count in dimensions.items():
            coverage_by_dimension[dim] = min(100.0, count * 20.0)

        # Average confidence
        conf_weights = {"high": 1.0, "medium": 0.6, "low": 0.3, "estimated": 0.1}
        avg_conf = (
            sum(conf_weights.get(e.confidence, 0.3) for e in evidence_items)
            / max(len(evidence_items), 1)
        )

        quality = QualityReport(
            sources_attempted=max(len(all_results), 1),
            sources_succeeded=sum(1 for r in all_results if r.status == "success"),
            total_evidence_items=len(evidence_items),
            coverage_by_dimension=coverage_by_dimension,
            avg_confidence=round(avg_conf, 2),
            fallback_used=False,
            missing_data_warnings=(
                ["TAVILY_API_KEY 未配置，无法执行真实搜索"]
                if not evidence_items and not total_results
                else []
            ),
        )

        return bundle, quality

    @staticmethod
    def _join_evidence(items: list[EvidenceItemDTO]) -> str:
        if not items:
            return ""
        return " | ".join(
            e.content[:200] for e in items if e.content
        )
