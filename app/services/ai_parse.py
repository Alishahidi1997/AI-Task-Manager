import json
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app.services.category_guess import guess_category


def _resolve_tz(user_timezone: str | None):
    if not user_timezone:
        return timezone.utc
    try:
        return ZoneInfo(user_timezone.strip())
    except Exception:
        return timezone.utc


def _extract_time_components(input_text: str):
    lowered = input_text.lower()
    match = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lowered)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = match.group(3)
    if hour == 12:
        hour = 0
    if meridiem == "pm":
        hour += 12
    return hour, minute


def _fallback_parse(input_text: str, user_timezone: str | None):
    text = input_text.strip()
    tz = _resolve_tz(user_timezone)
    now = datetime.now(tz)
    lowered = text.lower()

    due_date = None
    if "tomorrow" in lowered:
        due_date = now + timedelta(days=1)
    elif "next week" in lowered:
        due_date = now + timedelta(days=7)
    elif "today" in lowered:
        due_date = now

    extracted_time = _extract_time_components(text)
    if due_date and extracted_time:
        hour, minute = extracted_time
        due_date = due_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

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


def _openai_parse(input_text: str, api_key: str, user_timezone: str | None):
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    tz = _resolve_tz(user_timezone)
    now = datetime.now(tz).isoformat()
    tz_name = user_timezone.strip() if user_timezone else "UTC"
    messages = [
        {
            "role": "system",
            "content": (
                "Extract task fields from user text. Return strict JSON only with keys: "
                "title, description, due_date, category, confidence. "
                "category must be one of: today,this_week,routine,backlog. "
                "confidence must be one of: low,medium,high. "
                "due_date must be ISO-8601 with timezone or null. "
                "When the user gives times like '5pm', interpret them in the user's timezone."
            ),
        },
        {
            "role": "user",
            "content": f"User timezone: {tz_name}\nNow: {now}\nTask text: {input_text}",
        },
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


def parse_task_text(input_text: str, user_timezone: str | None = None):
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        parsed = _fallback_parse(input_text, user_timezone)
        parsed["reason"] = "OPENAI_API_KEY is not set; used local parser fallback."
        return parsed
    try:
        return _openai_parse(input_text, key, user_timezone)
    except Exception as exc:
        parsed = _fallback_parse(input_text, user_timezone)
        parsed["reason"] = f"OpenAI parse failed ({type(exc).__name__}); used local parser fallback."
        return parsed


def _fallback_plan_task_text(input_text: str, user_timezone: str | None):
    separators = re.split(r"\band\b|,|;|\n", input_text, flags=re.IGNORECASE)
    parts = [p.strip(" .") for p in separators if p and p.strip(" .")]
    if not parts:
        parts = [input_text.strip()]

    global_parse = _fallback_parse(input_text, user_timezone)
    tasks = []
    for idx, chunk in enumerate(parts[:8], start=1):
        parsed = _fallback_parse(chunk, user_timezone)
        due_date = parsed.get("due_date") or global_parse.get("due_date")
        tasks.append(
            {
                "order": idx,
                "title": parsed.get("title") or chunk[:255],
                "description": parsed.get("description"),
                "due_date": due_date,
                "category": parsed.get("category") or "backlog",
                "priority": "medium",
            }
        )

    return {
        "roadmap_title": f"Roadmap: {input_text.strip()[:80]}",
        "tasks": tasks,
        "mode": "fallback",
        "reason": "OPENAI_API_KEY is not set; used local roadmap fallback.",
    }


def _openai_plan_task_text(input_text: str, api_key: str, user_timezone: str | None, horizon_days: int):
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    tz = _resolve_tz(user_timezone)
    now = datetime.now(tz).isoformat()
    tz_name = user_timezone.strip() if user_timezone else "UTC"
    messages = [
        {
            "role": "system",
            "content": (
                "Break goal text into an actionable roadmap. Return strict JSON only with keys: "
                "roadmap_title, tasks. tasks is an array of objects with keys: order, title, description, due_date, category, priority. "
                "category must be one of: today,this_week,routine,backlog. "
                "priority must be one of: low,medium,high. "
                "due_date must be ISO-8601 with timezone or null. Keep 2-8 tasks max."
            ),
        },
        {
            "role": "user",
            "content": (
                f"User timezone: {tz_name}\nNow: {now}\nHorizon days: {horizon_days}\n"
                f"Goal text: {input_text}"
            ),
        },
    ]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 700,
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

    parsed = json.loads(data["choices"][0]["message"]["content"])
    tasks = []
    for idx, item in enumerate((parsed.get("tasks") or [])[:8], start=1):
        category = str(item.get("category") or "backlog")
        if category not in {"today", "this_week", "routine", "backlog"}:
            category = "backlog"
        priority = str(item.get("priority") or "medium")
        if priority not in {"low", "medium", "high"}:
            priority = "medium"
        tasks.append(
            {
                "order": int(item.get("order") or idx),
                "title": str(item.get("title") or f"Step {idx}").strip()[:255],
                "description": (str(item.get("description") or "").strip()[:8000] or None),
                "due_date": item.get("due_date"),
                "category": category,
                "priority": priority,
            }
        )

    if not tasks:
        return _fallback_plan_task_text(input_text, user_timezone)

    return {
        "roadmap_title": str(parsed.get("roadmap_title") or f"Roadmap: {input_text[:80]}").strip()[:160],
        "tasks": tasks,
        "mode": "openai",
    }


def plan_task_text(input_text: str, user_timezone: str | None = None, horizon_days: int = 7):
    safe_horizon = max(1, min(30, int(horizon_days)))
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return _fallback_plan_task_text(input_text, user_timezone)
    try:
        return _openai_plan_task_text(input_text, key, user_timezone, safe_horizon)
    except Exception as exc:
        parsed = _fallback_plan_task_text(input_text, user_timezone)
        parsed["reason"] = f"OpenAI roadmap failed ({type(exc).__name__}); used local roadmap fallback."
        return parsed
