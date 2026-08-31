"""Shared assertions for observable structured log records."""

import json
from typing import Any


def decode_json_records(captured: str) -> list[dict[str, Any]]:
    """Decode newline-delimited JSON log records into object mappings."""
    records: list[dict[str, Any]] = []
    for line in captured.strip().splitlines():
        decoded: object = json.loads(line)
        if not isinstance(decoded, dict):
            raise AssertionError("structured log record must be a JSON object")
        records.append({str(key): value for key, value in decoded.items()})
    return records
