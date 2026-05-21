from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.evals.models import GoldenCase
from app.evals.scoring import accuracy, score_case


@dataclass
class EvalResult:
    total: int
    tool_correct: int
    param_correct: int
    tool_accuracy: float
    param_accuracy: float
    failures: list[dict] = field(default_factory=list)

    def assert_thresholds(self, *, min_tool: float, min_param: float) -> None:
        if self.tool_accuracy < min_tool:
            raise AssertionError(
                f"tool accuracy {self.tool_accuracy:.3f} below threshold {min_tool:.3f}; "
                f"failures={len(self.failures)}"
            )
        if self.param_accuracy < min_param:
            raise AssertionError(
                f"parameter accuracy {self.param_accuracy:.3f} below threshold {min_param:.3f}; "
                f"failures={len(self.failures)}"
            )


def run_eval_suite(
    planner_fn: Callable[[GoldenCase], dict],
    cases: list[GoldenCase],
) -> EvalResult:
    tool_correct = 0
    param_correct = 0
    failures: list[dict] = []

    for case in cases:
        raw = planner_fn(case)
        tool_ok, param_ok = score_case(case, raw)
        if tool_ok:
            tool_correct += 1
        if param_ok:
            param_correct += 1
        if not (tool_ok and param_ok):
            failures.append(
                {
                    "id": case.id,
                    "channel": case.channel,
                    "role": case.role,
                    "input": case.input,
                    "expected_tool": case.expected_tool,
                    "predicted_tool": raw.get("tool_name") or raw.get("tool"),
                    "tool_ok": tool_ok,
                    "param_ok": param_ok,
                    "arguments": raw.get("arguments"),
                }
            )

    total = len(cases)
    return EvalResult(
        total=total,
        tool_correct=tool_correct,
        param_correct=param_correct,
        tool_accuracy=accuracy(tool_correct, total),
        param_accuracy=accuracy(param_correct, total),
        failures=failures,
    )
