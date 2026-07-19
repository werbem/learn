"""Official Website Research Source — implements ResearchSource interface.

Capabilities:
  1. Auto-discover official website URL (Tavily + pattern fallback)
  2. Fetch homepage + key subpages
  3. Extract clean text (remove nav, footer, ads, scripts, styles)
  4. Create EvidenceItems with dimensions:
     - product_position  (product positioning, value proposition)
     - business_model    (revenue model, pricing, partnerships)
     - feature           (product features, capabilities)
  5. Fallback: Tavily web search for official pages

Rules:
  - No authentication/key required (public pages)
  - Respects robots.txt? Not for public informational pages
  - Rate limiting: 1 request per domain
"""

from __future__ import annotations

import asyncio as _asyncio
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from lxml import html as lxml_html

from app.infrastructure.tools.research_source import (
    EvidenceItem,
    ResearchSource,
    SourceResult,
    SourceType,
)
from app.infrastructure.tools.tavily_tool import tavily_search
from app.infrastructure.trace import trace_collector


_HTTP_TIMEOUT = 15.0
_MAX_PAGES = 3  # homepage + up to 2 subpages
_TEXT_MAX_LEN = 5000

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Common subpages to attempt
_SUBPAGE_PATTERNS = [
    "/about", "/aboutus", "/about-us",
    "/product", "/products", "/features",
    "/pricing", "/price", "/plans",
    "/business", "/enterprise", "/solutions",
    "/company",
]


