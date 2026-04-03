from __future__ import annotations

import re


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "item"


def role_code_from_name(value: str) -> str:
    return slugify(value).replace("-", "_")
