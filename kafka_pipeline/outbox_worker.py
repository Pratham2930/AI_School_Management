import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

from confluent_kafka import Producer
from sqlalchemy import inspect
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from app import (
    KafkaOutboxEvent,
    app,
    db
)
from kafka_pipeline.config import KAFKA_SERVER, SCHOOL_TOPIC


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)
MAX_DELIVERY_ATTEMPTS = 10
RETRY_BASE_SECONDS = 5
RETRY_MAX_SECONDS = 3600
CLAIM_LEASE_SECONDS = 60


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_producer():
    return Producer({
        "bootstrap.servers": KAFKA_SERVER,
        "acks": "all",
        "enable.idempotence": True,
        "message.send.max.retries": 5
    })


def _event_envelope(row):
    created_at = row.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)

    return {
        "event_id": row.event_id,
        "event_type": row.event_type,
        "entity_id": row.entity_id,
        "payload": json.loads(row.payload_json),
        "created_at": created_at.isoformat()
    }


def publish_outbox_event(producer, row):
    envelope = _event_envelope(row)
    delivery = {
        "success": False,
        "error": None
    }

    def on_delivery(error, _message):
        if error is not None:
            delivery["error"] = error
        else:
            delivery["success"] = True

    producer.produce(
        topic=SCHOOL_TOPIC,
        key=row.entity_id.encode("utf-8"),
        value=json.dumps(envelope).encode("utf-8"),
        callback=on_delivery
    )

    remaining = producer.flush(timeout=15)
    if remaining > 0:
        raise TimeoutError("Kafka outbox event delivery timed out.")
    if delivery["error"] is not None:
        raise RuntimeError(
            f"Kafka outbox event delivery failed: {delivery['error']}"
        )
    if not delivery["success"]:
        raise RuntimeError("Kafka did not confirm outbox event delivery.")


def _claim_next_event():
    now = _utcnow_naive()
    claim_token = str(uuid.uuid4())
    claim_expires_at = now + timedelta(seconds=CLAIM_LEASE_SECONDS)
    recovered_count = db.session.execute(
        update(KafkaOutboxEvent)
        .where(
            KafkaOutboxEvent.published_at.is_(None),
            KafkaOutboxEvent.failed_at.is_(None),
            KafkaOutboxEvent.attempts >= MAX_DELIVERY_ATTEMPTS,
            or_(
                KafkaOutboxEvent.claim_token.is_(None),
                KafkaOutboxEvent.claim_expires_at.is_(None),
                KafkaOutboxEvent.claim_expires_at <= now
            )
        )
        .values(
            failed_at=now,
            next_attempt_at=None,
            claim_token=None,
            claim_expires_at=None,
            last_error=func.coalesce(
                KafkaOutboxEvent.last_error,
                "The delivery lease expired after the maximum attempts."
            )
        )
    ).rowcount
    if recovered_count:
        logger.error(
            "Marked %s expired outbox event claim(s) as failed after "
            "the maximum attempts.",
            recovered_count
        )

    available = and_(
        KafkaOutboxEvent.published_at.is_(None),
        KafkaOutboxEvent.failed_at.is_(None),
        KafkaOutboxEvent.attempts < MAX_DELIVERY_ATTEMPTS,
        or_(
            KafkaOutboxEvent.next_attempt_at.is_(None),
            KafkaOutboxEvent.next_attempt_at <= now
        ),
        or_(
            KafkaOutboxEvent.claim_token.is_(None),
            KafkaOutboxEvent.claim_expires_at.is_(None),
            KafkaOutboxEvent.claim_expires_at <= now
        )
    )
    candidate_id = (
        select(KafkaOutboxEvent.id)
        .where(available)
        .order_by(KafkaOutboxEvent.id.asc())
        .limit(1)
        .scalar_subquery()
    )
    result = db.session.execute(
        update(KafkaOutboxEvent)
        .where(
            KafkaOutboxEvent.id == candidate_id,
            available
        )
        .values(
            claim_token=claim_token,
            claim_expires_at=claim_expires_at,
            attempts=KafkaOutboxEvent.attempts + 1
        )
    )
    if result.rowcount != 1:
        if recovered_count:
            db.session.commit()
        else:
            db.session.rollback()
        return None

    event_id = db.session.execute(
        select(KafkaOutboxEvent.id)
        .where(KafkaOutboxEvent.claim_token == claim_token)
    ).scalar_one()
    db.session.commit()
    return db.session.get(KafkaOutboxEvent, event_id)


