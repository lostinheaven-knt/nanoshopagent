from __future__ import annotations

import json
import re
from typing import Any, Dict, List


def extract_json_array(text: str) -> List[Any]:
    text = text.strip()

    # strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        raise ValueError(f"No JSON array found in: {text[:200]}")
    return json.loads(m.group(0))


def extract_json_obj(text: str) -> Dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError(f"No JSON object found in: {text[:200]}")
    return json.loads(m.group(0))
