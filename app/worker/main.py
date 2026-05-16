"""
Run the LLM orchestration worker:

    python -m app.worker.main

Requires RABBITMQ_URL (see docker-compose.yml).
"""

from __future__ import annotations

import json
import logging
import sys

import pika

from app.queue.config import QUEUE_ORCHESTRATION, ROUTING_ORCHESTRATION, rabbitmq_url
from app.queue.publisher import _ensure_topology
from app.worker.handlers import process_llm_job_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _on_message(channel, method, properties, body):  # noqa: ARG001
    try:
        message = json.loads(body.decode("utf-8"))
        process_llm_job_message(message)
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main() -> int:
    url = rabbitmq_url()
    if not url:
        logger.error("RABBITMQ_URL is not set")
        return 1

    params = pika.URLParameters(url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    _ensure_topology(channel)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_ORCHESTRATION, on_message_callback=_on_message)
    logger.info("worker listening on queue=%s", QUEUE_ORCHESTRATION)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
