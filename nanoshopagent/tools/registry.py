from __future__ import annotations

import ast
import os
from typing import Any, Dict

from nanoshopagent.tools.types import ToolDef


def _extract_registry_dict() -> Dict[str, Any]:
    """Load org_tools_registry from the original demo file via AST literal eval.

    This avoids executing the original script (which initializes OpenAI client etc.).
    We only parse and literal-eval the dict literal.
    """

    src_path = os.path.expanduser("~/backup/nano_shop_agent/dpskv32_mtc_demo0211.py")
    with open(src_path, "r", encoding="utf-8") as f:
        src = f.read()

    mod = ast.parse(src)
    reg_node = None
    for node in mod.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "org_tools_registry" for t in node.targets
        ):
            reg_node = node.value
            break

    if reg_node is None:
        raise RuntimeError("org_tools_registry not found in demo script")

    # org_tools_registry is a pure dict literal in this repo, safe for literal_eval
    return ast.literal_eval(reg_node)


def load_org_tools_registry() -> Dict[str, ToolDef]:
    """Load full tool registry (29 tools) from 0211 demo."""

    raw = _extract_registry_dict()
    out: Dict[str, ToolDef] = {}

    for name, tool_def in raw.items():
        fn = tool_def.get("function", {})
        out[name] = ToolDef(
            name=fn.get("name", name),
            description=fn.get("description", ""),
            parameters=fn.get("parameters", {"type": "object", "properties": {}}),
        )

    return out
