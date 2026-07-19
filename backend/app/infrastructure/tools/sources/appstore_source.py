"""Apple App Store Research Source — implements ResearchSource interface.

Data sources (all free, public, no authentication required):
  1. iTunes Search API — app metadata (name, rating, version, etc.)
     https://itunes.apple.com/search
  2. Customer Reviews RSS — recent reviews
     https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/json
  3. Fallback: Tavily web search for app store pages

Limitations:
  - No authentication/key required (public APIs)
  - Reviews feed may return empty for some apps
  - Rate limiting: Apple recommends max ~20 requests/min
"""

from __future__ import annotations

import time
from typing import Optional
from urllib.parse import quote

import httpx

from app.infrastructure.tools.research_source import (
    EvidenceItem,
    ResearchSource,
    SourceResult,
    SourceType,
)
from app.infrastructure.tools.tavily_tool import tavily_search
from app.infrastructure.trace import trace_collector, TraceStatus


# ── API Endpoints ──

_ITUNES_SEARCH = "https://itunes.apple.com/search"
_REVIEWS_RSS = "https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/sortBy=mostRecent/json"

_HTTP_TIMEOUT = 15.0
_MAX_APP_RESULTS = 5
_MAX_REVIEWS = 10


class AppStoreSource(ResearchSource):
    """Apple App Store public data via iTunes Search API + Reviews RSS.

    Retrieves:
      - App metadata: name, rating, rating count, version, genre, seller
      - Update history: release date, current version release date
      - Reviews: recent user reviews (title + content + rating)
      - Fallback: Tavily web search when iTunes API returns no results
    """

    def __init__(self, country: str = "cn"):
        self._country = country

    @property
    def name(self) -> str:
        return "Apple App Store"

    @property
    def source_type(self) -> str:
        return SourceType.APP_STORE

    async def search(
        self,
        query: str,
        context: Optional[dict] = None,
    ) -> SourceResult:
        task_id = (context or {}).get("task_id", "unknown")
        start = time.time()

        # --- Trace ---
        trace = trace_collector.start_trace(
            task_id=task_id,
            stage="search_tool",
            agent_name="research",
            input_summary=f"AppStore: {query[:100]}",
            metadata={"source": "app_store", "query": query, "country": self._country},
        )

        # Step 1: Search via iTunes API
        app_items = await self._search_itunes(query)

        if not app_items:
            # Step 2: Fallback — use Tavily to search app store pages
            app_items = await self._fallback_tavily(query)

        # Step 3: Try to fetch reviews for the top app
        if app_items:
            reviews = await self._fetch_reviews(app_items[0])
            app_items.extend(reviews)

        duration_ms = int((time.time() - start) * 1000)

        if not app_items:
            trace_collector.end_trace(
                trace, success=True,
                output_summary="AppStore: no results",
                metadata={"duration_ms": duration_ms, "query": query, "result_count": 0},
            )
            return SourceResult(
                items=[],
                source_type=SourceType.APP_STORE,
                source_name=self.name,
                status="no_data",
                total_found=0,
                duration_ms=duration_ms,
            )

        trace_collector.end_trace(
            trace, success=True,
            output_summary=f"AppStore: {len(app_items)} items for '{query[:80]}'",
            metadata={"duration_ms": duration_ms, "query": query, "result_count": len(app_items)},
        )

        return SourceResult(
            items=app_items,
            source_type=SourceType.APP_STORE,
            source_name=self.name,
            status="success",
            total_found=len(app_items),
            duration_ms=duration_ms,
        )

    # ── iTunes Search API ──

    async def _search_itunes(self, query: str) -> list[EvidenceItem]:
        """Search iTunes for apps matching the query."""
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(
                    _ITUNES_SEARCH,
                    params={
                        "term": query,
                        "country": self._country,
                        "entity": "software",
                        "limit": _MAX_APP_RESULTS,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        results = data.get("results", [])
        if not results:
            return []

        items: list[EvidenceItem] = []
        for app in results:
            track_id = app.get("trackId")
            track_name = app.get("trackName", "")
            rating = app.get("averageUserRating")
            rating_count = app.get("userRatingCount", 0)
            version = app.get("version", "")
            genre = app.get("primaryGenreName", "")
            seller = app.get("sellerName", "")
            description = app.get("description", "")[:500]
            release_date = app.get("releaseDate", "")[:10]
            current_release_date = app.get("currentVersionReleaseDate", "")[:10]
            track_url = app.get("trackViewUrl", f"https://apps.apple.com/cn/app/id{track_id}")

            # Build content string
            content_parts = []
            if description:
                content_parts.append(description)
            if rating is not None:
                content_parts.append(f"评分: {rating}/5 ({rating_count} 个评分)")
            if version:
                content_parts.append(f"当前版本: {version}")
            if seller:
                content_parts.append(f"开发商: {seller}")
            if genre:
                content_parts.append(f"类别: {genre}")

            evidence = EvidenceItem(
                source_type=SourceType.APP_STORE,
                source_name=self.name,
                title=f"{track_name} (App Store)",
                url=track_url,
                content=" | ".join(content_parts),
                published_date=current_release_date or release_date,
                author=seller,
                metrics={
                    "rating": rating,
                    "rating_count": rating_count,
                    "version": version,
                    "genre": genre,
                    "app_id": str(track_id) if track_id else "",
                    "release_date": release_date,
                },
                dimension="user_experience",
                confidence="high",
            )
            items.append(evidence)

        return items

    # ── Reviews RSS ──

    async def _fetch_reviews(self, app_item: EvidenceItem) -> list[EvidenceItem]:
        """Fetch recent customer reviews for an app via RSS feed."""
        app_id = app_item.metrics.get("app_id", "")
        app_name = app_item.title.replace(" (App Store)", "")
        if not app_id:
            return []

        url = _REVIEWS_RSS.format(country=self._country, app_id=app_id)

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        entries = data.get("feed", {}).get("entry", [])
        if not entries or len(entries) <= 1:
            return []

        items: list[EvidenceItem] = []
        count = 0
        for entry in entries[1:]:  # Skip first entry (app metadata, not a review)
            if count >= _MAX_REVIEWS:
                break

            title = entry.get("title", {}).get("label", "")
            content = entry.get("content", {}).get("label", "")
            rating_label = entry.get("im:rating", {}).get("label", "")
            author = entry.get("author", {}).get("name", {}).get("label", "")
            updated = entry.get("updated", {}).get("label", "")[:10]

            if not content:
                continue

            review = EvidenceItem(
                source_type=SourceType.APP_STORE,
                source_name=self.name,
                title=f"{app_name} 用户评价: {title[:80]}" if title else f"{app_name} 用户评价",
                url=f"https://apps.apple.com/cn/app/id{app_id}",
                content=f"评分: {rating_label}/5 | {content[:500]}",
                published_date=updated,
                author=author,
                metrics={
                    "rating": int(rating_label) if rating_label.isdigit() else None,
                    "app_id": app_id,
                    "review_type": "user_review",
                },
                dimension="user_experience",
                confidence="medium",
            )
            items.append(review)
            count += 1

        return items

    # ── Fallback: Tavily ──

    async def _fallback_tavily(self, query: str) -> list[EvidenceItem]:
        """Fallback: search for app store pages via Tavily web search."""
        result = await tavily_search(
            query=f"{query} App Store",
            max_results=3,
            search_depth="basic",
            include_raw_content=False,
        )

        if not result.items:
            return []

        items: list[EvidenceItem] = []
        for r in result.items[:3]:
            items.append(EvidenceItem(
                source_type=SourceType.APP_STORE,
                source_name=f"{self.name} (via Tavily)",
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", "")[:1000],
                published_date=r.get("published_date", ""),
                metrics={
                    "score": r.get("score", 0.0),
                    "fallback": True,
                },
                dimension="user_experience",
                confidence="low",
            ))

        return items


# ── Singleton ──

appstore_source = AppStoreSource()
