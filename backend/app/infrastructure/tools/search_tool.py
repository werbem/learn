"""Real search/scraper tools with graceful degradation.

Each tool attempts real HTTP requests first.
When network / API keys are unavailable, falls back to generated mock data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from app.infrastructure.trace import trace_collector, TraceStatus

import httpx
import lxml.html


@dataclass
class SearchResult:
    items: list[dict] = field(default_factory=list)
    status: str = "success"  # success | rate_limited | blocked | no_data
    total_found: int = 0
    error: Optional[str] = None


_HTTP_TIMEOUT = 15.0  # seconds
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


# ── Helpers ──

def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT,
        headers=_HTTP_HEADERS,
        follow_redirects=True,
    )


def _extract_text(html: str, max_len: int = 5000) -> str:
    """Extract readable text from HTML."""
    try:
        doc = lxml.html.fromstring(html)
        # Remove script/style
        for tag in doc.xpath("//script | //style | //nav | //footer | //header"):
            tag.drop_tree()
        text = doc.text_content()
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_len]
    except Exception:
        return "[提取失败]"


def _extract_meta(doc: lxml.html.HtmlElement) -> dict:
    """Extract meta description and title."""
    title = doc.findtext(".//title", "")
    desc = ""
    for meta in doc.xpath("//meta[@name='description']"):
        desc = meta.get("content", "")
    return {"title": title.strip(), "description": desc.strip()}


# ── Google Play 信息提取 ──

def _extract_play_store_info(app_id: str, html: str) -> dict:
    """Extract structured info from Google Play page HTML."""
    doc = lxml.html.fromstring(html)
    info: dict = {
        "app_id": app_id,
        "source": "google_play",
    }

    # Title
    title_el = doc.xpath("//h1[@itemprop='name']")
    if title_el:
        info["title"] = title_el[0].text_content().strip()

    # Rating
    rating_el = doc.xpath("//div[@itemprop='starRating']//meta[@itemprop='ratingValue']")
    if rating_el:
        info["rating"] = rating_el[0].get("content", "")

    # Installs
    installs_el = doc.xpath("//div[@itemprop='numDownloads']")
    if installs_el:
        info["installs"] = installs_el[0].text_content().strip()

    # Description
    desc_el = doc.xpath("//div[@itemprop='description']")
    if desc_el:
        info["description"] = _extract_text(
            lxml.html.tostring(desc_el[0], encoding="unicode"),
            2000,
        )

    # Genre/Category
    genre_el = doc.xpath("//a[@itemprop='genre']")
    if genre_el:
        info["genre"] = genre_el[0].text_content().strip()

    return info


# ── Tool Classes ──


class WebScraperTool:
    """Fetches a URL and extracts structured content.

    Primary:   httpx GET + lxml text extraction
    Fallback:  generated mock text
    """

    async def fetch(
        self,
        url: str,
        extract_meta: bool = False,
    ) -> SearchResult:
        items: list[dict] = []
        try:
            async with _make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:
            # Fallback: generate plausible-looking content
            items.append({
                "url": url,
                "content": f"[MOCK] {url} 的内容摘要。由于网络请求失败 ({exc})，此处为生成内容。",
                "status": "fallback",
                "error": str(exc),
            })
            return SearchResult(items=items, status="blocked", total_found=1)

        text = _extract_text(html, max_len=5000)
        item = {
            "url": url,
            "content": text,
            "status": "success",
        }
        if extract_meta:
            doc = lxml.html.fromstring(html)
            meta = _extract_meta(doc)
            item["title"] = meta["title"]
            item["description"] = meta["description"]

        items.append(item)
        return SearchResult(items=items, status="success", total_found=1)


class WebSearchTool:
    """Web search via DuckDuckGo lite (no API key required).

    Primary:   GET https://lite.duckduckgo.com/lite/ with q=keywords
    Fallback:  generated mock search results
    """

    async def search(
        self,
        keywords: list[str],
        max_results: int = 5,
    ) -> SearchResult:
        query = " ".join(keywords)
        items: list[dict] = []

        try:
            async with _make_client() as client:
                resp = await client.get(
                    "https://lite.duckduckgo.com/lite/",
                    params={"q": query},
                )
                resp.raise_for_status()
                doc = lxml.html.fromstring(resp.text)

                # DuckDuckGo lite results are in <a class="result-link">
                for link in doc.xpath("//a[contains(@class, 'result-link')]"):
                    if len(items) >= max_results:
                        break
                    href = link.get("href", "")
                    title = link.text_content().strip()
                    snippet = ""
                    # Sibling result-snippet
                    parent = link.getparent()
                    if parent is not None:
                        sib = parent.xpath(
                            "following-sibling::tr//td[@class='result-snippet']"
                        )
                        if sib:
                            snippet = sib[0].text_content().strip()
                    items.append({
                        "title": title,
                        "url": href,
                        "snippet": snippet,
                        "source": "duckduckgo",
                    })
        except Exception as exc:
            # Fallback mock results
            for i, kw in enumerate(keywords[:max_results]):
                items.append({
                    "title": f"[MOCK] 关于「{kw}」的搜索结果",
                    "url": f"https://example.com/search/{kw}",
                    "snippet": f"[MOCK] 这是关于 {kw} 的搜索结果摘要，用于演示证据采集流程。",
                    "source": "mock",
                })
            return SearchResult(
                items=items,
                status="fallback",
                total_found=len(items),
                error=str(exc),
            )

        return SearchResult(items=items, status="success", total_found=len(items))


class AppStoreSearchTool:
    """iOS App Store search via iTunes Search API (free, no key).

    Primary:   GET https://itunes.apple.com/search with entity=software
    Fallback:  generated mock

    Also fetches user reviews from the RSS feed.
    """

    async def search(self, app_name: str, country: str = "cn") -> SearchResult:
        items: list[dict] = []

        try:
            async with _make_client() as client:
                # Search for the app
                resp = await client.get(
                    "https://itunes.apple.com/search",
                    params={
                        "term": app_name,
                        "entity": "software",
                        "country": country,
                        "limit": 5,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])

                for app in results:
                    item = {
                        "track_id": app.get("trackId"),
                        "app_name": app.get("trackName"),
                        "seller": app.get("sellerName"),
                        "description": app.get("description", ""),
                        "rating": app.get("averageUserRating"),
                        "rating_count": app.get("userRatingCount"),
                        "price": app.get("formattedPrice"),
                        "category": (
                            app.get("primaryGenreName")
                            if app.get("primaryGenreName")
                            else ""
                        ),
                        "icon_url": app.get("artworkUrl100", ""),
                        "version": app.get("version", ""),
                        "size": app.get("fileSizeBytes"),
                        "languages": app.get("languageCodesISO2A", []),
                        "minimum_os": app.get("minimumOsVersion", ""),
                        "source": "app_store",
                        "url": app.get("trackViewUrl", ""),
                    }
                    items.append(item)

                    # Try to fetch reviews
                    if app.get("trackId"):
                        try:
                            reviews = await self._fetch_reviews(
                                app["trackId"], country
                            )
                            item["reviews"] = reviews[:5]
                        except Exception:
                            item["reviews"] = []
        except Exception as exc:
            items.append({
                "app_name": app_name,
                "description": f"[MOCK] {app_name} 是一款iOS应用，提供相关功能。",
                "rating": 4.2,
                "rating_count": 1500,
                "source": "mock_app_store",
                "reviews": [
                    {"rating": 5, "title": "很好用", "content": "[MOCK] 体验不错", "author": "用户A"},
                    {"rating": 4, "title": "功能丰富", "content": "[MOCK] 功能比较全面", "author": "用户B"},
                ],
            })
            return SearchResult(
                items=items, status="fallback", total_found=len(items), error=str(exc),
            )

        return SearchResult(items=items, status="success", total_found=len(items))

    async def _fetch_reviews(self, track_id: int, country: str) -> list[dict]:
        """Fetch user reviews from Apple's RSS feed."""
        reviews: list[dict] = []
        async with _make_client() as client:
            url = (
                f"https://itunes.apple.com/{country}/rss/customerreviews/"
                f"id={track_id}/sortBy=mostRecent/json"
            )
            resp = await client.get(url)
            if resp.status_code != 200:
                return reviews
            data = resp.json()
            feed = data.get("feed", {})
            entries = feed.get("entry", [])
            for entry in entries[1:]:  # Skip first entry (app metadata)
                reviews.append({
                    "rating": entry.get("im:rating", {}).get("label", ""),
                    "title": entry.get("title", {}).get("label", ""),
                    "content": entry.get("content", {}).get("label", ""),
                    "author": entry.get("author", {}).get("name", {}).get("label", ""),
                    "version": entry.get("im:version", {}).get("label", ""),
                })
        return reviews


