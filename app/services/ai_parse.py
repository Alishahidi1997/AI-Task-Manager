import json
import os
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.services.category_guess import guess_category


def _fallback_parse(input_text: str):
    text = input_text.strip()
    now = datetime.now(timezone.utc)
    lowered = text.lower()

    due_date = None
    if "tomorrow" in lowered:
        due_date = now + timedelta(days=1)
    elif "next week" in lowered:
        due_date = now + timedelta(days=7)
    elif "today" in lowered:
        due_date = now

    title = text
    parts = re.split(r"[,.]| by | due ", text, maxsplit=1, flags=re.IGNORECASE)
    if parts and parts[0].strip():
        title = parts[0].strip()

    description = None
    if title != text:
        description = text

    category = guess_category(title, description or "", due_date)

    confidence = "low"
    if title and len(title.split()) >= 3:
        confidence = "medium"
    if due_date and title and len(title.split()) >= 3:
        confidence = "high"

    return {
        "title": title[:255],
        "description": (description or "")[:8000] or None,
        "due_date": due_date.isoformat() if due_date else None,
        "category": category,
        "confidence": confidence,
        "mode": "fallback",
    }


def _openai_parse(input_text: str, api_key: str):
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    now = datetime.now(timezone.utc).isoformat()
    messages = [
        {
            "role": "system",
            "content": (
                "Extract task fields from user text. Return strict JSON only with keys: "
                "title, description, due_date, category, confidence. "
                "category must be one of: today,this_week,routine,backlog. "
                "confidence must be one of: low,medium,high. "
                "due_date must be ISO-8601 with timezone or null."
            ),
        },
        {"role": "user", "content": f"Now: {now}\nTask text: {input_text}"},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 220,
        "response_format": {"type": "json_object"},
    }

    with httpx.Client(timeout=45.0) as client:
        response = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    category = parsed.get("category") or "backlog"
    if category not in {"today", "this_week", "routine", "backlog"}:
        category = "backlog"
    confidence = parsed.get("confidence") or "medium"
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"

    return {
        "title": str(parsed.get("title") or input_text).strip()[:255],
        "description": (str(parsed.get("description") or "").strip()[:8000] or None),
        "due_date": parsed.get("due_date"),
        "category": category,
        "confidence": confidence,
        "mode": "openai",
    }


def parse_task_text(input_text: str):
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        parsed = _fallback_parse(input_text)
        parsed["reason"] = "OPENAI_API_KEY is not set; used local parser fallback."
        return parsed
    try:
        return _openai_parse(input_text, key)
    except Exception as exc:
        parsed = _fallback_parse(input_text)
        parsed["reason"] = f"OpenAI parse failed ({type(exc).__name__}); used local parser fallback."
        return parsed
