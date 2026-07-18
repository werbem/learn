"""Planner Agent prompts — used by the LLM to generate ResearchPlan."""

from __future__ import annotations

from pydantic import BaseModel, Field


SYSTEM_PROMPT = """你是一名资深的互联网产品战略分析师。你的任务是根据用户输入的竞品分析需求，制定一份结构化的研究计划。

你需要分析：
1. 用户描述的问题本质是什么
2. 涉及哪些公司、产品和市场
3. 需要从哪些维度进行研究
4. 应该搜索哪些关键词
5. 研究的优先级

请输出结构化的 JSON 格式。"""


class LLMResearchPlanOutput(BaseModel):
    """Structured output that the LLM returns — maps to ResearchPlan."""
    analysis_goal: str = Field(description="分析目标的一句话总结，例如「分析飞猪DAU持续下降的根因」")
    research_dimensions: list[str] = Field(
        description="需要分析的研究维度列表（至少3个，不超过8个）。"
                    "例如：['用户画像与行为变化', '核心功能对比', '商业模式差异', '增长策略与市场']",
    )
    search_keywords: list[str] = Field(
        description="搜索关键词列表，用于跨源证据采集。"
                    "每个关键词应该具体、可搜索。例如：['飞猪 DAU 下降 原因', '携程 用户增长 策略']",
    )
    priority: int = Field(
        ge=1, le=5,
        description="研究优先级：1最低，5最高。"
                    "根据问题的紧迫性和业务影响判断。",
    )
    estimated_complexity: str = Field(
        description="研究复杂度评估：'simple'（单一维度问题）、'moderate'（多维度、需对比分析）、'complex'（多公司、多市场、多维度深度研究）",
    )


def build_user_prompt(
    our_company: str,
    competitor_company: str,
    product: str,
    objective: str,
    optional_context: str | None = None,
) -> str:
    """Build the user prompt for the LLM."""
    objective_labels = {
        "product_improvement": "产品改进 — 对标竞品发现自身短板，制定迭代方向",
        "go_to_market": "市场进入 — 了解竞品格局，制定差异化定位与策略",
        "investment_due_diligence": "投资尽调 — 评估标的公司的产品竞争壁垒与风险",
        "competitive_defense": "竞争防御 — 应对竞品进攻，评估威胁并制定防守策略",
        "positioning_switch": "定位转型 — 重新定义产品定位时，需要全面竞争格局分析",
        "partnership_evaluation": "合作评估 — 考察竞品是否可作为生态合作伙伴",
        "feature_benchmark": "功能对标 — 针对具体功能模块做深度对比",
    }

    obj_label = objective_labels.get(objective, objective)

    prompt = f"""## 分析需求

- **我方公司**: {our_company}
- **竞品公司**: {competitor_company}
- **分析产品**: {product}
- **分析目标**: {obj_label}
"""

    if optional_context:
        prompt += f"\n- **补充背景**: {optional_context}\n"

    prompt += """
请根据以上需求，制定一份研究计划。注意：
1. research_dimensions 必须至少3个，且有实质内容
2. search_keywords 应该具体可搜索，至少5个
3. priority 根据问题紧迫性判断
4. estimated_complexity 根据问题范围判断
"""

    return prompt
