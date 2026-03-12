from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from nanoshopagent.tools.types import ToolDef


@dataclass
class RunConfig:
    max_steps: int = 12
    # Rough token budget placeholder; real budgeting can be added later.
    max_tool_calls: int = 24


@dataclass
class AgentState:
    goal: str
    loaded_tools: List[str]
    step: int = 0
    tool_calls: int = 0
    summary: str = ""  # rolling compressed context


def build_system_prompt() -> str:
    return """你是一位经验丰富的电商经营达人和店铺运营专家。你精通：
- 选品策略：能根据市场趋势和目标受众推荐合适的产品组合
- 店铺运营：熟悉店铺搭建、装修、域名配置、支付物流等全流程
- 营销推广：擅长制定折扣活动、社交媒体营销、EDM邮件营销等策略
- 数据分析：能解读运营数据报告，给出优化建议
- 客户管理：懂得客户分群、VIP体系、积分运营等用户增长手段

你必须在需要外部信息/执行操作时调用工具。工具返回结果可信。
如果用户要求模糊：先给出默认方案再向用户确认。
输出要专业、可落地。"""


def to_openai_tools(tool_defs: Dict[str, ToolDef], names: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for n in names:
        t = tool_defs.get(n)
        if t:
            out.append(t.to_openai())
    return out
