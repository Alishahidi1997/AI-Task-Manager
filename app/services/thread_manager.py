"""Conversation thread storage for /chat and Slack (Epic 2 — context drift)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import ConversationThread, utcnow

MAX_TURNS = int(os.getenv("THREAD_MAX_TURNS", "10"))


def api_thread_key(user_id: int, conversation_id: str) -> str:
    return f"api:{user_id}:{conversation_id.strip()}"


def slack_thread_key(
    user_id: int,
    channel_id: str,
    *,
    thread_ts: str | None,
    message_ts: str | None,
) -> str:
    root = str(thread_ts or message_ts or "root")
    return f"slack:{user_id}:{channel_id}:{root}"


class ThreadManager:
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

    def load(self, thread_key: str) -> ConversationThread:
        row = (
            self.db.query(ConversationThread)
            .filter(
                ConversationThread.thread_key == thread_key,
                ConversationThread.user_id == self.user_id,
            )
            .first()
        )
        if row is None:
            row = ConversationThread(
                thread_key=thread_key,
                user_id=self.user_id,
                turns_json="[]",
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        return row

    def turns(self, row: ConversationThread) -> list[dict]:
        try:
            data = json.loads(row.turns_json or "[]")
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def add_turn(
        self,
        row: ConversationThread,
        role: str,
        content: str,
        *,
        task_id: int | None = None,
    ) -> None:
        turns = self.turns(row)
        turns.append(
            {
                "role": role,
                "content": content[:2000],
                "task_id": task_id,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        if len(turns) > MAX_TURNS:
            turns = turns[-MAX_TURNS:]
        row.turns_json = json.dumps(turns, ensure_ascii=True)
        row.updated_at = utcnow()
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)

    def set_last_task_id(self, row: ConversationThread, task_id: int | None) -> None:
        row.last_task_id = task_id
        row.updated_at = utcnow()
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)

    def set_pending(self, row: ConversationThread, pending: dict | None) -> None:
        row.pending_json = json.dumps(pending, ensure_ascii=True) if pending else None
        row.updated_at = utcnow()
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)

    def get_pending(self, row: ConversationThread) -> dict | None:
        if not row.pending_json:
            return None
        try:
            return json.loads(row.pending_json)
        except json.JSONDecodeError:
            return None

    def planner_context(self, row: ConversationThread | None) -> dict:
        if row is None:
            return {"last_task_id": None, "recent_turns": [], "pending": None}
        return {
            "last_task_id": row.last_task_id,
            "recent_turns": self.turns(row),
            "pending": self.get_pending(row),
        }

    def record_execution_result(self, row: ConversationThread | None, result: dict) -> None:
        if row is None:
            return
        status = result.get("status")
        if status == "executed":
            task_id = (result.get("result") or {}).get("task_id")
            if task_id is not None:
                self.set_last_task_id(row, int(task_id))
            self.set_pending(row, None)
        elif status == "clarification_required":
            self.set_pending(
                row,
                {
                    "question": result.get("question"),
                    "planner_output": result.get("planner_output"),
                },
            )