class GooglePlaySearchTool:
    """Google Play Store search.

    Primary:   GET https://play.google.com/store/apps with q=query
    Fallback:  generated mock
    """

    async def search(self, app_name: str) -> SearchResult:
        items: list[dict] = []

        try:
            query = app_name.replace(" ", "+")
            url = f"https://play.google.com/store/search?q={query}&c=apps"
            async with _make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
                doc = lxml.html.fromstring(resp.text)

                # Try to find app cards
                cards = doc.xpath(
                    "//div[contains(@class, 'card') or contains(@class, 'Vpfmgd')]"
                )
                for card in cards[:5]:
                    title_el = card.xpath(".//div[contains(@class, 'WsMG1c')]")
                    subtitle_el = card.xpath(".//div[contains(@class, 'wXUyZd')]")

                    item: dict = {
                        "app_name": title_el[0].text_content().strip() if title_el else app_name,
                        "source": "google_play",
                        "genre": subtitle_el[0].text_content().strip() if subtitle_el else "",
                    }
                    items.append(item)
        except Exception as exc:
            items.append({
                "app_name": app_name,
                "rating": 4.0,
                "installs": "100,000+",
                "description": f"[MOCK] {app_name} 的Google Play信息。",
                "source": "mock_google_play",
                "genre": "工具",
            })
            return SearchResult(
                items=items, status="fallback", total_found=len(items), error=str(exc),
            )

        return SearchResult(items=items, status="success", total_found=len(items))

    async def fetch_app_details(self, app_id: str) -> dict:
        """Fetch detailed info for a specific Play Store app by package name."""
        try:
            url = f"https://play.google.com/store/apps/details?id={app_id}"
            async with _make_client() as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return _extract_play_store_info(app_id, resp.text)
        except Exception as exc:
            return {
                "app_id": app_id,
                "title": app_id,
                "description": f"[MOCK] {app_id} 的应用详情",
                "source": "mock_google_play",
                "error": str(exc),
            }


