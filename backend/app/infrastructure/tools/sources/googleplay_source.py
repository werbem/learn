"""Google Play Research Source — implements ResearchSource interface.

Data sources (all public, free, no authentication required):
  1. Google Play Store search — find app IDs
  2. App detail page — JSON-LD structured data via asyncio.to_thread
  3. Fallback: Tavily web search
"""

from __future__ import annotations

import asyncio as _asyncio
import json
import re
import time
from typing import Optional

import httpx

from app.infrastructure.tools.research_source import (
    EvidenceItem,
    ResearchSource,
    SourceResult,
    SourceType,
)
from app.infrastructure.tools.tavily_tool import tavily_search
from app.infrastructure.trace import trace_collector

# ── API Endpoints ──

_PLAY_SEARCH = "https://play.google.com/store/search"
_PLAY_DETAIL = "https://play.google.com/store/apps/details"

_HTTP_TIMEOUT = 15.0
_MAX_APPS = 3
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class GooglePlaySource(ResearchSource):
    """Google Play Store public data via HTML scraping + JSON-LD."""

    def __init__(self, country: str = "us", language: str = "en"):
        self._country = country
        self._language = language

    @property
    def name(self) -> str:
        return "Google Play Store"

    @property
    def source_type(self) -> str:
        return SourceType.APP_STORE

    async def search(self, query: str, context: Optional[dict] = None) -> SourceResult:
        task_id = (context or {}).get("task_id", "unknown")
        start = time.time()

        trace = trace_collector.start_trace(
            task_id=task_id, stage="search_tool", agent_name="research",
            input_summary=f"GooglePlay: {query[:100]}",
            metadata={"source": "google_play", "query": query},
        )

        app_ids = await self._search_play_store(query)
        items: list[EvidenceItem] = []
        for app_id, app_name in app_ids[:_MAX_APPS]:
            evidence = await self._fetch_app_detail(app_id, app_name)
            if evidence:
                items.append(evidence)

        if not items:
            items = await self._fallback_tavily(query)

        duration_ms = int((time.time() - start) * 1000)

        trace_collector.end_trace(
            trace, success=True,
            output_summary=f"GooglePlay: {len(items)} items",
            metadata={"duration_ms": duration_ms, "result_count": len(items)},
        )

        return SourceResult(
            items=items, source_type=SourceType.APP_STORE,
            source_name=self.name,
            status="success" if items else "no_data",
            total_found=len(items), duration_ms=duration_ms,
        )

    async def _search_play_store(self, query: str) -> list[tuple[str, str]]:
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(_PLAY_SEARCH, params={
                    "q": query, "c": "apps",
                    "hl": self._language, "gl": self._country,
                }, headers=_HEADERS)
                resp.raise_for_status()
                html = resp.text
        except Exception:
            return []

        ids = re.findall(r'/store/apps/details\?id=([a-zA-Z0-9._]+)', html)
        seen: set[str] = set()
        results: list[tuple[str, str]] = []
        for pid in ids:
            if pid not in seen:
                seen.add(pid)
                results.append((pid, ""))
        return results[:_MAX_APPS]

    async def _fetch_app_detail(self, app_id: str, fallback_name: str = "") -> Optional[EvidenceItem]:
        url = f"{_PLAY_DETAIL}?id={app_id}&hl={self._language}&gl={self._country}"

        try:
            resp = await _asyncio.to_thread(httpx.get, url, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
        except Exception:
            return None

        ld_match = re.search(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        if not ld_match:
            return self._fallback_parse(app_id, html)

        try:
            ld = json.loads(ld_match.group(1))
        except json.JSONDecodeError:
            return self._fallback_parse(app_id, html)

        name = ld.get("name", fallback_name)
        description = ld.get("description", "")[:500]
        rating_data = ld.get("aggregateRating", {})
        rating = rating_data.get("ratingValue")
        rating_count = rating_data.get("ratingCount", 0)
        category = ld.get("applicationCategory", "")
        developer = ld.get("author", {}).get("name", "") if isinstance(ld.get("author"), dict) else ""

        content_parts = [description] if description else []
        if rating is not None:
            content_parts.append(f"评分: {rating}/5 ({rating_count} 个评分)")
        if category:
            content_parts.append(f"类别: {category}")

        installs = self._regex_extract(html, r'(\d[\d,]*[KMB]?\+?\s*(?:Downloads|下载))')
        version = self._regex_extract(html, r'Current\s*Version[^<]*</div><[^>]*>([^<]+)<')
        updated = self._regex_extract(html, r'Updated[^<]*</div><[^>]*>([^<]+)<')

        if installs:
            content_parts.append(f"下载量: {installs}")
        if version:
            content_parts.append(f"版本: {version}")
        if updated:
            content_parts.append(f"更新: {updated}")

        return EvidenceItem(
            source_type=SourceType.APP_STORE,
            source_name=self.name,
            title=f"{name} (Google Play)",
            url=url,
            content=" | ".join(content_parts),
            published_date=updated or "",
            author=developer,
            metrics={
                "rating": rating,
                "rating_count": rating_count,
                "installs": installs,
                "version": version,
                "category": category,
                "app_id": app_id,
                "url": f"https://play.google.com/store/apps/details?id={app_id}",
            },
            dimension="user_experience",
            confidence="high",
        )

    def _fallback_parse(self, app_id: str, html: str) -> Optional[EvidenceItem]:
        name = self._regex_extract(html, r'<h1[^>]*itemprop="name"[^>]*>(?:<span[^>]*>)?(.*?)(?:</span>)?</h1>')
        rating = self._regex_extract(html, r'aria-label="Rated\s+([\d.]+)\s+stars')
        reviews = self._regex_extract(html, r'(\d[\d,]*)\s*(?:reviews|条评价)')
        if not name:
            return None
        return EvidenceItem(
            source_type=SourceType.APP_STORE, source_name=self.name,
            title=f"{name.strip()} (Google Play)",
            url=f"https://play.google.com/store/apps/details?id={app_id}",
            content=f"评分: {rating}/5 | {reviews} 条评价" if rating else "评价信息未获取",
            metrics={"rating": float(rating) if rating else None, "rating_count": int(reviews.replace(",", "")) if reviews else 0, "app_id": app_id},
            dimension="user_experience", confidence="medium" if rating else "low",
        )

    async def _fallback_tavily(self, query: str) -> list[EvidenceItem]:
        result = await tavily_search(query=f"{query} Google Play app", max_results=3, search_depth="basic", include_raw_content=False)
        if not result.items:
            return []
        return [EvidenceItem(
            source_type=SourceType.APP_STORE, source_name=f"{self.name} (via Tavily)",
            title=r.get("title", ""), url=r.get("url", ""),
            content=r.get("content", "")[:800], published_date=r.get("published_date", ""),
            metrics={"score": r.get("score", 0.0), "fallback": True},
            dimension="user_experience", confidence="low",
        ) for r in result.items[:3]]

    @staticmethod
    def _regex_extract(html: str, pattern: str) -> str:
        m = re.search(pattern, html)
        return m.group(1).strip() if m else ""


googleplay_source = GooglePlaySource()
