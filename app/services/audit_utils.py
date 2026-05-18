"""Shared audit helpers for chat routes and queue workers."""


def audit_validation_result(execution_status: str) -> str:
    if execution_status == "executed":
        return "passed"
    if execution_status == "clarification_required":
        return "clarification"
    return "failed"
