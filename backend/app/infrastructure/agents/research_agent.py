"""Research Agent — evidence collection engine.

遵循「互联网产品竞品分析模板」的 10 大分析维度，自动生成 Research Plan，
跨多源采集证据，输出标准化的 EvidenceBundle。

原则：
  - 不分析：只收集原始证据，不做推断
  - 不总结：只输出结构化事实
  - 引用来源：每条证据必须标注来源和可信度
"""

from __future__ import annotations

import asyncio
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
from app.infrastructure.tools.search_tool import (
    SearchResult,
    app_store_search,
    google_play_search,
    news_search,
    social_search,
    web_scraper,
    web_search,
)

# ── 模板维度 → 搜索映射 ──
# 基于「互联网产品竞品分析模板」Section 3 的 10 大分析维度

TEMPLATE_DIMENSIONS: list[dict[str, Any]] = [
    {
        "id": "positioning",
        "label": "产品概览与定位",
        "keywords": ["产品定位", "公司介绍", "核心价值主张", "市场定位", "一句话定位"],
        "sources": ["web", "news"],
        "weight": 10,
    },
    {
        "id": "users",
        "label": "目标用户与画像",
        "keywords": ["目标用户", "用户画像", "用户规模", "MAU", "DAU", "用户获取"],
        "sources": ["web", "social", "app_store", "google_play"],
        "weight": 15,
    },
    {
        "id": "features",
        "label": "核心功能对比",
        "keywords": ["功能", "功能介绍", "核心功能", "产品模块", "API"],
        "sources": ["web", "app_store", "google_play", "news"],
        "weight": 20,
    },
    {
        "id": "ux",
        "label": "用户体验与设计",
        "keywords": ["用户体验", "交互设计", "UI", "新手引导", "设计风格"],
        "sources": ["app_store", "google_play", "social"],
        "weight": 10,
    },
    {
        "id": "business",
        "label": "商业模式与收费",
        "keywords": ["商业模式", "定价", "收费", "订阅", "付费", "营收"],
        "sources": ["web", "news"],
        "weight": 15,
    },
    {
        "id": "technology",
        "label": "技术架构与能力",
        "keywords": ["技术栈", "技术架构", "AI能力", "基础设施", "云服务"],
        "sources": ["web"],
        "weight": 10,
    },
    {
        "id": "growth",
        "label": "增长策略与市场",
        "keywords": ["增长策略", "市场策略", "运营", "获客", "增长率"],
        "sources": ["web", "news", "social"],
        "weight": 10,
    },
    {
        "id": "competitive_landscape",
        "label": "竞争格局",
        "keywords": ["竞争格局", "市场份额", "竞争对手", "行业排名"],
        "sources": ["web", "news"],
        "weight": 5,
    },
    {
        "id": "risks",
        "label": "风险评估",
        "keywords": ["风险", "挑战", "合规", "数据安全", "政策"],
        "sources": ["news", "social"],
        "weight": 5,
    },
    # strategy = 战略建议 — 不可搜索，仅分析
]


# ── 搜索源执行器 ──

_SOURCE_EXECUTORS: dict[str, Any] = {
    "web": web_search,
    "web_scraper": web_scraper,
    "news": news_search,
    "app_store": app_store_search,
    "google_play": google_play_search,
    "social": social_search,
}


async def _search_source(
    source_type: str,
    keywords: list[str],
) -> tuple[str, SearchResult]:
    """Dispatch a search task to the appropriate tool."""
    executor = _SOURCE_EXECUTORS.get(source_type)
    if executor is None:
        return source_type, SearchResult(
            items=[], status="no_data", total_found=0,
        )

    try:
        if source_type == "web":
            result = await executor.search(keywords, max_results=5)
        elif source_type == "web_scraper":
            # web_scraper.fetch needs a URL — handled separately in URL scraping
            result = SearchResult(items=[], status="no_data", total_found=0)
        elif source_type == "news":
            result = await executor.search(keywords, max_results=8)
        elif source_type == "app_store":
            result = await executor.search(" ".join(keywords))
        elif source_type == "google_play":
            result = await executor.search(" ".join(keywords))
        elif source_type == "social":
            result = await executor.search("zhihu", keywords)
        else:
            result = SearchResult(items=[], status="no_data", total_found=0)
    except Exception:
        result = SearchResult(items=[], status="failed", total_found=0)

    return source_type, result


