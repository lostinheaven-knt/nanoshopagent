from __future__ import annotations

import os


def load_env_file(path: str) -> None:
    """Minimal .env loader (no external dependency).

    - Supports KEY=VALUE
    - Supports quotes around VALUE
    - Ignores comments and blank lines
    - Does not override existing env vars
    """

    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if not k:
                continue
            os.environ.setdefault(k, v)