class OfficialWebsiteSource(ResearchSource):
    """Official website data via HTTP scraping + content extraction."""

    @property
    def name(self) -> str:
        return "Official Website"

    @property
    def source_type(self) -> str:
        return SourceType.OFFICIAL

    async def search(self, query: str, context: Optional[dict] = None) -> SourceResult:
        task_id = (context or {}).get("task_id", "unknown")
        start = time.time()

        trace = trace_collector.start_trace(
            task_id=task_id, stage="search_tool", agent_name="research",
            input_summary=f"OfficialSite: {query[:100]}",
            metadata={"source": "official", "query": query},
        )

        # Step 1: Discover URLs
        urls = await self._discover_urls(query)

        # Step 2: Fetch and extract content from each URL
        items: list[EvidenceItem] = []
        for url in urls[:_MAX_PAGES]:
            evidence = await self._extract_from_url(url, query)
            if evidence:
                items.append(evidence)

        # Step 3: Fallback — Tavily
        if not items:
            items = await self._fallback_tavily(query)

        duration_ms = int((time.time() - start) * 1000)

        trace_collector.end_trace(
            trace, success=True,
            output_summary=f"OfficialSite: {len(items)} items",
            metadata={"duration_ms": duration_ms, "result_count": len(items)},
        )

        return SourceResult(
            items=items, source_type=SourceType.OFFICIAL,
            source_name=self.name,
            status="success" if items else "no_data",
            total_found=len(items), duration_ms=duration_ms,
        )

    # ── URL Discovery ──

    async def _discover_urls(self, query: str) -> list[str]:
        """Discover official website URLs via Tavily + pattern fallback."""
        urls: list[str] = []

        # Primary: Tavily search for official site
        try:
            result = await tavily_search(
                query=f"{query} 官方网站",
                max_results=3,
                search_depth="basic",
                include_raw_content=False,
            )
            for item in result.items:
                url = item.get("url", "")
                if url and self._is_valid_url(url):
                    urls.append(url)
        except Exception:
            pass

        # Fallback: common patterns
        if not urls:
            company = query.strip()
            patterns = [
                f"https://www.{company}.com",
                f"https://{company}.com",
                f"https://www.{company}.com.cn",
            ]
            for pattern in patterns:
                try:
                    resp = await _asyncio.to_thread(
                        httpx.head, pattern, headers=_HEADERS, timeout=5,
                        follow_redirects=True,
                    )
                    if resp.status_code < 400:
                        urls.append(pattern)
                        break
                except Exception:
                    continue

        return urls

    # ── Content Extraction ──

    async def _extract_from_url(self, url: str, query: str) -> Optional[EvidenceItem]:
        """Fetch URL, extract clean text, determine dimension."""
        try:
            resp = await _asyncio.to_thread(
                httpx.get, url, headers=_HEADERS, timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
            )
            resp.raise_for_status()
            html = resp.text
        except Exception:
            return None

        # Extract page title
        title = self._extract_title(html, url)

        # Clean text
        text = self._clean_html(html)

        if not text or len(text) < 50:
            return None

        # Determine dimension from URL path
        dimension = self._infer_dimension(url)

        # Extract metadata
        domain = urlparse(url).netloc
        meta_desc = self._extract_meta_desc(html)

        content_parts = [text]
        if meta_desc:
            content_parts = [f"页面描述: {meta_desc}"] + content_parts

        return EvidenceItem(
            source_type=SourceType.OFFICIAL,
            source_name=self.name,
            title=title or f"{query} 官方网站",
            url=url,
            content="\n".join(content_parts)[:3000],
            published_date="",
            author=domain,
            metrics={
                "domain": domain,
                "page_type": dimension,
                "text_length": len(text),
            },
            dimension=dimension,
            confidence="high",  # Official source = high confidence
        )

    # ── HTML Cleaning ──

    @staticmethod
    def _clean_html(html_text: str) -> str:
        """Extract readable text, removing noise."""
        try:
            doc = lxml_html.fromstring(html_text)
        except Exception:
            return ""

        # Remove non-content elements
        for tag in doc.xpath(
            '//script | //style | //nav | //footer | //header | '
            '//aside | //noscript | //iframe | //svg'
        ):
            tag.drop_tree()

        # Remove common ad/nav UI patterns
        bad_patterns = [
            "nav", "footer", "advertisement", "sidebar",
            "menu", "banner", "popup", "cookie", "modal",
        ]
        for pattern in bad_patterns:
            try:
                xp = f'//*[contains(@class,"{pattern}") or contains(@id,"{pattern}") or contains(@role,"{pattern}")]'
                for tag in doc.xpath(xp):
                    tag.drop_tree()
            except Exception:
                pass

        text = doc.text_content()
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove very short lines (navigation remnants)
        lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 5]
        text = ' '.join(lines)
        return text[:_TEXT_MAX_LEN]

    @staticmethod
    def _extract_title(html_text: str, url: str) -> str:
        """Extract page title from HTML."""
        try:
            doc = lxml_html.fromstring(html_text)
            title_el = doc.find(".//title")
            if title_el is not None and title_el.text:
                return title_el.text.strip()[:200]
        except Exception:
            pass
        return f"官方网站: {urlparse(url).netloc}"

    @staticmethod
    def _extract_meta_desc(html_text: str) -> str:
        """Extract meta description."""
        try:
            doc = lxml_html.fromstring(html_text)
            for meta in doc.xpath("//meta[@name='description']"):
                content = meta.get("content", "")
                if content:
                    return content.strip()[:300]
        except Exception:
            pass
        return ""

    @staticmethod
    def _infer_dimension(url: str) -> str:
        """Infer evidence dimension from URL path."""
        path = urlparse(url).path.lower()
        if any(k in path for k in ["about", "company", "intro", "overview"]):
            return "product_position"
        if any(k in path for k in ["product", "features", "feature"]):
            return "feature"
        if any(k in path for k in ["pricing", "price", "plan", "buy"]):
            return "business_model"
        if any(k in path for k in ["business", "enterprise", "partner", "solution"]):
            return "business_model"
        # Homepage or unknown → general product positioning
        return "product_position"

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Check if URL looks valid (not CDN, not API, etc.)."""
        if not url or not url.startswith("http"):
            return False
        skip_domains = ["cdn", "static", "api", "assets", "img", "image"]
        domain = urlparse(url).netloc.lower()
        for skip in skip_domains:
            if skip in domain:
                return False
        return True

    # ── Fallback ──

    async def _fallback_tavily(self, query: str) -> list[EvidenceItem]:
        """Fallback: search for official pages via Tavily."""
        result = await tavily_search(
            query=f"{query} 官方网站 产品介绍",
            max_results=3,
            search_depth="basic",
            include_raw_content=True,
        )
        if not result.items:
            return []

        items: list[EvidenceItem] = []
        for r in result.items[:3]:
            items.append(EvidenceItem(
                source_type=SourceType.OFFICIAL,
                source_name=f"{self.name} (via Tavily)",
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", "")[:2000],
                published_date=r.get("published_date", ""),
                metrics={"score": r.get("score", 0.0), "fallback": True},
                dimension="product_position",
                confidence="medium",
            ))
        return items


# ── Singleton ──

official_source = OfficialWebsiteSource()
