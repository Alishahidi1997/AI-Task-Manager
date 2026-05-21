from __future__ import annotations

from app.evals.models import GoldenCase


def _normalize_tool(raw: dict, channel: str) -> str | None:
    if channel == "chat":
        return raw.get("tool_name") or raw.get("tool")
    return raw.get("tool") or raw.get("tool_name")


def _normalize_args(raw: dict) -> dict:
    args = raw.get("arguments")
    return args if isinstance(args, dict) else {}


def _value_matches(expected, actual) -> bool:
    if expected is None:
        return True
    if actual is None:
        return False
    exp = str(expected).strip().lower()
    act = str(actual).strip().lower()
    if exp == act:
        return True
    return exp in act or act in exp


def score_case(case: GoldenCase, planner_raw: dict) -> tuple[bool, bool]:
    predicted_tool = _normalize_tool(planner_raw, case.channel)
    args = _normalize_args(planner_raw)

    tool_ok = predicted_tool == case.expected_tool
    keys_ok = all(key in args for key in case.required_arg_keys)
    values_ok = all(_value_matches(expected, args.get(key)) for key, expected in case.expected_arg_values.items())
    param_ok = keys_ok and values_ok
    return tool_ok, param_ok


def accuracy(correct: int, total: int) -> float:
    if total == 0:
        return 0.0
    return correct / total
