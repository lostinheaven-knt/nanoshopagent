from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ToolDef:
    """OpenAI tool definition wrapper."""

    name: str
    description: str
    parameters: Dict[str, Any]

    def to_openai(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCall:
    tool_call_id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    content: str  # must be string for OpenAI tool message
    is_error: bool = False

    @staticmethod
    def ok(tool_call_id: str, data: Any) -> "ToolResult":
        return ToolResult(tool_call_id=tool_call_id, content=json.dumps(data, ensure_ascii=False))

    @staticmethod
    def err(tool_call_id: str, message: str, data: Optional[Any] = None) -> "ToolResult":
        payload = {"status": "error", "message": message}
        if data is not None:
            payload["data"] = data
        return ToolResult(tool_call_id=tool_call_id, content=json.dumps(payload, ensure_ascii=False), is_error=True)


def tool_summaries(tools: Dict[str, ToolDef]) -> List[Dict[str, str]]:
    return [{"name": t.name, "description": t.description} for t in tools.values()]
