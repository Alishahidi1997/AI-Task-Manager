"""CLI: python -m app.evals [--live]"""

from __future__ import annotations

import argparse
import os
import sys

from app.evals.keyword_planner import keyword_planner
from app.evals.live_planner import live_planner
from app.evals.loader import load_golden_cases
from app.evals.runner import run_eval_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Run planner golden eval suite")
    parser.add_argument("--live", action="store_true", help="Call OpenAI (requires OPENAI_API_KEY)")
    parser.add_argument("--min-tool", type=float, default=float(os.getenv("EVAL_TOOL_ACCURACY_MIN", "0.95")))
    parser.add_argument("--min-param", type=float, default=float(os.getenv("EVAL_PARAM_ACCURACY_MIN", "0.90")))
    args = parser.parse_args()

    cases = load_golden_cases()
    planner = live_planner if args.live else keyword_planner
    result = run_eval_suite(planner, cases)
    print(
        f"cases={result.total} tool_accuracy={result.tool_accuracy:.3f} "
        f"param_accuracy={result.param_accuracy:.3f} failures={len(result.failures)}"
    )
    try:
        result.assert_thresholds(min_tool=args.min_tool, min_param=args.min_param)
    except AssertionError as exc:
        print(str(exc), file=sys.stderr)
        for row in result.failures[:10]:
            print(f"  - {row['id']}: tool_ok={row['tool_ok']} param_ok={row['param_ok']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
