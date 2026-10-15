"""Bounded syntax repair only. Never execute text, invent fields or log inputs."""

import json


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("Non-finite JSON value")


def remove_trailing_commas(text):
    result, quoted, escaped = [], False, False
    for index, char in enumerate(text):
        if char == '"' and not escaped:
            quoted = not quoted
        if char == "," and not quoted and text[index + 1 :].lstrip().startswith(("}", "]")):
            continue
        result.append(char)
        escaped = char == "\\" and not escaped if quoted else False
    return "".join(result)


def parse_object(text):
    if not isinstance(text, str) or len(text) > 20000:
        raise ValueError("Invalid JSON size")
    candidate = text.strip()
    if candidate.startswith("```json\n") and candidate.endswith("```"):
        candidate = candidate[8:-3].strip()
    elif candidate.startswith("```\n") and candidate.endswith("```"):
        candidate = candidate[4:-3].strip()
    candidate = remove_trailing_commas(candidate)
    value = json.loads(candidate, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value, candidate != text.strip()
