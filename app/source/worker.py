from __future__ import annotations

import json
import logging
import os
import time
from decimal import Decimal

import pika
from sqlalchemy.exc import OperationalError

from .auth import build_prediction_result
from .db import engine
from .db import get_session
from .domain import Base
from .domain import Direction
from .domain import MarketRegime
from .domain import PredictionTask
from .domain import VolatilityLevel
from .init_db import init_db
from .rabbitmq import QUEUE_NAME
from .rabbitmq import make_connection
from .services import complete_prediction_task
from .services import fail_prediction_task


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ml-worker")


WORKER_ID = os.getenv("WORKER_ID", "worker-1")
PROCESSING_DELAY_SECONDS = float(os.getenv("ML_WORKER_DELAY_SECONDS", "1"))


def prepare_database() -> None:
    for attempt in range(1, 31):
        try:
            Base.metadata.create_all(bind=engine)
            with get_session() as session:
                init_db(session)
            return
        except OperationalError:
            logger.info("Database is not ready, retry %s/30", attempt)
            time.sleep(2)
    raise RuntimeError("Database connection was not established")


def process_task(task_id: int) -> None:
    with get_session() as session:
        task = session.get(PredictionTask, task_id)
        if task is None:
            logger.warning("Task %s was not found", task_id)
            return

        try:
            time.sleep(PROCESSING_DELAY_SECONDS)
            result = build_prediction_result(task.input_payload)
            complete_prediction_task(
                session=session,
                task_id=task.id,
                worker_id=WORKER_ID,
                direction=Direction(result["direction"]),
                probability=Decimal(str(result["probability"])),
                volatility_level=VolatilityLevel(result["volatility_level"]),
                market_regime=MarketRegime(result["market_regime"]),
            )
            logger.info("Task %s processed by %s", task.id, WORKER_ID)
        except Exception as exc:
            fail_prediction_task(session, task.id, WORKER_ID, str(exc))
            logger.exception("Task %s failed", task.id)


def on_message(channel, method, _properties, body: bytes) -> None:
    try:
        payload = json.loads(body.decode("utf-8"))
        process_task(int(payload["task_id"]))
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception("Invalid queue message: %r", body)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def run() -> None:
    prepare_database()

    connection = None
    for attempt in range(1, 31):
        try:
            connection = make_connection()
            break
        except pika.exceptions.AMQPConnectionError:
            logger.info("RabbitMQ is not ready, retry %s/30", attempt)
            time.sleep(2)
    if connection is None:
        raise RuntimeError("RabbitMQ connection was not established")

    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message, auto_ack=False)
    logger.info("%s is waiting for RabbitMQ tasks from %s", WORKER_ID, QUEUE_NAME)
    channel.start_consuming()


if __name__ == "__main__":
    run()
