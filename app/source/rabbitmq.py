from __future__ import annotations

import json
import os
from dataclasses import dataclass

import pika


QUEUE_NAME = os.getenv("RABBITMQ_QUEUE", "ml_task_queue")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "")


@dataclass(frozen=True)
class QueueMessage:
    task_id: int

    def to_json(self) -> str:
        return json.dumps({"task_id": self.task_id})


def is_queue_enabled() -> bool:
    return bool(RABBITMQ_URL)


def make_connection() -> pika.BlockingConnection:
    if not RABBITMQ_URL:
        raise RuntimeError("RABBITMQ_URL is not configured")
    return pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))


def publish_prediction_task(task_id: int) -> None:
    message = QueueMessage(task_id=task_id)
    connection = make_connection()
    try:
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=message.to_json(),
            properties=pika.BasicProperties(delivery_mode=2),
        )
    finally:
        connection.close()