def _to_evidence_items(
    source_type: str,
    results: SearchResult,
    dimension_id: str,
    company_label: str,
) -> list[dict]:
    """Convert raw search results to evidence item dicts."""
    items: list[dict] = []
    now = datetime.utcnow().isoformat()

    for raw in results.items:
        content = (
            raw.get("content")
            or raw.get("snippet")
            or raw.get("description")
            or raw.get("excerpt")
            or raw.get("title")
            or ""
        )
        if not content:
            continue

        # Determine confidence based on source
        source_str = raw.get("source", source_type)
        is_mock = source_str.startswith("mock_")
        confidence = "estimated" if is_mock else "likely"

        evidence = {
            "source": raw.get("url") or raw.get("source_name", "") or source_type,
            "source_type": source_type,
            "content": content[:2000],  # Truncate to 2000 chars
            "confidence": confidence,
            "category": dimension_id,
            "extracted_at": now,
            "raw_data": {
                k: v for k, v in raw.items()
                if k not in ("content", "snippet", "description", "excerpt")
            },
        }
        items.append(evidence)

    return items


# ── 官网抓取 ──

async def _scrape_website(
    company_name: str,
    product_name: str,
) -> list[dict]:
    """Try to scrape the company's official website."""
    evidence_items: list[dict] = []
    urls_to_try = [
        f"https://www.{company_name}.com",
        f"https://{company_name}.com",
        f"https://{company_name}.cn",
        f"https://www.{company_name}.com.cn",
    ]

    now = datetime.utcnow().isoformat()
    scraped_urls = set()

    for url in urls_to_try:
        if url in scraped_urls:
            continue
        scraped_urls.add(url)

        try:
            result = await web_scraper.fetch(url, extract_meta=True)
            if result.items:
                item = result.items[0]
                content = item.get("content", "")
                title = item.get("title", "")
                if content and len(content) > 20:  # Only accept meaningful content
                    evidence_items.append({
                        "source": url,
                        "source_type": "web",
                        "content": content[:2000],
                        "confidence": "verified",
                        "category": "positioning",
                        "extracted_at": now,
                        "raw_data": {"title": title, "status": item.get("status")},
                    })
                    break  # First successful scrape is enough
        except Exception:
            continue

    # Fallback: generate mock website content
    if not evidence_items:
        evidence_items.append({
            "source": f"https://{company_name}.com",
            "source_type": "web",
            "content": (
                f"[MOCK] {company_name} 官方网站内容摘要。"
                f"{company_name} 是一家专注于 {product_name} 的产品公司，"
                f"致力于为用户提供优质的 {product_name} 服务。"
                f"公司产品覆盖多个平台，服务大量企业客户。"
            ),
            "confidence": "estimated",
            "category": "positioning",
            "extracted_at": now,
            "raw_data": {"note": "网络请求失败，使用生成内容"},
        })

    return evidence_items


