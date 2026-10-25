import json

from confluent_kafka import (
    Consumer,
    KafkaException
)

from kafka_pipeline.config import (
    KAFKA_SERVER,
    SCHOOL_TOPIC,
    ML_CONSUMER_GROUP
)

from kafka_pipeline.training_state import (
    process_training_event
)


def start_consumer():

    # Configure the Kafka consumer.
    consumer = Consumer({
        "bootstrap.servers": KAFKA_SERVER,
        "group.id": ML_CONSUMER_GROUP,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False
    })

    try:

        # Subscribe to the school event topic.
        consumer.subscribe([SCHOOL_TOPIC])

        print(
            "Kafka ML consumer started...",
            flush=True
        )

        print(
            "Waiting for school events...",
            flush=True
        )

        # Keep listening for Kafka messages.
        while True:

            # Wait up to one second for a message.
            message = consumer.poll(timeout=1.0)

            # Continue waiting when no message is available.
            if message is None:
                continue

            # Check for Kafka message errors.
            if message.error():
                raise KafkaException(
                    message.error()
                )

            try:

                # Decode the Kafka message from JSON.
                event = json.loads(
                    message.value().decode("utf-8")
                )

                # Print the received event type.
                print(
                    "\nReceived:",
                    event.get("event_type"),
                    flush=True
                )

                # Process the event using the existing
                # ML training counter logic.
                training_required = process_training_event(
                    event
                )

                # Display a message when retraining is required.
                if training_required:
                    print(
                        "Retraining threshold reached. "
                        "Training job is required.",
                        flush=True
                    )

                # Commit only after successful processing.
                consumer.commit(
                    message=message,
                    asynchronous=False
                )

                print(
                    "Event processed and offset committed.",
                    flush=True
                )

            except Exception as error:

                # Do not commit the failed message.
                print(
                    "Consumer error:",
                    error,
                    flush=True
                )

                # Stop so the failed event can be investigated.
                raise

    except KeyboardInterrupt:

        print(
            "\nStopping Kafka consumer..."
        )

    finally:

        # Leave the consumer group cleanly.
        consumer.close()

        print(
            "Kafka consumer closed."
        )


if __name__ == "__main__":

    start_consumer()