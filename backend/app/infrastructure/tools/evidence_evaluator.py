"""Evidence Quality Evaluator — scores evidence across 4 dimensions.

Scoring strategy (hybrid rule-based + LLM):
  - Authority   → rule-based (source_type priority)
  - Freshness   → rule-based (date recency check)
  - Relevance   → LLM-powered  (semantic match with research question)
  - Reliability → LLM-powered  (content verification check)

Why hybrid: Authority/Freshness are deterministic lookups (fast, consistent).
Relevance/Reliability need semantic understanding (LLM).

Architecture:
  EvidenceItem + Research Question
      ↓
  EvidenceEvaluator.evaluate()
      ↓
  EvidenceQualityScore  (appended to EvidenceItem)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from app.infrastructure.tools.research_source import SourceType


# ═══════════════════════════════════════════════════
#  Quality Score Model
# ═══════════════════════════════════════════════════

@dataclass
class EvidenceQualityScore:
    """Per-evidence quality evaluation result."""
    evidence_id: str = ""
    authority_score: float = 0.0    # 0-1, source credibility
    freshness_score: float = 0.0    # 0-1, recency relevance
    relevance_score: float = 0.0    # 0-1, topic match
    reliability_score: float = 0.0  # 0-1, data verifiability
    overall_confidence: float = 0.0  # weighted composite
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "authority_score": round(self.authority_score, 2),
            "freshness_score": round(self.freshness_score, 2),
            "relevance_score": round(self.relevance_score, 2),
            "reliability_score": round(self.reliability_score, 2),
            "overall_confidence": round(self.overall_confidence, 2),
            "reason": self.reason,
        }


# ═══════════════════════════════════════════════════
#  Authority Scoring (rule-based)
# ═══════════════════════════════════════════════════

_AUTHORITY_MAP: dict[str, float] = {
    SourceType.OFFICIAL: 1.0,      # 官網最高
    SourceType.NEWS: 0.85,         # 正规新闻
    SourceType.APP_STORE: 0.75,    # App Store 评分/评论
    SourceType.DEVELOPER: 0.70,    # GitHub
    SourceType.WEB: 0.60,          # 普通网页/Tavily
    SourceType.SOCIAL: 0.40,       # 社区/用户讨论
}


def _score_authority(source_type: str, url: str = "") -> float:
    """Score source authority based on source_type and URL patterns.

    Tiers: Official (1.0) > News (0.85) > App Store (0.75) >
           Developer (0.70) > Web (0.60) > Social (0.40) > Unknown (0.30)
    """
    base = _AUTHORITY_MAP.get(source_type, 0.30)

    # Boost for known high-authority domains
    authoritative_domains = [
        "gov.cn", ".gov", "stats.gov", "cnnic",
        "apple.com/app", "play.google.com",
        "techcrunch.com", "36kr.com",
        "crunchbase.com",
    ]
    if any(d in url for d in authoritative_domains):
        base = min(1.0, base + 0.10)

    # Penalty for blog/no-name sources
    low_authority_patterns = ["blogspot", "wordpress", "medium.com/@", "zhuanlan.zhihu.com"]
    if any(p in url for p in low_authority_patterns):
        base = max(0.20, base - 0.15)

    return round(base, 2)


# ═══════════════════════════════════════════════════
#  Freshness Scoring (rule-based)
# ═══════════════════════════════════════════════════

def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats to datetime."""
    if not date_str:
        return None
    formats = [
        "%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S",
        "%Y年%m月%d日", "%b %d, %Y", "%d %b %Y",
        "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    # Try ISO 8601 with timezone
    try:
        return datetime.fromisoformat(date_str.strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    return None


def _score_freshness(date_str: str) -> float:
    """Score freshness based on publication date.

    < 1 month:  1.0
    < 3 months: 0.85
    < 6 months: 0.70
    < 1 year:   0.55
    < 2 years:  0.35
    > 2 years:  0.20
    unknown:    0.50 (neutral, don't penalize unknown dates)
    """
    dt = _parse_date(date_str)
    if dt is None:
        return 0.50  # neutral for unknown dates

    now = datetime.now()
    age = now - dt.replace(tzinfo=None)

    if age < timedelta(days=30):
        return 1.0
    elif age < timedelta(days=90):
        return 0.85
    elif age < timedelta(days=180):
        return 0.70
    elif age < timedelta(days=365):
        return 0.55
    elif age < timedelta(days=730):
        return 0.35
    else:
        return 0.20


# ═══════════════════════════════════════════════════
#  Relevance & Reliability (LLM-powered)
# ═══════════════════════════════════════════════════

_EVAL_SYSTEM_PROMPT = """你是证据质量评估专家。对给定的证据评分（0-1）。

## 相关性 (relevance) 评分规则
- 1.0: 证据直接回答研究问题
- 0.7: 证据与研究问题相关但非核心
- 0.4: 证据仅在领域中，间接相关
- 0.1: 证据几乎无关
- 检查: 证据内容是否包含研究问题中的关键实体和概念？

## 可靠性 (reliability) 评分规则
- 1.0: 有明确数据来源、引用、具体数字
- 0.7: 内容合理但缺少直接引用
- 0.4: 包含主观推测、二手转载
- 0.1: 无来源数据、纯观点、猜测
- 检查: 是否有具体数字？是否标注数据来源？是否有"据称"、"可能"等不确定词？

## 输出格式 (JSON)
{
  "relevance_score": 0.0,
  "relevance_reason": "一句话说明",
  "reliability_score": 0.0,
  "reliability_reason": "一句话说明"
}"""


_EVAL_USER_PROMPT_TEMPLATE = """## 研究问题
{objective}

## 证据信息
- 标题: {title}
- 来源类型: {source_type}
- URL: {url}
- 日期: {date}
- 内容摘要: {content}

请评估这条证据的相关性和可靠性。只返回 JSON。"""


# ═══════════════════════════════════════════════════
#  Evaluator
# ═══════════════════════════════════════════════════

class EvidenceEvaluator:
    """Evaluates evidence quality across 4 dimensions.

    Uses:
      - Rule-based heuristics for Authority and Freshness
      - LLM-powered analysis for Relevance and Reliability

    Provides both individual dimension scores and a weighted overall.
    """

    # Weights for overall composite score
    _WEIGHTS = {
        "authority": 0.25,
        "freshness": 0.15,
        "relevance": 0.35,
        "reliability": 0.25,
    }

    def __init__(self):
        self._llm_available = None  # lazy check

    async def _check_llm_available(self) -> bool:
        """Lazy check if LLM is available for scoring."""
        if self._llm_available is None:
            try:
                from app.infrastructure.llm.client import llm_client
                self._llm_available = llm_client._use_openai()
            except Exception:
                self._llm_available = False
        return self._llm_available

    async def evaluate(
        self,
        evidence_id: str,
        title: str,
        content: str,
        source_type: str,
        url: str = "",
        date: str = "",
        objective: str = "",
    ) -> EvidenceQualityScore:
        """Evaluate a single evidence item.

        Args:
            evidence_id: Unique evidence identifier
            title: Evidence title
            content: Evidence content (first 500 chars used)
            source_type: Source type (web, app_store, official, etc.)
            url: Source URL
            date: Publication date string
            objective: The research question being answered

        Returns:
            EvidenceQualityScore with all dimensions scored
        """
        # ── Rule-based: Authority ──
        authority = _score_authority(source_type, url)

        # ── Rule-based: Freshness ──
        freshness = _score_freshness(date)

        # ── LLM-powered: Relevance + Reliability ──
        relevance = 0.50
        reliability = 0.50
        reasons: list[str] = [
            f"authority={authority:.2f}(source_type={source_type})",
            f"freshness={freshness:.2f}(date={date or 'unknown'})",
        ]

        if await self._check_llm_available():
            try:
                from app.infrastructure.llm.client import llm_client

                user_prompt = _EVAL_USER_PROMPT_TEMPLATE.format(
                    objective=objective,
                    title=title,
                    source_type=source_type,
                    url=url,
                    date=date or "未知",
                    content=content[:500] if content else "(无内容)",
                )

                response = await llm_client.generate(
                    system_prompt=_EVAL_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.1,
                )

                if response.content:
                    # Parse JSON from response
                    json_match = re.search(r'\{[^}]+\}', response.content)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        relevance = float(parsed.get("relevance_score", 0.50))
                        reliability = float(parsed.get("reliability_score", 0.50))
                        reasons.append(
                            f"relevance: {parsed.get('relevance_reason', 'N/A')}"
                        )
                        reasons.append(
                            f"reliability: {parsed.get('reliability_reason', 'N/A')}"
                        )
                    else:
                        reasons.append("relevance=0.50 (LLM parse failed)")
                        reasons.append("reliability=0.50 (LLM parse failed)")
                else:
                    reasons.append("relevance=0.50 (no LLM content)")
                    reasons.append("reliability=0.50 (no LLM content)")

            except Exception as exc:
                reasons.append(f"relevance=0.50 (LLM error: {exc})")
                reasons.append(f"reliability=0.50 (LLM error: {exc})")
        else:
            reasons.append("relevance=0.50 (no LLM available, using defaults)")
            reasons.append("reliability=0.50 (no LLM available, using defaults)")

        # ── Weighted overall ──
        overall = round(
            authority * self._WEIGHTS["authority"]
            + freshness * self._WEIGHTS["freshness"]
            + relevance * self._WEIGHTS["relevance"]
            + reliability * self._WEIGHTS["reliability"],
            2,
        )

        return EvidenceQualityScore(
            evidence_id=evidence_id,
            authority_score=authority,
            freshness_score=freshness,
            relevance_score=relevance,
            reliability_score=reliability,
            overall_confidence=overall,
            reason=" | ".join(reasons),
        )

    async def evaluate_batch(
        self,
        items: list[dict],
        objective: str = "",
        max_concurrent: int = 10,
    ) -> list[EvidenceQualityScore]:
        """Evaluate multiple evidence items in parallel.

        Args:
            items: List of dicts with keys: id, title, content, source_type, url, date
            objective: Research question
            max_concurrent: Max parallel LLM calls

        Returns:
            List of EvidenceQualityScore, one per item
        """
        import asyncio
        sem = asyncio.Semaphore(max_concurrent)

        async def _eval_one(item: dict) -> EvidenceQualityScore:
            async with sem:
                return await self.evaluate(
                    evidence_id=item.get("id", ""),
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    source_type=item.get("source_type", ""),
                    url=item.get("url", ""),
                    date=item.get("date", ""),
                    objective=objective,
                )

        if not items:
            return []

        coros = [_eval_one(item) for item in items]
        return list(await asyncio.gather(*coros))


# ── Singleton ──

evidence_evaluator = EvidenceEvaluator()
