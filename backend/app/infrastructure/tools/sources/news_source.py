"""News Research Source — implements ResearchSource interface.

Data sources (all free, public, no authentication required):
  1. Google News RSS  — https://news.google.com/rss/search
  2. Bing News RSS    — https://www.bing.com/news/search?format=rss
  3. Fallback: Tavily web search

Output dimensions:
  - growth_strategy  (growth-related news, strategy shifts, partnerships)
  - market_change    (market dynamics, competitor moves, industry shifts)
"""

from __future__ import annotations

import re
import time
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote

import httpx
from lxml import etree

from app.infrastructure.tools.research_source import (
    EvidenceItem,
    ResearchSource,
    SourceResult,
    SourceType,
)
from app.infrastructure.tools.tavily_tool import tavily_search
from app.infrastructure.trace import trace_collector


_HTTP_TIMEOUT = 15.0
_MAX_RESULTS = 8

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# Growth/strategy keywords for dimension inference
_GROWTH_KEYWORDS = [
    "增长", "策略", "融资", "上市", "扩张", "收购", "合作",
    "增长", "用户", "DAU", "MAU", "营收", "收入", "投资",
    "growth", "strategy", "funding", "acquisition", "invest",
    "expansion", "partnership", "user growth", "revenue",
]

_MARKET_KEYWORDS = [
    "市场", "竞争", "竞品", "行业", "监管", "政策", "份额",
    "market", "competition", "industry", "regulation",
    "market share", "competitive",
]


class NewsSource(ResearchSource):
    """News data via Google News RSS + Bing News RSS."""

    @property
    def name(self) -> str:
        return "News Search"

    @property
    def source_type(self) -> str:
        return SourceType.NEWS

    async def search(self, query: str, context: Optional[dict] = None) -> SourceResult:
        task_id = (context or {}).get("task_id", "unknown")
        start = time.time()

        trace = trace_collector.start_trace(
            task_id=task_id, stage="search_tool", agent_name="research",
            input_summary=f"News: {query[:100]}",
            metadata={"source": "news", "query": query},
        )

        # Try Google News RSS first, then Bing
        items = await self._fetch_google_news(query)
        if not items:
            items = await self._fetch_bing_news(query)

        # Fallback: Tavily
        if not items:
            items = await self._fallback_tavily(query)

        duration_ms = int((time.time() - start) * 1000)

        trace_collector.end_trace(
            trace, success=True,
            output_summary=f"News: {len(items)} items",
            metadata={"duration_ms": duration_ms, "result_count": len(items)},
        )

        return SourceResult(
            items=items, source_type=SourceType.NEWS,
            source_name=self.name,
            status="success" if items else "no_data",
            total_found=len(items), duration_ms=duration_ms,
        )

    # ── Google News RSS ──

    async def _fetch_google_news(self, query: str) -> list[EvidenceItem]:
        """Fetch news from Google News RSS."""
        url = "https://news.google.com/rss/search"
        params = {"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=_HEADERS)
                resp.raise_for_status()
        except Exception:
            return []

        return self._parse_rss(resp.text, "Google News")

    # ── Bing News RSS ──

    async def _fetch_bing_news(self, query: str) -> list[EvidenceItem]:
        """Fetch news from Bing News RSS."""
        url = f"https://www.bing.com/news/search?q={quote(query)}&format=rss"

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers=_HEADERS)
                resp.raise_for_status()
        except Exception:
            return []

        return self._parse_rss(resp.text, "Bing News")

    # ── RSS Parser ──

    def _parse_rss(self, xml_text: str, source_label: str) -> list[EvidenceItem]:
        """Parse RSS XML and extract news items."""
        try:
            root = etree.fromstring(xml_text.encode("utf-8"))
        except Exception:
            return []

        items: list[EvidenceItem] = []
        # Handle both RSS and Atom namespaces
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
            "media": "http://search.yahoo.com/mrss/",
        }

        # Try RSS <item> elements
        item_els = root.findall(".//item")
        if not item_els:
            # Try Atom <entry> elements
            item_els = root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for el in item_els[: _MAX_RESULTS]:
            title = self._el_text(el, "title")
            link = self._el_text(el, "link")
            desc = self._el_text(el, "description")
            pub_date = self._el_text(el, "pubDate")

            # Clean description (strip HTML)
            if desc:
                desc = re.sub(r"<[^>]+>", " ", desc)
                desc = re.sub(r"\s+", " ", desc).strip()

            # Clean title
            if title:
                title = title.strip()

            if not title and not link:
                continue

            # Parse date
            formatted_date = ""
            if pub_date:
                try:
                    dt = parsedate_to_datetime(pub_date)
                    formatted_date = dt.strftime("%Y-%m-%d")
                except Exception:
                    formatted_date = ""

            # Infer dimension
            text = f"{title} {desc}".lower()
            if any(kw in text for kw in _GROWTH_KEYWORDS):
                dimension = "growth_strategy"
            elif any(kw in text for kw in _MARKET_KEYWORDS):
                dimension = "market_change"
            else:
                dimension = "growth_strategy"  # default for news

            # Extract source name from title (Google News format: "Title - Source")
            source_name = source_label
            title_match = re.search(r"\s+-\s+([^-]+)$", title)
            if title_match:
                source_name = title_match.group(1).strip()

            items.append(EvidenceItem(
                source_type=SourceType.NEWS,
                source_name=f"{source_label} ({source_name})",
                title=title[:200] if title else "新闻",
                url=link,
                content=desc[:1500] if desc else title,
                published_date=formatted_date,
                author=source_name,
                metrics={"source": source_label},
                dimension=dimension,
                confidence="medium",
            ))

        return items

    # ── Fallback ──

    async def _fallback_tavily(self, query: str) -> list[EvidenceItem]:
        """Fallback: search for news via Tavily."""
        result = await tavily_search(
            query=f"{query} 新闻 最新",
            max_results=5,
            search_depth="basic",
            include_raw_content=False,
        )
        if not result.items:
            return []

        return [EvidenceItem(
            source_type=SourceType.NEWS,
            source_name=f"{self.name} (via Tavily)",
            title=r.get("title", ""),
            url=r.get("url", ""),
            content=r.get("content", "")[:1500],
            published_date=r.get("published_date", ""),
            metrics={"score": r.get("score", 0.0), "fallback": True},
            dimension="growth_strategy",
            confidence="low",
        ) for r in result.items[:5]]

    # ── Helpers ──

    @staticmethod
    def _el_text(el, tag: str) -> str:
        """Get text from element with optional namespace."""
        child = el.find(tag)
        if child is None:
            # Try with namespace
            for ns in ["{http://www.w3.org/2005/Atom}", "{http://purl.org/rss/1.0/}"]:
                child = el.find(f"{ns}{tag}")
                if child is not None:
                    break
        if child is None:
            return ""
        text = child.text or ""
        # Also check for atom link href
        if tag == "link" and not text:
            text = child.get("href", "")
        return text.strip()


# ── Singleton ──

news_source = NewsSource()
