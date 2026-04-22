from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


def stable_payload_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def stable_payload_hash(payload: Mapping[str, object]) -> str:
    return f"sha256:{hashlib.sha256(stable_payload_json(payload).encode('utf-8')).hexdigest()}"
