from __future__ import annotations

import copy
from typing import Any, Dict, Iterable


DEFAULT_SENSITIVE_KEYS = {
    "api_key",
    "api_keys",
    "auth_token",
    "access_token",
    "refresh_token",
    "token",
    "secret",
    "password",
    "passwd",
    "key",
}


def _is_sensitive_key(k: str) -> bool:
    kl = k.lower()
    if kl in DEFAULT_SENSITIVE_KEYS:
        return True
    # common patterns
    if "token" in kl:
        return True
    if "secret" in kl:
        return True
    if kl.endswith("_key") or kl.endswith("_keys"):
        return True
    return False


def redact(obj: Any, *, mask: str = "***", extra_keys: Iterable[str] = ()) -> Any:
    """Recursively redact sensitive fields in dict/list structures.

    Use this for user-visible logs/outputs. Don't use for internal model context unless desired.
    """

    extra = {k.lower() for k in extra_keys}

    def rec(x: Any) -> Any:
        if isinstance(x, dict):
            out: Dict[str, Any] = {}
            for k, v in x.items():
                if isinstance(k, str) and (_is_sensitive_key(k) or k.lower() in extra):
                    out[k] = mask
                else:
                    out[k] = rec(v)
            return out
        if isinstance(x, list):
            return [rec(i) for i in x]
        return x

    return rec(copy.deepcopy(obj))
