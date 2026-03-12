from __future__ import annotations

import os

from nanoshopagent.core.agent import NanoShopAgent, select_tools_tool_def
from nanoshopagent.core.llm_client import LLMConfig
from nanoshopagent.core.tool_selection import ToolSelector
from nanoshopagent.executors.llm_executor import LLMToolExecutor
from nanoshopagent.tools.registry import load_org_tools_registry
from nanoshopagent.utils.env_load import load_env_file


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
    )

    print("NanoShopAgent interactive. /quit to exit")
    while True:
        try:
            q = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q.lower() in ("/quit", "/exit"):
            break
        out = agent.run(q)
        print("\n助理>", out)


if __name__ == "__main__":
    main()
