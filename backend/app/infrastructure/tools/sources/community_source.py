"""Community Research Source — implements ResearchSource interface.

Sources (all public, free, no authentication):
  1. Reddit — JSON API https://www.reddit.com/search.json
  2. 知乎 — search page https://www.zhihu.com/search
  3. 小红书 — Tavily search fallback (site heavily JS-rendered)

Output:
  EvidenceItem with sentiment field (positive/negative/neutral)
  Dimension: user_feedback
"""

from __future__ import annotations

import re
import time
from typing import Optional

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
_MAX_RESULTS = 10

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0; +https://example.com/bot)",
}

# Keyword-based sentiment detection
_POSITIVE_CN = {"好", "赞", "喜欢", "推荐", "优秀", "方便", "好用", "满意", "不错",
                "棒", "强", "厉害", "舒服", "流畅", "完美", "惊喜", "值得", "良心"}
_NEGATIVE_CN = {"差", "不好", "问题", "投诉", "垃圾", "难用", "失望", "坑", "烂",
                "bug", "卡", "慢", "崩溃", "闪退", "贵", "不值", "后悔", "骗"}
_POSITIVE_EN = {"great", "love", "good", "excellent", "amazing", "awesome",
                "best", "fantastic", "wonderful", "perfect", "solid"}
_NEGATIVE_EN = {"bad", "terrible", "awful", "worst", "hate", "horrible",
                "garbage", "trash", "broken", "useless", "poor", "disappointed"}


