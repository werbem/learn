"""Integration test for LLM Client with OpenAI.

Run with:
    export OPENAI_API_KEY=sk-xxx
    python -m pytest tests/integration/test_llm_client.py -v
"""

from __future__ import annotations

import os
import pytest
from pydantic import BaseModel, Field

from app.infrastructure.llm.client import LLMClient, _parse_response
from app.application.dto.agent_dto import ResearchPlan, ResearchTask


# ── Test: Structured Output Parsing ──

class SimplePlan(BaseModel):
    """A minimal plan for testing structured output."""
    objective: str = Field(description="分析目标")
    hypothesis: str = Field(description="核心假设")
    dimensions: list[str] = Field(description="分析维度列表")
    priority_tasks: int = Field(default=3, ge=1, le=5, description="优先任务数")


class TestParseResponse:
    """Test the JSON → Pydantic parsing logic."""

    def test_parse_valid_json(self):
        content = '{"objective": "分析DAU下降", "hypothesis": "竞品分流", "dimensions": ["用户", "功能"], "priority_tasks": 3}'
        _, parsed = _parse_response(content, SimplePlan)
        assert parsed is not None
        assert parsed.objective == "分析DAU下降"
        assert parsed.hypothesis == "竞品分流"

    def test_parse_with_code_fence(self):
        content = '```json\n{"objective": "test", "hypothesis": "h", "dimensions": ["a"], "priority_tasks": 3}\n```'
        _, parsed = _parse_response(content, SimplePlan)
        assert parsed is not None

    def test_parse_invalid_json(self):
        content = "Some free text without JSON"
        _, parsed = _parse_response(content, SimplePlan)
        assert parsed is None  # graceful degradation

    def test_parse_partial_json(self):
        content = 'Here is the result: {"objective": "test", "hypothesis": "h", "dimensions": ["a"], "priority_tasks": 3} and more text'
        _, parsed = _parse_response(content, SimplePlan)
        assert parsed is not None

    def test_no_response_model(self):
        content = "Some text"
        text, parsed = _parse_response(content, None)
        assert text == "Some text"
        assert parsed is None


# ── Integration Test (requires OPENAI_API_KEY) ──

@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — skipping integration test",
)
class TestLLMClientIntegration:
    """Real LLM integration tests. Requires OPENAI_API_KEY environment variable."""

    @pytest.fixture
    def client(self):
        return LLMClient()

    @pytest.mark.asyncio
    async def test_generate_structured_output(self, client):
        """Test: LLM generates structured output matching a Pydantic schema."""
        result = await client.generate(
            system_prompt="你是一名资深互联网产品分析师。请用JSON格式回答。",
            user_prompt=(
                "分析飞猪（阿里巴巴旗下旅游平台）DAU持续下降的原因。\n"
                "请输出JSON，包含：\n"
                "- objective: 分析目标\n"
                "- hypothesis: 你认为最可能的核心假设\n"
                "- dimensions: 需要分析的维度列表（至少3个）\n"
                "- priority_tasks: 优先任务数（1-5之间）"
            ),
            response_model=SimplePlan,
            temperature=0.3,
        )

        print(f"\n--- LLM Response ---")
        print(f"Model: {result.model}")
        print(f"Content: {result.content[:200]}...")
        print(f"Prompt tokens: {result.prompt_tokens}")
        print(f"Completion tokens: {result.completion_tokens}")
        print(f"Duration: {result.duration_ms}ms")

        assert result.parsed is not None, f"Parsed output should not be None. Raw: {result.content[:200]}"
        assert len(result.parsed.dimensions) >= 3, f"Should have 3+ dimensions: {result.parsed.dimensions}"
        assert 1 <= result.parsed.priority_tasks <= 5
        assert result.prompt_tokens > 0
        assert result.completion_tokens > 0
        assert "openai/" in result.model

    @pytest.mark.asyncio
    async def test_research_plan_generation(self, client):
        """Test: LLM generates a ResearchPlan-like output."""
        result = await client.generate(
            system_prompt=(
                "你是一名互联网产品竞品分析专家。"
                "请输出结构化的JSON，包含研究计划。"
            ),
            user_prompt=(
                "我方：飞猪（阿里巴巴旗下在线旅游平台）\n"
                "竞品：携程、美团酒店\n"
                "产品：飞猪旅行App\n"
                "分析目标：分析DAU持续下降的原因\n\n"
                "请生成初步研究假设，列出需要分析的维度。"
            ),
            response_model=SimplePlan,
            temperature=0.3,
        )

        print(f"\n--- Research Plan Generation ---")
        print(f"Model: {result.model}")
        if result.parsed:
            print(f"Objective: {result.parsed.objective}")
            print(f"Hypothesis: {result.parsed.hypothesis}")
            print(f"Dimensions: {result.parsed.dimensions}")
            print(f"Priority Tasks: {result.parsed.priority_tasks}")

        assert result.parsed is not None
        assert len(result.parsed.dimensions) >= 2

    @pytest.mark.asyncio
    async def test_timeout_handling(self, client):
        """Test: timeout is handled gracefully."""
        import asyncio
        try:
            result = await asyncio.wait_for(
                client.generate(
                    system_prompt="Test",
                    user_prompt="This is a test",
                    response_model=SimplePlan,
                    temperature=0.5,
                ),
                timeout=5,
            )
            # Should succeed or fail gracefully either way
            assert result is not None
        except asyncio.TimeoutError:
            pytest.fail("LLMClient.generate() should not hang indefinitely")


# ── Direct test runner (for manual execution) ──

if __name__ == "__main__":
    import asyncio

    async def main():
        client = LLMClient()

        print("=" * 50)
        print("LLM Client Integration Test")
        print("=" * 50)
        print(f"Provider: {client.provider}")
        print(f"Model: {client.model}")
        print(f"API Key set: {bool(client.api_key)}")
        print()

        if not client.api_key:
            print("⚠️  OPENAI_API_KEY not set — will use MOCK fallback")
            print()

        result = await client.generate(
            system_prompt="你是一名资深分析师。用JSON回答。",
            user_prompt=(
                "分析飞猪DAU下降原因。输出JSON: "
                '{"objective": "分析DAU下降原因", "hypothesis": "竞品分流", '
                '"dimensions": ["用户留存", "竞品对比", "产品功能"], "priority_tasks": 3}'
            ),
            response_model=SimplePlan,
        )

        print(f"Model: {result.model}")
        print(f"Duration: {result.duration_ms}ms")
        print(f"Tokens: {result.prompt_tokens} prompt + {result.completion_tokens} completion")

        if result.parsed:
            print(f"\n✅ Parsed Output:")
            print(f"   Objective: {result.parsed.objective}")
            print(f"   Hypothesis: {result.parsed.hypothesis}")
            print(f"   Dimensions: {', '.join(result.parsed.dimensions)}")
            print(f"   Priority Tasks: {result.parsed.priority_tasks}")
        else:
            print(f"\n⚠️  Could not parse structured output")
            print(f"   Raw content preview: {result.content[:200]}")

    asyncio.run(main())
