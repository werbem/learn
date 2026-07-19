"""GitHub Research Source — implements ResearchSource interface.

Data sources (all free, public, no authentication required):
  1. GitHub REST API v3 — search repositories, details, releases
     https://api.github.com
  2. Fallback: Tavily web search for github.com pages

Rate limit: 60 req/hour without token (sufficient for competitive analysis)

Output dimensions:
  - technical_capability  (tech stack, language, architecture)
  - developer_ecosystem   (community health, activity, adoption)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
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


_HTTP_TIMEOUT = 15.0
_MAX_REPOS = 3

_GITHUB_API = "https://api.github.com"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)",
    "Accept": "application/vnd.github.v3+json",
}


class GitHubSource(ResearchSource):
    """GitHub public data via REST API v3."""

    @property
    def name(self) -> str:
        return "GitHub Open Source"

    @property
    def source_type(self) -> str:
        return SourceType.DEVELOPER

    async def search(self, query: str, context: Optional[dict] = None) -> SourceResult:
        task_id = (context or {}).get("task_id", "unknown")
        start = time.time()

        trace = trace_collector.start_trace(
            task_id=task_id, stage="search_tool", agent_name="research",
            input_summary=f"GitHub: {query[:100]}",
            metadata={"source": "github", "query": query},
        )

        # Step 1: Search repositories
        repos = await self._search_repos(query)

        # Step 2: Fetch details for top repos
        items: list[EvidenceItem] = []
        for repo_data in repos[:_MAX_REPOS]:
            detail = await self._fetch_repo_detail(repo_data)
            if detail:
                items.append(detail)

        # Step 3: Fallback — Tavily
        if not items:
            items = await self._fallback_tavily(query)

        duration_ms = int((time.time() - start) * 1000)

        trace_collector.end_trace(
            trace, success=True,
            output_summary=f"GitHub: {len(items)} items (repos={len(repos)})",
            metadata={"duration_ms": duration_ms, "result_count": len(items)},
        )

        return SourceResult(
            items=items, source_type=SourceType.DEVELOPER,
            source_name=self.name,
            status="success" if items else "no_data",
            total_found=len(items), duration_ms=duration_ms,
        )

    # ── Search ──

    async def _search_repos(self, query: str) -> list[dict]:
        """Search GitHub repositories."""
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(
                    f"{_GITHUB_API}/search/repositories",
                    params={"q": query, "sort": "stars", "per_page": _MAX_REPOS},
                    headers=_HEADERS,
                )
                resp.raise_for_status()
                return resp.json().get("items", [])
        except Exception:
            return []

    # ── Detail Fetch ──

    async def _fetch_repo_detail(self, repo_data: dict) -> Optional[EvidenceItem]:
        """Fetch detailed repo info and optionally releases."""
        full_name = repo_data.get("full_name", "")

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                detail_resp = await client.get(
                    f"{_GITHUB_API}/repos/{full_name}",
                    headers=_HEADERS,
                )
                detail_resp.raise_for_status()
                detail = detail_resp.json()

                # Try releases
                releases = []
                try:
                    rel_resp = await client.get(
                        f"{_GITHUB_API}/repos/{full_name}/releases",
                        params={"per_page": 2},
                        headers=_HEADERS,
                    )
                    if rel_resp.status_code == 200:
                        releases = rel_resp.json()
                except Exception:
                    pass

                # Try contributors
                contributor_count = 0
                try:
                    contr_resp = await client.get(
                        f"{_GITHUB_API}/repos/{full_name}/contributors",
                        params={"per_page": 1, "anon": "true"},
                        headers=_HEADERS,
                    )
                    if contr_resp.status_code == 200:
                        # Count via link header or first page
                        link = contr_resp.headers.get("Link", "")
                        if "last" in link:
                            import re
                            m = re.search(r"[&?]page=(\d+)", link.split("last")[0] if "last" in link else link)
                            if m:
                                contributor_count = int(m.group(1))
                        if contributor_count == 0:
                            contributor_count = len(contr_resp.json())
                except Exception:
                    pass
        except Exception:
            # Fallback: use search data only
            detail = repo_data
            releases = []
            contributor_count = 0

        return self._build_evidence(repo_data, detail, releases, contributor_count)

    def _build_evidence(
        self,
        repo_data: dict,
        detail: dict,
        releases: list,
        contributor_count: int,
    ) -> EvidenceItem:
        """Build EvidenceItem from GitHub API data."""
        full_name = repo_data.get("full_name", "")
        description = detail.get("description") or repo_data.get("description", "")
        stars = detail.get("stargazers_count", repo_data.get("stargazers_count", 0))
        forks = detail.get("forks_count", repo_data.get("forks_count", 0))
        open_issues = detail.get("open_issues_count", 0)
        language = detail.get("language") or repo_data.get("language", "")
        license_name = (detail.get("license") or {}).get("spdx_id", "")
        topics = detail.get("topics") or repo_data.get("topics", [])
        owner = repo_data.get("owner", {}).get("login", "")
        pushed_at = detail.get("pushed_at") or repo_data.get("pushed_at", "")
        archived = detail.get("archived", False)

        # Build content
        parts = [description] if description else []
        if language:
            parts.append(f"语言: {language}")
        if license_name:
            parts.append(f"许可证: {license_name}")
        if topics:
            parts.append(f"主题: {', '.join(topics[:8])}")
        if archived:
            parts.append("[已归档]")

        # Release info
        latest_release = ""
        release_count = len(releases)
        if releases:
            latest = releases[0]
            latest_release = latest.get("tag_name", "")
            release_date = latest.get("published_at", "")[:10]
            parts.append(f"最新发布: {latest_release} ({release_date})")

        # Activity
        last_push_date = pushed_at[:10] if pushed_at else ""
        if last_push_date:
            parts.append(f"最近推送: {last_push_date}")
        if contributor_count:
            parts.append(f"贡献者: {contributor_count}+")

        # Dimension
        dimension = "technical_capability"
        if contributor_count > 10 or release_count > 5:
            dimension = "developer_ecosystem"

        # Confidence based on data completeness
        completeness = sum([
            bool(description), bool(stars > 0), bool(language),
            bool(license_name), bool(releases), bool(contributor_count > 0),
        ])
        confidence = "high" if completeness >= 4 else "medium" if completeness >= 2 else "low"

        return EvidenceItem(
            source_type=SourceType.DEVELOPER,
            source_name=self.name,
            title=f"{full_name} — {description[:80] if description else 'No description'}",
            url=f"https://github.com/{full_name}",
            content=" | ".join(parts)[:2000],
            published_date=last_push_date,
            author=owner,
            metrics={
                "stars": stars,
                "forks": forks,
                "open_issues": open_issues,
                "contributors": contributor_count,
                "language": language,
                "license": license_name,
                "topics": topics,
                "latest_release": latest_release,
                "release_count": release_count,
                "archived": archived,
                "pushed_at": pushed_at,
            },
            dimension=dimension,
            confidence=confidence,
            sentiment="neutral",
        )

    # ── Fallback ──

    async def _fallback_tavily(self, query: str) -> list[EvidenceItem]:
        """Fallback: search GitHub pages via Tavily."""
        result = await tavily_search(
            query=f"site:github.com {query}",
            max_results=5,
            search_depth="basic",
            include_raw_content=False,
        )
        if not result.items:
            return []

        return [EvidenceItem(
            source_type=SourceType.DEVELOPER,
            source_name=f"{self.name} (via Tavily)",
            title=r.get("title", ""),
            url=r.get("url", ""),
            content=r.get("content", "")[:1500],
            published_date=r.get("published_date", ""),
            metrics={"score": r.get("score", 0.0), "fallback": True},
            dimension="technical_capability",
            confidence="low",
            sentiment="neutral",
        ) for r in result.items[:5]]


# ── Singleton ──

github_source = GitHubSource()