def publish_next_event(producer):
    row = _claim_next_event()
    if row is None:
        return False

    row_id = row.id

    try:
        publish_outbox_event(producer, row)
    except Exception as error:
        db.session.rollback()
        failed_row = db.session.get(KafkaOutboxEvent, row_id)
        if failed_row is None:
            raise RuntimeError(
                f"Outbox event {row_id} disappeared after a Kafka publish failure."
            ) from error
        failed_row.last_error = str(error)[:4000]
        failed_row.claim_token = None
        failed_row.claim_expires_at = None
        if failed_row.attempts >= MAX_DELIVERY_ATTEMPTS:
            failed_row.failed_at = _utcnow_naive()
            failed_row.next_attempt_at = None
            logger.error(
                "Outbox event %s exhausted %s delivery attempts and needs "
                "administrator retry.",
                failed_row.event_id,
                MAX_DELIVERY_ATTEMPTS
            )
        else:
            delay_seconds = min(
                RETRY_BASE_SECONDS * (2 ** (failed_row.attempts - 1)),
                RETRY_MAX_SECONDS
            )
            failed_row.next_attempt_at = (
                _utcnow_naive() + timedelta(seconds=delay_seconds)
            )
        db.session.commit()
        logger.warning(
            "Kafka publish failed for outbox event %s on attempt %s: %s",
            failed_row.event_id,
            failed_row.attempts,
            failed_row.last_error
        )
        return False

    row.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
    row.last_error = None
    row.next_attempt_at = None
    row.claim_token = None
    row.claim_expires_at = None
    db.session.commit()
    logger.info(
        "Published outbox event %s (%s).",
        row.event_id,
        row.event_type
    )
    return True


def run_worker():
    try:
        poll_interval = float(
            os.environ.get("KAFKA_OUTBOX_POLL_INTERVAL_SECONDS", "1")
        )
    except ValueError as error:
        raise RuntimeError(
            "KAFKA_OUTBOX_POLL_INTERVAL_SECONDS must be a positive number."
        ) from error
    if poll_interval <= 0:
        raise RuntimeError(
            "KAFKA_OUTBOX_POLL_INTERVAL_SECONDS must be a positive number."
        )

    with app.app_context():
        required_columns = {
            "next_attempt_at",
            "claim_token",
            "claim_expires_at",
            "failed_at"
        }
        existing_columns = {
            column["name"]
            for column in inspect(db.engine).get_columns("kafka_outbox_event")
        }
        missing_columns = required_columns - existing_columns
        if missing_columns:
            raise RuntimeError(
                "The Kafka outbox schema is not initialized. Start Flask once "
                "to apply database migrations, then restart the outbox worker."
            )

    producer = create_producer()
    logger.info("Kafka outbox worker started for topic %s.", SCHOOL_TOPIC)
    try:
        while True:
            try:
                with app.app_context():
                    published = publish_next_event(producer)
            except SQLAlchemyError:
                logger.exception(
                    "Database error while dispatching the Kafka outbox; "
                    "the worker will retry."
                )
                db.session.rollback()
                published = False
            if not published:
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("Kafka outbox worker stopping.")
    finally:
        remaining = producer.flush(timeout=15)
        if remaining:
            logger.warning(
                "%s Kafka message(s) remained undelivered at shutdown.",
                remaining
            )


if __name__ == "__main__":
    run_worker()
