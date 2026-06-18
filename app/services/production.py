"""Production environment guards (Phase 3.7)."""

from __future__ import annotations

import os


def is_production() -> bool:
    return os.getenv("APP_ENV", "").strip().lower() == "production"


def demo_mode_enabled() -> bool:
    """Demo routes on by default in non-production unless DEMO_MODE=false."""
    raw = os.getenv("DEMO_MODE", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return not is_production()


def validate_production_settings() -> None:
    if not is_production():
        return
    jwt = os.getenv("JWT_SECRET_KEY", "").strip()
    if not jwt or jwt == "change-me-in-production":
        raise RuntimeError("JWT_SECRET_KEY must be set to a strong value when APP_ENV=production")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OPENAI_API_KEY is required when APP_ENV=production")