class NewsSearchTool:
    """News search via RSS / public sources.

    Primary:   Google News RSS (no key)
    Fallback:  generated mock
    """

    async def search(self, keywords: list[str], max_results: int = 8) -> SearchResult:
        query = " ".join(keywords)
        items: list[dict] = []

        try:
            # Google News RSS
            url = "https://news.google.com/rss/search"
            async with _make_client() as client:
                resp = await client.get(url, params={"q": query, "hl": "zh-CN", "gl": "CN"})
                resp.raise_for_status()
                doc = lxml.html.fromstring(resp.text)

                for item_el in doc.xpath("//item")[:max_results]:
                    title = item_el.findtext("title", "")
                    link = item_el.findtext("link", "")
                    pub_date = item_el.findtext("pubDate", "")
                    source_el = item_el.find("source")
                    items.append({
                        "title": title,
                        "url": link,
                        "published_at": pub_date,
                        "source_name": source_el.text if source_el is not None else "Google News",
                        "source": "google_news",
                    })
        except Exception as exc:
            # Fallback mock news
            today = datetime.utcnow().strftime("%Y-%m-%d")
            for kw in keywords[:max_results]:
                items.append({
                    "title": f"[MOCK] {kw} 获得新一轮融资",
                    "url": f"https://news.example.com/{kw}",
                    "published_at": today,
                    "source_name": "36氪",
                    "snippet": f"[MOCK] 据消息人士透露，{kw} 近期完成了新一轮融资...",
                    "source": "mock_news",
                })
            return SearchResult(
                items=items, status="fallback", total_found=len(items), error=str(exc),
            )

        return SearchResult(items=items, status="success", total_found=len(items))


class SocialMediaSearchTool:
    """Social media search (limited to public content).

    Primary:   attempts to fetch from public pages
    Fallback:  generated mock posts / comments
    """

    async def search(
        self,
        platform: str,
        keywords: list[str],
        max_results: int = 6,
    ) -> SearchResult:
        query = " ".join(keywords)
        items: list[dict] = []

        if platform == "zhihu":
            try:
                url = f"https://www.zhihu.com/search?q={query}&type=content"
                async with _make_client() as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    doc = lxml.html.fromstring(resp.text)
                    for result in doc.xpath("//div[@data-za-module='SearchResultItem']")[:max_results]:
                        title_el = result.xpath(".//h2//a")
                        excerpt_el = result.xpath(".//span[@class='RichText']")
                        if title_el:
                            items.append({
                                "title": title_el[0].text_content().strip(),
                                "excerpt": excerpt_el[0].text_content().strip() if excerpt_el else "",
                                "platform": "zhihu",
                                "source": "zhihu",
                            })
            except Exception:
                pass

            # Fallback if zhihu request failed or no results
            if not items:
                for kw in keywords[:max_results]:
                    items.append({
                        "title": f"[MOCK] 知乎：关于「{kw}」的讨论",
                        "excerpt": f"[MOCK] 这是知乎上关于 {kw} 的一条热门讨论，"
                                   f"有 120 个回答和 3500 个关注。",
                        "platform": "zhihu",
                        "source": "mock_zhihu",
                    })
        else:
            # Other platforms (xiaohongshu, weibo, etc.) — mock
            for kw in keywords[:max_results]:
                items.append({
                    "title": f"[MOCK] {platform}：{kw} 相关讨论",
                    "content": f"[MOCK] 这是 {platform} 上关于 {kw} 的热门内容。",
                    "platform": platform,
                    "source": f"mock_{platform}",
                })

        return SearchResult(items=items, status="success", total_found=len(items))


# ── Singleton instances ──
web_search = WebSearchTool()
web_scraper = WebScraperTool()
app_store_search = AppStoreSearchTool()
google_play_search = GooglePlaySearchTool()
news_search = NewsSearchTool()
social_search = SocialMediaSearchTool()
