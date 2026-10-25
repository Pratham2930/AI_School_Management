import json
import uuid

from datetime import datetime, timezone

from confluent_kafka import Producer

from kafka_pipeline.config import (
    KAFKA_SERVER,
    SCHOOL_TOPIC
)


def create_producer():

    # Create a Kafka producer using the working Confluent client.
    return Producer({
        "bootstrap.servers": KAFKA_SERVER,
        "acks": "all",
        "message.send.max.retries": 3,
        "socket.timeout.ms": 10000
    })


def publish_event(event_type, entity_id, payload):

    # Preserve the existing school event structure.
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "entity_id": str(entity_id),
        "payload": payload,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    # Create the producer.
    producer = create_producer()

    # Track whether Kafka confirms successful delivery.
    delivery_result = {
        "delivered": False,
        "error": None
    }

    def delivery_callback(error, message):

        if error is not None:
            delivery_result["error"] = error
        else:
            delivery_result["delivered"] = True

            print(
                "Published:",
                event_type,
                entity_id,
                "| Partition:",
                message.partition(),
                "| Offset:",
                message.offset()
            )

    # Convert the event dictionary into JSON bytes.
    event_json = json.dumps(
        event
    ).encode("utf-8")

    # Publish the event to Kafka.
    producer.produce(
        topic=SCHOOL_TOPIC,
        key=str(entity_id).encode("utf-8"),
        value=event_json,
        callback=delivery_callback
    )

    # Wait up to 15 seconds for pending messages to be delivered.
    remaining = producer.flush(timeout=15)

    # Raise an error if delivery was not confirmed.
    if remaining > 0:
        raise TimeoutError(
            "Kafka event delivery timed out."
        )

    if delivery_result["error"] is not None:
        raise RuntimeError(
            f"Kafka delivery failed: {delivery_result['error']}"
        )

    if not delivery_result["delivered"]:
        raise RuntimeError(
            "Kafka did not confirm event delivery."
        )

    return event


if __name__ == "__main__":

    # Publish a sample teacher assignment event.
    publish_event(
        "teacher.assignment.updated",
        "TCH-2026-0002",
        {
            "subject": "Mathematics",
            "standard": 8
        }
    )