"""Publish orchestration jobs to RabbitMQ (sync pika — call via asyncio.to_thread in routes)."""

from __future__ import annotations

import json

import pika

from app.queue.config import (
    EXCHANGE_NAME,
    QUEUE_BATCH,
    QUEUE_ORCHESTRATION,
    ROUTING_BATCH,
    ROUTING_ORCHESTRATION,
    is_batch_job,
    rabbitmq_url,
)


def _orchestration_queue() -> str:
    return QUEUE_ORCHESTRATION


def _ensure_topology(channel: pika.channel.Channel) -> None:
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type="topic", durable=True)
    channel.queue_declare(queue=QUEUE_ORCHESTRATION, durable=True)
    channel.queue_declare(queue=QUEUE_BATCH, durable=True)
    channel.queue_bind(
        exchange=EXCHANGE_NAME, queue=QUEUE_ORCHESTRATION, routing_key=ROUTING_ORCHESTRATION
    )
    channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_BATCH, routing_key=ROUTING_BATCH)


def publish_llm_job(message: dict, *, job_type: str) -> None:
    """Publish a job dict (must include job_id). Raises on broker failure."""
    routing_key = ROUTING_BATCH if is_batch_job(job_type) else ROUTING_ORCHESTRATION
    body = json.dumps(message, ensure_ascii=True).encode("utf-8")
    params = pika.URLParameters(rabbitmq_url())
    connection = pika.BlockingConnection(params)
    try:
        channel = connection.channel()
        _ensure_topology(channel)
        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
                message_id=str(message.get("job_id", "")),
            ),
        )
    finally:
        connection.close()
