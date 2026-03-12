from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from nanoshopagent.core.llm_client import LLMConfig, make_client, resolve_model
from nanoshopagent.core.state import AgentState, RunConfig, build_system_prompt, to_openai_tools
from nanoshopagent.core.tool_selection import ToolSelector
from nanoshopagent.executors.llm_executor import ToolExecutor
from nanoshopagent.tools.types import ToolDef, ToolResult
from nanoshopagent.utils.redact import redact
from nanoshopagent.utils.redact_text import sanitize_text
from nanoshopagent.utils.sanitize_reasoning import sanitize_reasoning, tool_display_name


def _prune_messages_keep_last_user_turns(
    messages: List[Dict[str, Any]], *, keep_last_user_turns: int
) -> List[Dict[str, Any]]:
    """Keep system messages, and keep last N user turns with their following assistant/tool messages.

    This mimics the 0211-style pruning: keep multiple turns, but do not keep sub-turn reasoning as history
    (reasoning_content is already dropped by _assistant_msg_with_tool_calls_and_thinking).
    """

    if keep_last_user_turns <= 0:
        # keep only system
        return [m for m in messages if m.get("role") == "system"]

    sys_msgs = [m for m in messages if m.get("role") == "system"]

    # find indices of user messages
    user_idxs = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if not user_idxs:
        return sys_msgs

    keep_user_idxs = user_idxs[-keep_last_user_turns:]
    start = keep_user_idxs[0]
    kept = messages[start:]

    # ensure system prompts stay first
    return sys_msgs + [m for m in kept if m.get("role") != "system"]


SELECT_TOOL_NAME = "select_tools_by_llm"


def select_tools_tool_def() -> ToolDef:
    return ToolDef(
        name=SELECT_TOOL_NAME,
        description=(
            "动态加载额外工具。当你发现当前可用工具不足以完成任务时，调用此工具描述你需要什么能力，系统会为你加载相应的工具。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "select_requirement": {
                    "type": "string",
                    "description": "描述你需要的工具能力",
                }
            },
            "required": ["select_requirement"],
        },
    )


def _assistant_msg_with_tool_calls_and_thinking(msg: Any) -> Dict[str, Any]:
    """Serialize assistant message back into `messages`.

    IMPORTANT: We intentionally do NOT persist `reasoning_content` into history.
    DeepSeek requires reasoning_content to be present when a message has tool_calls,
    but the next request only needs it for those specific assistant messages.

    Keeping reasoning for every sub-turn bloats context and hurts caching/perf.
    We still show reasoning to the user, but we don't keep it in `messages`.
    """

    out: Dict[str, Any] = {
        "role": "assistant",
        "content": msg.content or "",
        "reasoning_content": "",
    }

    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        # Only attach reasoning_content if provider produced it; required by DeepSeek protocol.
        reasoning = getattr(msg, "reasoning_content", "")
        out["reasoning_content"] = reasoning or ""

        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tool_calls
        ]

    return out