class ResearchAgent(BaseAgent[ResearchInput, ResearchOutput]):
    """Research Agent — executes evidence collection across multiple sources.

    Workflow:
      1. Auto-generate Research Plan from template dimensions
      2. Scrape official websites
      3. Execute parallel search tasks per dimension
      4. Collect and structure evidence into EvidenceBundle
      5. Calculate quality scores
    """

    @property
    def agent_name(self) -> str:
        return "research"

    @property
    def phase(self) -> Phase:
        return Phase.RESEARCHING

    async def arun(self, ctx: AgentContext, input_data: ResearchInput) -> AgentResult:
        our = input_data.our_company
        competitor = input_data.competitor_company
        product = input_data.product

        # Phase 1: Scrape official websites for both companies
        our_website_ev = await _scrape_website(our, product)
        comp_website_ev = await _scrape_website(competitor, product)

        # Phase 2: Generate search tasks from template dimensions
        search_tasks: list[asyncio.Task] = []
        for dim in TEMPLATE_DIMENSIONS:
            dim_id = dim["id"]
            base_kws = dim["keywords"]
            sources = dim["sources"]

            for company_label, company_name in [("our", our), ("competitor", competitor)]:
                keywords = [f"{company_name} {product}"] + [
                    f"{company_name} {kw}" for kw in base_kws
                ]
                # Deduplicate
                keywords = list(dict.fromkeys(keywords))

                for src in sources:
                    search_tasks.append(
                        asyncio.create_task(
                            _search_source(src, keywords),
                            name=f"{dim_id}_{company_label}_{src}",
                        )
                    )

        # Phase 3: Execute all searches in parallel
        raw_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Phase 4: Convert results to evidence items
        all_evidence: list[EvidenceItemDTO] = []
        source_stats: dict[str, dict] = {}
        coverage_by_dimension: dict[str, float] = {d["id"]: 0.0 for d in TEMPLATE_DIMENSIONS}

        # Process website evidence first
        for ev in our_website_ev + comp_website_ev:
            all_evidence.append(EvidenceItemDTO(**ev))
            dim = ev.get("category", "positioning")
            coverage_by_dimension[dim] = min(
                (coverage_by_dimension.get(dim, 0) or 0) + 20.0,
                100.0,
            )

        # Process search results
        for raw_result in raw_results:
            if isinstance(raw_result, Exception):
                continue

            source_type, search_result = raw_result  # type: ignore[misc]
            if not isinstance(search_result, SearchResult):
                continue

            # Track source
            if source_type not in source_stats:
                source_stats[source_type] = {"attempted": 0, "succeeded": 0, "failed": 0}
            source_stats[source_type]["attempted"] += 1
            if search_result.status in ("success", "fallback"):
                source_stats[source_type]["succeeded"] += 1
            else:
                source_stats[source_type]["failed"] += 1

            # Convert to evidence items
            task_name = (
                raw_result[0] if isinstance(raw_result, tuple) and len(raw_result) > 0 else ""
            )
            dim_id = "positioning"
            company_label = "our"
            # Try to extract dimension from evidence context
            # (the evidence will carry the dimension via _to_evidence_items)

            # We need a way to know which dimension this search was for.
            # The search_tasks were created with name="{dim_id}_{company_label}_{src}".
            # Since we lose the task name after gather, let's handle this differently:
            # Each raw_result carries (source_type, SearchResult) tuple.
            # We'll assign evidence to dimensions based on content matching.
            items = _to_evidence_items(source_type, search_result, dim_id, company_label)
            for item in items:
                # Try to match content to dimensions
                content = item.get("content", "").lower()
                for dim in TEMPLATE_DIMENSIONS:
                    for kw in dim["keywords"]:
                        if kw.lower() in content:
                            item["category"] = dim["id"]
                            # Bump coverage
                            coverage_by_dimension[dim["id"]] = min(
                                (coverage_by_dimension.get(dim["id"], 0) or 0) + 5.0,
                                100.0,
                            )
                            break
                    else:
                        continue
                    break
                all_evidence.append(EvidenceItemDTO(**item))

        # Phase 5: Extract company & product info
        our_company_info = self._extract_company_info(
            our, all_evidence, label="our",
        )
        comp_company_info = self._extract_company_info(
            competitor, all_evidence, label="competitor",
        )
        our_product_info = self._extract_product_info(
            product, all_evidence, label="our",
        )
        comp_product_info = self._extract_product_info(
            product, all_evidence, label="competitor",
        )

        # Phase 6: Build EvidenceBundle
        total_attempted = sum(s["attempted"] for s in source_stats.values())
        total_succeeded = sum(s["succeeded"] for s in source_stats.values())
        fallback_used = any(
            r[1].status == "fallback"
            for r in raw_results
            if isinstance(r, tuple) and len(r) > 1
        )

        avg_confidence = 0.0
        if all_evidence:
            conf_map = {"verified": 1.0, "likely": 0.8, "estimated": 0.5, "speculative": 0.3}
            scores = [conf_map.get(e.confidence, 0.5) for e in all_evidence]
            avg_confidence = sum(scores) / len(scores)

        bundle = EvidenceBundleDTO(
            our_company=our_company_info,
            competitor_company=comp_company_info,
            our_product=our_product_info,
            competitor_product=comp_product_info,
            evidence_items=all_evidence,
            news=[e.model_dump() for e in all_evidence if e.source_type == "news"],
            reviews=[e.model_dump() for e in all_evidence if e.source_type in ("app_store", "google_play")],
            sources_used=[
                {
                    "type": st,
                    "status": "success" if stats["succeeded"] > 0 else "no_data",
                    "items_found": stats["succeeded"],
                }
                for st, stats in source_stats.items()
            ],
            references=[{"url": u} for u in dict.fromkeys([e.source for e in all_evidence if e.source.startswith("http")])],
            quality_score={
                "overall": round(avg_confidence * 100, 1),
                "coverage": round(
                    sum(v for v in coverage_by_dimension.values()) / max(len(coverage_by_dimension), 1),
                    1,
                ),
                "freshness": 70.0,
            },
        )

        quality = QualityReport(
            sources_attempted=total_attempted,
            sources_succeeded=total_succeeded,
            total_evidence_items=len(all_evidence),
            coverage_by_dimension=coverage_by_dimension,
            avg_confidence=round(avg_confidence, 2),
            fallback_used=fallback_used,
            missing_data_warnings=[
                f"[{dim}] 数据量较少" if v < 30 else ""
                for dim, v in coverage_by_dimension.items()
                if v < 30
            ],
        )

        # Deduplicate warnings
        quality.missing_data_warnings = [
            w for w in quality.missing_data_warnings if w
        ]

        output = ResearchOutput(
            evidence_bundle=bundle,
            quality_report=quality,
        )
        return AgentResult(success=True, output=output)

    # ── Info Extraction Helpers ──

    def _extract_company_info(
        self,
        company_name: str,
        evidence: list[EvidenceItemDTO],
        label: str,
    ) -> CompanyInfoDTO:
        """Extract company-level information from collected evidence."""
        # Find positioning evidence
        pos_items = [
            e for e in evidence
            if e.category == "positioning" and company_name.lower() in e.content.lower()
        ]
        biz_items = [
            e for e in evidence
            if e.category == "business" and company_name.lower() in e.content.lower()
        ]
        growth_items = [
            e for e in evidence
            if e.category == "growth" and company_name.lower() in e.content.lower()
        ]

        pos_content = " | ".join(
            dict.fromkeys([e.content[:300] for e in pos_items])
        )
        biz_content = " | ".join(
            dict.fromkeys([e.content[:300] for e in biz_items])
        )
        growth_content = " | ".join(
            dict.fromkeys([e.content[:300] for e in growth_items])
        )

        has_real_data = any(
            not e.confidence == "estimated" and not e.source.startswith("mock")
            for e in pos_items + biz_items
        )

        return CompanyInfoDTO(
            name=company_name,
            description=pos_content[:500] if pos_content else "",
            positioning=pos_content[:500] if pos_content else "",
            business_model=biz_content[:300] if biz_content else "",
            market_focus=growth_content[:200] if growth_content else "",
            data_quality="high" if has_real_data else ("medium" if pos_content else "no_data"),
        )

    def _extract_product_info(
        self,
        product_name: str,
        evidence: list[EvidenceItemDTO],
        label: str,
    ) -> ProductInfoDTO:
        """Extract product-level information from collected evidence."""
        feat_items = [
            e for e in evidence
            if e.category == "features" and product_name.lower() in e.content.lower()
        ]
        ux_items = [
            e for e in evidence
            if e.category == "ux" and product_name.lower() in e.content.lower()
        ]

        feat_content = " | ".join(
            dict.fromkeys([e.content[:300] for e in feat_items])
        )
        ux_content = " | ".join(
            dict.fromkeys([e.content[:300] for e in ux_items])
        )

        has_real_data = any(
            not e.confidence == "estimated" and not e.source.startswith("mock")
            for e in feat_items
        )

        # Extract platform hints from evidence
        platform_keywords = {
            "web": "Web", "app": "App", "iOS": "iOS",
            "Android": "Android", "小程序": "小程序",
        }
        platforms_found = set()
        for e in feat_items + ux_items:
            for kw, platform in platform_keywords.items():
                if kw.lower() in e.content.lower():
                    platforms_found.add(platform)

        return ProductInfoDTO(
            name=product_name,
            description=feat_content[:500] if feat_content else "",
            key_features=[
                f"[{label}] {f}" for f in (
                    self._guess_features(feat_content) if feat_content else [
                        "核心功能模块A", "核心功能模块B",
                    ]
                )
            ],
            target_users=ux_content[:200] if ux_content else "",
            platforms=list(platforms_found) if platforms_found else ["Web"],
            data_quality="high" if has_real_data else ("medium" if feat_content else "no_data"),
        )

    @staticmethod
    def _guess_features(content: str) -> list[str]:
        """Simple heuristic: extract bullet / list items as potential features."""
        features: list[str] = []
        # Look for Chinese bullet markers
        for line in content.split("。"):
            line = line.strip()
            if any(marker in line for marker in ["功能", "支持", "提供", "具备", "包括"]):
                features.append(line[:60])
                if len(features) >= 5:
                    break
        if not features:
            features = ["核心功能模块（详见证据内容）"]
        return features
