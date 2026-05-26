import os

EXCHANGE_NAME = "llm.tasks"
QUEUE_ORCHESTRATION = "llm.orchestration.high"
QUEUE_BATCH = "llm.batch.low"
ROUTING_ORCHESTRATION = "orchestration.high"
ROUTING_BATCH = "batch.low"

JOB_SLACK_ORCHESTRATION = "slack_orchestration"
JOB_CHAT_ORCHESTRATION = "chat_orchestration"
JOB_DAILY_SUMMARY = "daily_summary"
JOB_CHAT_STREAM = "chat_planner_stream"


def chat_stream_queue_enabled() -> bool:
    """Queue /chat/stream when RabbitMQ + Redis are available."""
    if not llm_queue_enabled():
        return False
    if not os.getenv("REDIS_URL", "").strip():
        return False
    flag = os.getenv("CHAT_STREAM_QUEUE_ENABLED", "true").strip().lower()
    return flag not in {"0", "false", "no", "off"}


def rabbitmq_url() -> str:
    return os.getenv("RABBITMQ_URL", "").strip()


def llm_queue_enabled() -> bool:
    """Queue mode when RABBITMQ_URL is set and LLM_QUEUE_ENABLED is not explicitly off."""
    if not rabbitmq_url():
        return False
    flag = os.getenv("LLM_QUEUE_ENABLED", "true").strip().lower()
    return flag not in {"0", "false", "no", "off"}
