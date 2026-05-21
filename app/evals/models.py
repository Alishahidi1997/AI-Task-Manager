from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GoldenCase:
    id: str
    channel: str  # slack | chat
    role: str
    input: str
    expected_tool: str
    required_arg_keys: list[str] = field(default_factory=list)
    expected_arg_values: dict = field(default_factory=dict)
