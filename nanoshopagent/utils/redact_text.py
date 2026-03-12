from __future__ import annotations

import os
import re
from typing import Iterable


# Generic secret-like patterns
_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"),  # DeepSeek/OpenAI style
    re.compile(r"\bsk_[A-Za-z0-9]{10,}\b"),
    re.compile(r"\bsk_(?:test|live)_[A-Za-z0-9]{3,}\b"),  # common test/live keys
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{10,}\b"),
    # avoid partial leaks like sk_test_*** (treat as sensitive too)
    re.compile(r"\bsk_(?:test|live)_[A-Za-z0-9*]{3,}\b"),
]


def sanitize_text(text: str, *, mask: str = "***", extra_literals: Iterable[str] = ()) -> str:
    if not text:
        return text

    out = text

    # Mask explicit secrets we know (from env) if present
    literals = [
        os.environ.get("DEEPSEEK_API_KEY", ""),
        os.environ.get("GITHUB_TOKEN", ""),
    ]
    literals.extend([s for s in extra_literals if s])

    for lit in sorted({s for s in literals if s}, key=len, reverse=True):
        out = out.replace(lit, mask)

    for pat in _PATTERNS:
        out = pat.sub(mask, out)

    return out
