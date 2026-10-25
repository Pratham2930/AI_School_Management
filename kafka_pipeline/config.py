import os

KAFKA_SERVER = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "127.0.0.1:9092"
)

SCHOOL_TOPIC = "school.data.events"

ML_CONSUMER_GROUP = "school-ml-training"

RETRAIN_THRESHOLD = 100