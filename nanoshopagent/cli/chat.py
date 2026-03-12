from __future__ import annotations

"""CLI entrypoint.

Recommended:
    python -m nanoshopagent.cli.chat

Supports both single-line and multi-line input:
- Type your request and press Enter twice (blank line) to submit.
- Or end multi-line input with a line containing only `///`.
- Commands: /quit, /exit

If you insist on running as a script from this directory (python chat.py), we
patch sys.path so that `import nanoshopagent` resolves.
"""

import os
import sys

# Allow `python chat.py` when cwd is nanoshopagent/cli
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from nanoshopagent.core.agent import NanoShopAgent, select_tools_tool_def
from nanoshopagent.core.llm_client import LLMConfig
from nanoshopagent.core.tool_selection import ToolSelector
from nanoshopagent.executors.llm_executor import LLMToolExecutor
from nanoshopagent.tools.registry import load_org_tools_registry
from nanoshopagent.utils.env_load import load_env_file


def _print_step(evt: dict) -> None:
    """Print step events emitted by NanoShopAgent.

    Keeps the same user-facing four-part style, but streams as soon as each step finishes.
    """

    t = evt.get("type")
    if t in ("thinking", "final"):
        content = (evt.get("content") or "").strip()
        if content:
            print("\n" + content)
    elif t == "tool_call":
        name_zh = evt.get("tool_name_zh") or evt.get("tool_name") or ""
        if name_zh:
            print(f"\n【工具调用】{name_zh}")
    elif t == "tool_result":
        msg = (evt.get("message") or "").strip()
        if msg:
            print(f"【执行结果】{msg}")


def _read_user_message() -> str | None:
    """Read either a single-line or multi-line user message.

    - Returns None to indicate quit.
    """

    buf: list[str] = []
    while True:
        try:
            line = input("\n你> ")
        except (EOFError, KeyboardInterrupt):
            return None

        s = line.strip("\n")
        s_stripped = s.strip()

        # commands only when not in the middle of multi-line input
        if not buf and s_stripped.lower() in ("/quit", "/exit", "quit", "exit"):
            return None

        # multi-line submit marker
        if s_stripped == "///":
            break

        # blank line: if we have content, submit; else keep waiting
        if s_stripped == "":
            if buf:
                break
            continue

        buf.append(s)

        # Single-line convenience: if only one line so far and user didn't indicate multi-line,
        # let them submit by just pressing Enter on next blank line.

    msg = "\n".join(buf).strip()
    return msg if msg else ""


def main() -> None:
    # Load secrets from repo root if present
    here = os.path.abspath(os.path.dirname(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    load_env_file(os.path.join(repo_root, ".secrets.env"))

    tools = load_org_tools_registry()

    cfg = LLMConfig()
    selector = ToolSelector(tools=tools, cfg=cfg)
    executor = LLMToolExecutor()  # temperature=0.7 default

    all_tool_defs = {**tools, "select_tools_by_llm": select_tools_tool_def()}

    agent = NanoShopAgent(
        tool_defs=all_tool_defs,
        selector=selector,
        executor=executor,
        cfg=cfg,
        on_step=_print_step,
    )

    print("NanoShopAgent interactive. /quit to exit")
    print("(多行输入：空行提交；或输入 /// 提交)")

    while True:
        q = _read_user_message()
        if q is None:
            break
        if not q:
            continue
        # The agent will stream step outputs via on_step.
        # We still call run() to drive the loop, but we do not print the aggregated transcript again.
        agent.run(q)


if __name__ == "__main__":
    main()
