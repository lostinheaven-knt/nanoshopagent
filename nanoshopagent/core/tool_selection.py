from __future__ import annotations

from typing import List, Optional

from nanoshopagent.core.llm_client import LLMConfig, make_client, resolve_model
from nanoshopagent.tools.types import ToolDef
from nanoshopagent.utils.json_extract import extract_json_array


class ToolSelector:
    def __init__(self, tools: dict[str, ToolDef], cfg: Optional[LLMConfig] = None):
        self.tools = tools
        self.cfg = cfg or LLMConfig(temperature=0.0)
        self.client = make_client(self.cfg)

    def select(self, requirement: str, already_selected: Optional[List[str]] = None) -> List[str]:
        summary_text = "\n".join(
            f"- {t.name}: {t.description}" for t in self.tools.values()
        )
        already_info = (
            f"\n\n已加载的工具（不需要重复选择）：{', '.join(already_selected)}"
            if already_selected
            else ""
        )

        prompt = f"""你是一个电商 SaaS 系统的工具选择助手。
根据以下需求描述，从可用工具列表中选出需要用到的工具。
只返回工具名列表，用 JSON 数组格式，不要解释。
如果不确定某个工具是否需要，倾向于选上（宁多勿少）。

可用工具：
{summary_text}{already_info}

需求描述：{requirement}

请返回 JSON 数组，例如：["tool_a", "tool_b"]
"""

        resp = self.client.chat.completions.create(
            model=resolve_model(self.cfg),
            messages=[{"role": "user", "content": prompt}],
            temperature=self.cfg.temperature,
        )
        raw = resp.choices[0].message.content or ""
        names = extract_json_array(raw)
        return [n for n in names if isinstance(n, str) and n in self.tools]
