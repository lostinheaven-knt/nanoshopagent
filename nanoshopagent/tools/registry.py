from __future__ import annotations

import json
import os
from typing import Any, Dict

from nanoshopagent.tools.types import ToolDef


def _load_tools_json() -> Dict[str, Any]:
    """Load tool registry from a JSON file shipped with the repo.

    This avoids runtime dependency on any external demo script path.
    """

    here = os.path.abspath(os.path.dirname(__file__))
    data_path = os.path.join(here, "data", "tools_0211.json")

    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_org_tools_registry() -> Dict[str, ToolDef]:
    """Load full tool registry from tools/data/tools_0211.json."""

    raw = _load_tools_json()
    out: Dict[str, ToolDef] = {}

    for name, tool_def in raw.items():
        fn = tool_def.get("function", {})
        out[name] = ToolDef(
            name=fn.get("name", name),
            description=fn.get("description", ""),
            parameters=fn.get("parameters", {"type": "object", "properties": {}}),
        )

    return out
