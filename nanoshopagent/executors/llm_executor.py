from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict

from nanoshopagent.core.llm_client import LLMConfig, make_client, resolve_model
from nanoshopagent.utils.redact import redact


class ToolExecutor(ABC):
    @abstractmethod
    def execute(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


def _extract_json_obj(text: str) -> Dict[str, Any] | None:
    """Best-effort extract first JSON object from a string."""

    if not text:
        return None

    s = text.strip()
    # strip markdown fences
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)

    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return None

    try:
        return json.loads(m.group(0))
    except Exception:
        return None


class LLMToolExecutor(ToolExecutor):
    """Simulates tool execution via LLM (demo purpose).

    NOTE: We redact sensitive fields in the prompt to avoid leaking secrets.
    """

    def __init__(self, cfg: LLMConfig | None = None):
        self.cfg = cfg or LLMConfig(temperature=0.7)
        self.client = make_client(self.cfg)

    def execute(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        safe_args = redact(tool_args)

        prompt = f"""你是一个电商 SaaS 系统的后端服务模拟器。你需要根据被调用的工具名称和参数，
模拟出一个真实的系统返回结果。

要求：
1. 以产品运营的专业角度，返回合理的业务数据
2. 根据入参判断操作是否合理：
   - 如果参数合理，返回成功结果，包含具体的业务数据（如生成的ID、状态、详情等）
   - 如果参数有明显错误（如缺少必要信息、格式不对），返回错误信息
3. 返回 JSON 格式，包含 status（success/error）、message、以及 data 字段
4. 数据要看起来真实（如商品ID用 "prod_" 前缀 + 随机串，价格用合理数值等）

被调用的工具：{tool_name}
传入的参数（已脱敏）：{json.dumps(safe_args, ensure_ascii=False, indent=2)}

请直接返回 JSON 结果，不要其他说明文字。"""

        resp = self.client.chat.completions.create(
            model=resolve_model(self.cfg),
            messages=[{"role": "user", "content": prompt}],
            temperature=self.cfg.temperature,
        )
        raw = (resp.choices[0].message.content or "").strip()

        # 1) strict parse
        try:
            return json.loads(raw)
        except Exception:
            pass

        # 2) best-effort extract object from raw
        obj = _extract_json_obj(raw)
        if obj is not None:
            return obj

        # 3) fallback
        return {
            "status": "error",
            "message": "tool simulator returned non-JSON",
            "raw": raw[:2000],
        }
