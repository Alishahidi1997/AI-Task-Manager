from __future__ import annotations

import json
from pathlib import Path

from app.evals.models import GoldenCase

DEFAULT_GOLDEN_PATH = Path(__file__).resolve().parents[2] / "tests" / "evals" / "golden_prompts.jsonl"


def load_golden_cases(path: Path | None = None) -> list[GoldenCase]:
    golden_path = path or DEFAULT_GOLDEN_PATH
    cases: list[GoldenCase] = []
    with golden_path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            cases.append(
                GoldenCase(
                    id=str(row.get("id") or f"case-{line_no}"),
                    channel=str(row["channel"]).strip().lower(),
                    role=str(row.get("role") or "employee").strip().lower(),
                    input=str(row["input"]),
                    expected_tool=str(row["expected_tool"]),
                    required_arg_keys=list(row.get("required_arg_keys") or []),
                    expected_arg_values=dict(row.get("expected_arg_values") or {}),
                )
            )
    if len(cases) < 50:
        raise ValueError(f"golden set must have at least 50 rows (found {len(cases)})")
    return cases