class NanoShopAgent:
    def __init__(
        self,
        tool_defs: Dict[str, ToolDef],
        selector: ToolSelector,
        executor: ToolExecutor,
        cfg: Optional[LLMConfig] = None,
        run_cfg: Optional[RunConfig] = None,
        show_thinking_to_user: bool = True,
        on_step: Optional[callable] = None,
    ):
        self.tool_defs = tool_defs
        self.selector = selector
        self.executor = executor
        self.cfg = cfg or LLMConfig(temperature=0.0)
        self.client = make_client(self.cfg)
        self.run_cfg = run_cfg or RunConfig()
        self.show_thinking_to_user = show_thinking_to_user
        self.on_step = on_step

    def _emit(self, evt: Dict[str, Any]) -> None:
        if self.on_step is None:
            return
        try:
            self.on_step(evt)
        except Exception:
            # Never let UI callbacks break the agent loop
            return

    def run(self, user_query: str) -> str:
        selected = self.selector.select(user_query)
        loaded = list(dict.fromkeys(selected + [SELECT_TOOL_NAME]))
        state = AgentState(goal=user_query, loaded_tools=loaded)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt()},
            {
                "role": "system",
                "content": (
                    "你会进行多步推理（plan/act/observe loop）。每一步要么调用工具，要么在信息足够时给出最终答案。"
                    " 如果需要新工具，调用 select_tools_by_llm。"
                    " 注意：任何输出（包括复述参数/结果）都必须对敏感字段脱敏。"
                ),
            },
            {"role": "user", "content": user_query},
        ]

        # user-facing transcript
        user_chunks: List[str] = []

        while True:
            tools = to_openai_tools(self.tool_defs, state.loaded_tools)

            resp = self.client.chat.completions.create(
                model=resolve_model(self.cfg),
                messages=messages,
                tools=tools,
                temperature=self.cfg.temperature,
                extra_body={"thinking": {"type": "enabled"}},
            )
            msg = resp.choices[0].message

            # Capture and show reasoning (sanitized) without extra LLM calls
            if self.show_thinking_to_user:
                rc = getattr(msg, "reasoning_content", "")
                chunk = "【思考】\n" + sanitize_reasoning(rc or "")
                user_chunks.append(chunk)
                self._emit({"type": "thinking", "step": state.step, "content": chunk})

            messages.append(_assistant_msg_with_tool_calls_and_thinking(msg))

            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                final = sanitize_text(msg.content or "")
                chunk = "【回复】\n" + final
                user_chunks.append(chunk)
                self._emit({"type": "final", "step": state.step, "content": chunk})
                return "\n\n".join([c for c in user_chunks if c.strip()])

            # For each tool call: show tool name only, execute, then show tool message
            for tc in tool_calls:
                state.tool_calls += 1
                name = tc.function.name
                user_chunks.append(f"【工具调用】调用了：{tool_display_name(name)}（已脱敏）")
                self._emit({"type": "tool_call", "step": state.step, "tool_name": name, "tool_name_zh": tool_display_name(name)})

                if state.tool_calls > self.run_cfg.max_tool_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": "工具调用次数已达上限，我将基于已有信息给出结论（已脱敏）。",
                            "reasoning_content": "",
                        }
                    )
                    messages.append({"role": "user", "content": "请基于已有信息给出最终可执行方案。"})
                    break

                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}

                if name == SELECT_TOOL_NAME:
                    req = args.get("select_requirement", "")
                    new = self.selector.select(req, already_selected=state.loaded_tools)
                    added = [n for n in new if n not in state.loaded_tools]
                    state.loaded_tools.extend(added)
                    tool_payload = {
                        "status": "success",
                        "message": f"已加载新工具: {', '.join(added)}" if added else "无需加载新工具",
                    }
                    result = ToolResult.ok(tc.id, tool_payload)
                    user_chunks.append("【执行结果】" + sanitize_text(tool_payload.get("message", "")))
                    self._emit({"type": "tool_result", "step": state.step, "tool_name": name, "message": sanitize_text(tool_payload.get("message", ""))})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result.content,
                        }
                    )
                else:
                    data = self.executor.execute(name, args)
                    safe_data = redact(data)
                    # user only sees message
                    msg_text = ""
                    if isinstance(safe_data, dict):
                        msg_text = safe_data.get("message", "") or ""
                    user_chunks.append("【执行结果】" + sanitize_text(msg_text))
                    self._emit({"type": "tool_result", "step": state.step, "tool_name": name, "message": sanitize_text(msg_text)})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(safe_data, ensure_ascii=False),
                        }
                    )

            state.step += 1
            # prune history to control context growth (keep multiple turns, drop sub-turn reasoning)
            messages = _prune_messages_keep_last_user_turns(
                messages, keep_last_user_turns=self.run_cfg.keep_last_user_turns
            )
            if state.step >= self.run_cfg.max_steps:
                messages.append(
                    {
                        "role": "user",
                        "content": "请在不再调用工具的前提下，输出最终方案（注意脱敏）。",
                    }
                )
