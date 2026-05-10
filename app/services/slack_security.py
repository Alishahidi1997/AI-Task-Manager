import hashlib
import hmac
import os
import time

from fastapi import HTTPException


def verify_slack_signature(
    *,
    timestamp: str | None,
    signature: str | None,
    raw_body: bytes,
):
    if os.getenv("SLACK_SKIP_SIGNATURE_VERIFY", "").strip().lower() in {"1", "true", "yes"}:
        return
    if not timestamp or not signature:
        raise HTTPException(status_code=401, detail="missing slack signature headers")
    secret = os.getenv("SLACK_SIGNING_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="SLACK_SIGNING_SECRET is not configured")
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid slack timestamp") from exc
    if abs(int(time.time()) - ts) > 60 * 5:
        raise HTTPException(status_code=401, detail="slack request expired")

    basestring = f"v0:{timestamp}:{raw_body.decode('utf-8')}"
    expected = "v0=" + hmac.new(
        secret.encode("utf-8"),
        basestring.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="invalid slack signature")
