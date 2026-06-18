"""Manual live API smoke test against a running server."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)

BASE = os.getenv("SMOKE_API_BASE", "http://127.0.0.1:8000").rstrip("/")


def call(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc


def main() -> int:
    failures: list[str] = []

    def check(name: str, fn):
        try:
            fn()
            print(f"OK  {name}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {exc}")
            print(f"FAIL {name}: {exc}")

    check("health", lambda: call("GET", "/"))

    token_holder: dict[str, str] = {}

    def register():
        email = f"live-smoke-{os.getpid()}@test.local"
        out = call("POST", "/auth/register", body={"email": email, "password": "secret123"})
        token_holder["token"] = out["access_token"]

    check("register", register)
    token = token_holder.get("token", "")

    check("tasks list", lambda: call("GET", "/tasks", token))
    check("workspace directory", lambda: call("GET", "/workspace/directory", token))

    if os.getenv("OPENAI_API_KEY", "").strip():
        chat = call(
            "POST",
            "/chat",
            token,
            {"message": "create task called Live smoke due tomorrow", "source": "live-smoke"},
        )
        if chat.get("status") != "executed":
            raise RuntimeError(f"chat status={chat.get('status')} reason={chat.get('reason')}")

        agent = call(
            "POST",
            "/ai/agent-command",
            token,
            {"query": "list my open tasks", "timezone": "UTC", "dry_run": True},
        )
        if not agent.get("assistant_message"):
            raise RuntimeError(f"agent missing assistant_message: {agent}")
    else:
        print("SKIP live AI (no OPENAI_API_KEY)")

    if failures:
        print("\nFailures:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
