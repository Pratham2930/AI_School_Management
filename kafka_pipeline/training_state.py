import json
import os
import tempfile

from kafka_pipeline.config import RETRAIN_THRESHOLD


BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

STATE_FILE = os.path.join(
    BASE_DIR,
    "instance",
    "ml_training_state.json"
)

RELEVANT_EVENTS = {
    "teacher.assignment.created",
    "teacher.assignment.updated",
    "teacher.assignment.deleted",
    "teacher.availability.updated",
    "timetable.updated",
    "timetable.approved"
}


def load_state():

    default_state = {
        "pending_events": 0,
        "training_required": False,
        "processed_event_ids": []
    }

    if not os.path.exists(STATE_FILE):
        return default_state

    with open(
        STATE_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        state = json.load(file)

    # Preserve existing counts from the previous format.
    for key, value in default_state.items():
        state.setdefault(key, value)

    return state


def save_state(state):

    directory = os.path.dirname(STATE_FILE)

    os.makedirs(
        directory,
        exist_ok=True
    )

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            delete=False
        ) as file:

            json.dump(
                state,
                file,
                indent=4
            )

            temporary_path = file.name

        os.replace(
            temporary_path,
            STATE_FILE
        )

    finally:
        if (
            temporary_path
            and os.path.exists(temporary_path)
        ):
            os.remove(temporary_path)


def process_training_event(event):

    event_type = event.get("event_type", "")
    event_id = event.get("event_id")

    if event_type not in RELEVANT_EVENTS:

        print(
            "Event does not require timetable training."
        )

        return False

    if not event_id:
        raise ValueError(
            "Relevant Kafka event is missing event_id."
        )

    state = load_state()

    processed_ids = state["processed_event_ids"]

    if event_id in processed_ids:

        print(
            "Duplicate event skipped:",
            event_id
        )

        return state["training_required"]

    state["pending_events"] += 1

    processed_ids.append(event_id)

    if state["pending_events"] >= RETRAIN_THRESHOLD:
        state["training_required"] = True

    save_state(state)

    print(
        "Relevant events:",
        state["pending_events"]
    )

    return state["training_required"]