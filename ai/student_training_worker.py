"""Kafka consumer that trains student-progress models for uploaded CSV jobs."""

import hashlib
import json
import logging
import os
import sys
from datetime import datetime

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from ai.student_ml import TrainingDataError, train_student_models


LOG = logging.getLogger("school_ai_training")


def process_training_event(app, event):
    from app import (
        StudentModelTrainingJob,
        _student_training_data_path,
        db,
    )

    if (
        not isinstance(event, dict)
        or event.get("event_type") != "student_progress_training_requested"
        or event.get("schema_version") != 1
        or not isinstance(event.get("job_id"), str)
    ):
        LOG.error("Skipping malformed or unsupported Kafka training event.")
        return

    with app.app_context():
        job = StudentModelTrainingJob.query.filter_by(
            job_id=event["job_id"]
        ).first()
        if not job:
            LOG.error("Training job %s does not exist.", event["job_id"])
            return
        if job.status == "Trained":
            try:
                completed_dataset = _student_training_data_path(
                    job.storage_filename
                )
                if os.path.isfile(completed_dataset):
                    os.remove(completed_dataset)
            except OSError:
                LOG.exception(
                    "Could not remove raw CSV for completed job %s.",
                    job.job_id,
                )
            LOG.info("Training job %s was already completed.", job.job_id)
            return

        try:
            dataset_path = _student_training_data_path(job.storage_filename)
            with open(dataset_path, "rb") as dataset_file:
                file_bytes = dataset_file.read(10 * 1024 * 1024 + 1)
            if len(file_bytes) > 10 * 1024 * 1024:
                raise TrainingDataError("The stored training CSV exceeds the 10 MB limit.")

            actual_digest = hashlib.sha256(file_bytes).hexdigest()
            if (
                actual_digest != job.dataset_sha256
                or actual_digest != event.get("dataset_sha256")
            ):
                raise TrainingDataError(
                    "The training CSV failed its integrity check."
                )

            job.status = "Training"
            job.message = "Training and evaluating both models on held-out students."
            job.started_at = datetime.utcnow()
            job.completed_at = None
            db.session.commit()

            metadata = train_student_models(
                file_bytes,
                os.path.join(app.instance_path, "ai_models")
            )
            job.status = "Trained"
            job.message = (
                "Both models trained successfully. Evaluation uses held-out students; "
                "review the metrics before using predictions."
            )
            job.row_count = metadata["training_records"]
            job.metrics_json = json.dumps(metadata)
            job.completed_at = datetime.utcnow()
            db.session.commit()

            try:
                os.remove(dataset_path)
            except OSError:
                LOG.exception(
                    "Training succeeded, but the private CSV for job %s could not be removed.",
                    job.job_id,
                )
            LOG.info("Student model training job %s completed.", job.job_id)
        except (OSError, ValueError, TrainingDataError, RuntimeError) as error:
            db.session.rollback()
            job = StudentModelTrainingJob.query.filter_by(
                job_id=event["job_id"]
            ).first()
            if not job:
                raise
            job.status = "Failed"
            job.message = str(error)[:1000]
            job.completed_at = datetime.utcnow()
            db.session.commit()
            LOG.exception("Student model training job %s failed.", job.job_id)
        except Exception:
            db.session.rollback()
            LOG.exception(
                "Unexpected failure processing student model training job %s.",
                event["job_id"],
            )
            raise
        finally:
            db.session.remove()


def run_worker():
    from app import app, initialize_database

    with app.app_context():
        initialize_database()

    bootstrap_servers = [
        server.strip()
        for server in os.environ.get(
            "KAFKA_BOOTSTRAP_SERVERS",
            "localhost:9092"
        ).split(",")
        if server.strip()
    ]
    if not bootstrap_servers:
        raise ValueError("Set KAFKA_BOOTSTRAP_SERVERS to a Kafka broker.")

    topic = os.environ.get(
        "KAFKA_STUDENT_TRAINING_TOPIC",
        "school.ml.student-progress.train"
    )
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        group_id=os.environ.get(
            "KAFKA_STUDENT_TRAINING_GROUP",
            "school-student-model-trainer"
        ),
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=lambda value: value,
        consumer_timeout_ms=1000
    )
    LOG.info(
        "Listening for student model training events on %s via %s.",
        topic,
        ", ".join(bootstrap_servers),
    )

    try:
        while True:
            for message in consumer:
                try:
                    try:
                        event = json.loads(message.value.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        LOG.error(
                            "Skipping malformed JSON training event at partition %s offset %s.",
                            message.partition,
                            message.offset,
                        )
                        consumer.commit()
                        continue
                    process_training_event(app, event)
                    consumer.commit()
                except KafkaError:
                    LOG.exception("Kafka error processing a student-model event.")
                    raise
                except Exception:
                    LOG.exception(
                        "Student-model event failed unexpectedly; it will be retried."
                    )
                    raise
    except KeyboardInterrupt:
        LOG.info("Student model training worker stopped.")
    finally:
        consumer.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        run_worker()
    except (KafkaError, OSError, ValueError) as error:
        LOG.error("Student model worker could not start: %s", error)
        sys.exit(1)
