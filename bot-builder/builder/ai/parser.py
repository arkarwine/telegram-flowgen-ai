from __future__ import annotations

import json
import re


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
        json.loads(candidate)
        return candidate
    start = stripped.find("{")
    if start < 0:
        raise json.JSONDecodeError("No JSON object found", stripped, 0)
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(stripped)):
        char = stripped[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = stripped[start : index + 1]
                    json.loads(candidate)
                    return candidate
    raise json.JSONDecodeError("Unclosed JSON object", stripped, start)


def parse_json_object(text: str) -> dict[str, object]:
    return json.loads(extract_json_object(text))