class CommunitySource(ResearchSource):
    """Community feedback from Reddit + 知乎 + 小红书."""

    @property
    def name(self) -> str:
        return "Community Search"

    @property
    def source_type(self) -> str:
        return SourceType.SOCIAL

    async def search(self, query: str, context: Optional[dict] = None) -> SourceResult:
        task_id = (context or {}).get("task_id", "unknown")
        start = time.time()

        trace = trace_collector.start_trace(
            task_id=task_id, stage="search_tool", agent_name="research",
            input_summary=f"Community: {query[:100]}",
            metadata={"source": "community", "query": query},
        )

        items: list[EvidenceItem] = []

        # Try Reddit
        reddit_items = await self._fetch_reddit(query)
        items.extend(reddit_items)

        # Try Zhihu
        zhihu_items = await self._fetch_zhihu(query)
        items.extend(zhihu_items)

        # Fallback: Tavily for Reddit/Zhihu/Xiaohongshu discussions
        if not items:
            items = await self._fallback_tavily(query)

        duration_ms = int((time.time() - start) * 1000)

        trace_collector.end_trace(
            trace, success=True,
            output_summary=f"Community: {len(items)} items (reddit={len(reddit_items)}, zhihu={len(zhihu_items)})",
            metadata={"duration_ms": duration_ms, "result_count": len(items)},
        )

        return SourceResult(
            items=items, source_type=SourceType.SOCIAL,
            source_name=self.name,
            status="success" if items else "no_data",
            total_found=len(items), duration_ms=duration_ms,
        )

    # ── Reddit JSON API ──

    async def _fetch_reddit(self, query: str) -> list[EvidenceItem]:
        """Fetch Reddit posts via public JSON API."""
        url = "https://www.reddit.com/search.json"
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(
                    url, params={"q": query, "limit": 5, "sort": "relevance"},
                    headers=_REDDIT_HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        children = data.get("data", {}).get("children", [])
        if not children:
            return []

        items: list[EvidenceItem] = []
        for child in children[:_MAX_RESULTS]:
            post = child.get("data", {})
            title = post.get("title", "")
            selftext = post.get("selftext", "")[:1000]
            subreddit = post.get("subreddit_name_prefixed", "reddit")
            score = post.get("score", 0)
            num_comments = post.get("num_comments", 0)
            permalink = post.get("permalink", "")
            created_utc = post.get("created_utc", 0)

            url_full = f"https://www.reddit.com{permalink}" if permalink else ""
            content = selftext if selftext else title
            date = self._ts_to_date(created_utc)

            sentiment = self._detect_sentiment(f"{title} {selftext}")

            items.append(EvidenceItem(
                source_type=SourceType.SOCIAL,
                source_name=f"Reddit r/{subreddit}",
                title=title[:200],
                url=url_full,
                content=content[:1500],
                published_date=date,
                author=f"r/{subreddit}",
                metrics={
                    "score": score,
                    "comments": num_comments,
                    "subreddit": subreddit,
                    "platform": "reddit",
                },
                dimension="user_feedback",
                confidence="medium",
                sentiment=sentiment,
            ))

        return items

    # ── Zhihu Search ──

    async def _fetch_zhihu(self, query: str) -> list[EvidenceItem]:
        """Fetch Zhihu search results via page scraping."""
        url = "https://www.zhihu.com/search"
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(
                    url, params={"q": query, "type": "content"},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                html = resp.text
        except Exception:
            return []

        try:
            doc = lxml_html.fromstring(html)
        except Exception:
            return []

        items: list[EvidenceItem] = []
        # Search result cards
        for card in doc.xpath('//div[contains(@class,"List-item") or contains(@class,"SearchResult-Card")]'):
            title_el = card.xpath('.//h2//a | .//a[contains(@data-za-detail-view-id,"title")]')
            excerpt_el = card.xpath('.//span[contains(@class,"RichText")] | .//div[contains(@class,"SearchItem-excerpt")]')
            meta_el = card.xpath('.//div[contains(@class,"meta")]')

            title = title_el[0].text_content().strip() if title_el else ""
            excerpt = excerpt_el[0].text_content().strip() if excerpt_el else ""
            url = title_el[0].get("href", "") if title_el else ""
            if url and not url.startswith("http"):
                url = f"https://www.zhihu.com{url}"

            if not title:
                continue

            sentiment = self._detect_sentiment(f"{title} {excerpt}")

            items.append(EvidenceItem(
                source_type=SourceType.SOCIAL,
                source_name="知乎",
                title=title[:200],
                url=url,
                content=excerpt[:1500] if excerpt else title,
                published_date="",
                author="",
                metrics={"platform": "zhihu", "votes": 0},
                dimension="user_feedback",
                confidence="medium",
                sentiment=sentiment,
            ))

            if len(items) >= _MAX_RESULTS:
                break

        return items

    # ── Fallback: Tavily ──

    async def _fallback_tavily(self, query: str) -> list[EvidenceItem]:
        """Fallback: search Reddit/Zhihu/Xiaohongshu via Tavily."""
        results: list[EvidenceItem] = []

        for platform, site in [("Reddit", "reddit.com"), ("知乎", "zhihu.com"), ("小红书", "xiaohongshu.com")]:
            try:
                r = await tavily_search(
                    query=f"site:{site} {query}",
                    max_results=3,
                    search_depth="basic",
                    include_raw_content=False,
                )
                for item in r.items[:3]:
                    sentiment = self._detect_sentiment(
                        f"{item.get('title', '')} {item.get('content', '')}"
                    )
                    results.append(EvidenceItem(
                        source_type=SourceType.SOCIAL,
                        source_name=f"{platform} (via Tavily)",
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        content=item.get("content", "")[:1500],
                        published_date=item.get("published_date", ""),
                        metrics={"score": item.get("score", 0.0), "platform": platform.lower(), "fallback": True},
                        dimension="user_feedback",
                        confidence="low",
                        sentiment=sentiment,
                    ))
            except Exception:
                continue

        return results

    # ── Sentiment Detection ──

    @staticmethod
    def _detect_sentiment(text: str) -> str:
        """Simple keyword-based sentiment detection."""
        text_lower = text.lower()
        pos_count = sum(1 for w in _POSITIVE_CN if w in text_lower) + sum(1 for w in _POSITIVE_EN if w in text_lower)
        neg_count = sum(1 for w in _NEGATIVE_CN if w in text_lower) + sum(1 for w in _NEGATIVE_EN if w in text_lower)

        if pos_count > neg_count:
            return "positive"
        elif neg_count > pos_count:
            return "negative"
        return "neutral"

    # ── Helpers ──

    @staticmethod
    def _ts_to_date(ts: float) -> str:
        """Convert Unix timestamp to date string."""
        if not ts:
            return ""
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


# ── Singleton ──

community_source = CommunitySource()
