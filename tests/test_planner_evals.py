"""Epic 4 planner eval suite — mocked by default, live when EVAL_LIVE=1."""

from __future__ import annotations

import os

import pytest

from app.evals.keyword_planner import keyword_planner
from app.evals.loader import load_golden_cases
from app.evals.live_planner import live_planner
from app.evals.models import GoldenCase
from app.evals.runner import run_eval_suite
from app.evals.scoring import score_case


def test_golden_file_has_minimum_cases():
    cases = load_golden_cases()
    assert len(cases) >= 50


def test_eval_scoring_unit():
    case = GoldenCase(
        id="unit",
        channel="chat",
        role="employee",
        input="x",
        expected_tool="create_task",
        required_arg_keys=["title", "due_date"],
        expected_arg_values={"title": "Hello"},
    )
    raw = {
        "tool_name": "create_task",
        "arguments": {"title": "Hello", "due_date": "2099-01-01"},
        "confidence": 0.9,
        "missing_required": [],
    }
    tool_ok, param_ok = score_case(case, raw)
    assert tool_ok is True
    assert param_ok is True


def test_golden_suite_mocked_meets_thresholds():
    min_tool = float(os.getenv("EVAL_TOOL_ACCURACY_MIN", "0.95"))
    min_param = float(os.getenv("EVAL_PARAM_ACCURACY_MIN", "0.90"))
    cases = load_golden_cases()
    result = run_eval_suite(keyword_planner, cases)
    assert result.tool_accuracy >= min_tool, result.failures[:5]
    assert result.param_accuracy >= min_param, result.failures[:5]


@pytest.mark.live_openai
def test_golden_suite_live_openai():
    if os.getenv("EVAL_LIVE", "").strip().lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("set EVAL_LIVE=1 to run paid OpenAI eval")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        pytest.skip("OPENAI_API_KEY required for live eval")

    min_tool = float(os.getenv("EVAL_LIVE_TOOL_ACCURACY_MIN", "0.80"))
    min_param = float(os.getenv("EVAL_LIVE_PARAM_ACCURACY_MIN", "0.70"))
    cases = load_golden_cases()
    result = run_eval_suite(live_planner, cases)
    result.assert_thresholds(min_tool=min_tool, min_param=min_param)
