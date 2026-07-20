"""Domain constants and enumerations."""

from __future__ import annotations

import os

# ── Demo mode default ──
# Set DEMO_MODE=true (env) to run with pre-built demo data when no API keys configured.
# Default: true when OPENAI_API_KEY is not set (safe for public showcase)
DEMO_MODE_DEFAULT: bool = (
    os.getenv('DEMO_MODE', 'true' if not os.getenv('OPENAI_API_KEY') else 'false').lower() == 'true'
)

from enum import Enum


# ── Phase Enum ──

class Phase(str, Enum):
    INITIALIZED = "initialized"
    VALIDATING = "validating"
    VALIDATED = "validated"
    VALIDATION_FAILED = "validation_failed"
    PLANNING = "planning"
    PLANNED = "planned"
    RESEARCHING = "researching"
    RESEARCHED = "researched"
    COMPARING = "comparing"
    COMPARED = "compared"
    INSIGHTING = "insighting"
    INSIGHTED = "insighted"
    STRATEGIZING = "strategizing"
    STRATEGIZED = "strategized"
    REPORTING = "reporting"
    REPORTED = "reported"
    REVIEWING = "reviewing"
    REVIEWED = "reviewed"
    REVIEW_FAILED = "review_failed"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── Analysis Objective ──

class AnalysisObjective(str, Enum):
    PRODUCT_IMPROVEMENT = "product_improvement"
    GO_TO_MARKET = "go_to_market"
    INVESTMENT_DUE_DILIGENCE = "investment_due_diligence"
    COMPETITIVE_DEFENSE = "competitive_defense"
    POSITIONING_SWITCH = "positioning_switch"
    PARTNERSHIP_EVALUATION = "partnership_evaluation"
    FEATURE_BENCHMARK = "feature_benchmark"


# ── Analysis Dimension ──

class AnalysisDimension(str, Enum):
    POSITIONING = "positioning"
    USERS = "users"
    FEATURES = "features"
    UX = "ux"
    BUSINESS = "business"
    TECHNOLOGY = "technology"
    GROWTH = "growth"
    COMPETITIVE_LANDSCAPE = "competitive_landscape"
    RISKS = "risks"
    STRATEGY = "strategy"


# ── Source Type ──

class SourceType(str, Enum):
    WEB = "web"
    APP_STORE = "app_store"
    SOCIAL = "social"
    NEWS = "news"
    GITHUB = "github"
    AI_SEARCH = "ai_search"


# ── Evidence Confidence ──

class Confidence(str, Enum):
    VERIFIED = "verified"
    LIKELY = "likely"
    ESTIMATED = "estimated"
    SPECULATIVE = "speculative"


# ── Error Category ──

class ErrorCategory(str, Enum):
    INPUT_ERROR = "INPUT_ERROR"
    LLM_ERROR = "LLM_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    NO_DATA = "NO_DATA"
    PARSE_ERROR = "PARSE_ERROR"
    STATE_CORRUPTION = "STATE_CORRUPTION"
    CANCELLED = "CANCELLED"


# ── Stream Event Type ──

class StreamEventType(str, Enum):
    PHASE_ENTERED = "phase.entered"
    PHASE_COMPLETED = "phase.completed"
    PHASE_FAILED = "phase.failed"
    PROGRESS_UPDATE = "progress.update"
    AGENT_HEARTBEAT = "agent.heartbeat"
    INTERMEDIATE_RESULT = "intermediate.result"
    LLM_TOKEN = "llm.token"
    HUMAN_CHECKPOINT_REQUESTED = "human.checkpoint.required"
    HUMAN_DECISION_RECEIVED = "human.decision.received"
    ERROR = "error"
    WARNING = "warning"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Output Format ──

class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    DOCX = "docx"
