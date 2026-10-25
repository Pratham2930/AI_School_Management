import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

import app as school_app
from kafka_pipeline import outbox_worker


class FakeProducer:
    def __init__(self, error=None):
        self.error = error
        self.message = None

    def produce(self, topic, key, value, callback):
        self.message = (
            topic,
            key,
            json.loads(value.decode("utf-8"))
        )
        callback(self.error, None)

    def flush(self, timeout):
        self.asserted_timeout = timeout
        return 0


class KafkaOutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_app = Flask("isolated-kafka-outbox-tests")
        self.test_app.config.update(
            SQLALCHEMY_DATABASE_URI=(
                "sqlite:///"
                + os.path.join(self.temp_dir.name, "outbox-tests.db")
            ),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"timeout": 10}}
        )
        school_app.db.init_app(self.test_app)
        with self.test_app.app_context():
            school_app.KafkaOutboxEvent.__table__.create(
                bind=school_app.db.engine,
                checkfirst=True
            )

    def tearDown(self):
        with self.test_app.app_context():
            school_app.db.session.remove()
            school_app.KafkaOutboxEvent.__table__.drop(
                bind=school_app.db.engine,
                checkfirst=True
            )
            school_app.db.engine.dispose()
        self.temp_dir.cleanup()

    def add_event(self, event_id, entity_id="entity-1"):
        with self.test_app.app_context():
            event = school_app.KafkaOutboxEvent(
                event_id=event_id,
                event_type="teacher.assignment.created",
                entity_id=entity_id,
                payload_json='{"assignment_id": 9}',
                created_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            school_app.db.session.add(event)
            school_app.db.session.commit()
            return event.id

    def test_concurrent_workers_claim_distinct_events(self):
        self.add_event("event-one", "entity-one")
        self.add_event("event-two", "entity-two")
        gate = threading.Barrier(2)

        def claim_event():
            with self.test_app.app_context():
                gate.wait(timeout=5)
                event = outbox_worker._claim_next_event()
                return event.id if event else None

        with ThreadPoolExecutor(max_workers=2) as executor:
            claimed_ids = list(executor.map(lambda _: claim_event(), range(2)))

        self.assertNotIn(None, claimed_ids)
        self.assertEqual(len(set(claimed_ids)), 2)

    def test_acknowledged_publish_preserves_event_id_and_marks_published(self):
        row_id = self.add_event("stable-event-id", "assignment-9")
        producer = FakeProducer()

        with self.test_app.app_context():
            self.assertTrue(outbox_worker.publish_next_event(producer))
            row = school_app.db.session.get(
                school_app.KafkaOutboxEvent,
                row_id
            )

        self.assertEqual(producer.message[1], b"assignment-9")
        self.assertEqual(
            producer.message[2]["event_id"],
            "stable-event-id"
        )
        self.assertEqual(
            producer.message[2]["payload"],
            {"assignment_id": 9}
        )
        self.assertEqual(row.attempts, 1)
        self.assertIsNotNone(row.published_at)
        self.assertIsNone(row.claim_token)
        self.assertIsNone(row.last_error)

    def test_exhausted_delivery_is_retained_for_admin_recovery(self):
        row_id = self.add_event("failed-event-id")
        producer = FakeProducer(RuntimeError("broker unavailable"))

        with self.test_app.app_context():
            with patch.object(
                outbox_worker,
                "MAX_DELIVERY_ATTEMPTS",
                1
            ):
                self.assertFalse(outbox_worker.publish_next_event(producer))
            row = school_app.db.session.get(
                school_app.KafkaOutboxEvent,
                row_id
            )

        self.assertEqual(row.attempts, 1)
        self.assertIsNotNone(row.failed_at)
        self.assertIsNone(row.published_at)
        self.assertIsNone(row.claim_token)
        self.assertIn("broker unavailable", row.last_error)

    def test_admin_recovery_requeues_exhausted_event(self):
        row_id = self.add_event("recoverable-event-id")
        with self.test_app.app_context():
            row = school_app.db.session.get(
                school_app.KafkaOutboxEvent,
                row_id
            )
            row.attempts = 10
            row.failed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            row.last_error = "previous failure"
            row.next_attempt_at = None
            row.claim_token = "expired-worker"
            row.claim_expires_at = datetime.now(timezone.utc).replace(tzinfo=None)
            school_app.db.session.commit()

            self.assertTrue(
                school_app._requeue_failed_kafka_outbox_event(row)
            )
            self.assertFalse(
                school_app._requeue_failed_kafka_outbox_event(row)
            )
            self.assertEqual(row.attempts, 0)
            self.assertIsNone(row.failed_at)
            self.assertIsNone(row.last_error)
            self.assertIsNone(row.claim_token)

    def test_expired_last_attempt_is_marked_failed(self):
        row_id = self.add_event("expired-final-claim")
        with self.test_app.app_context():
            row = school_app.db.session.get(
                school_app.KafkaOutboxEvent,
                row_id
            )
            row.attempts = outbox_worker.MAX_DELIVERY_ATTEMPTS
            row.claim_token = "worker-that-crashed"
            row.claim_expires_at = (
                datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(minutes=2)
            )
            school_app.db.session.commit()

            self.assertIsNone(outbox_worker._claim_next_event())
            row = school_app.db.session.get(
                school_app.KafkaOutboxEvent,
                row_id
            )

        self.assertIsNotNone(row.failed_at)
        self.assertIsNone(row.claim_token)
        self.assertIn("lease expired", row.last_error)


if __name__ == "__main__":
    unittest.main()
