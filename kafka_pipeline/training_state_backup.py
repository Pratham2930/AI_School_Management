
import json
import os
import tempfile

from kafka_pipeline.config import (
    RETRAIN_THRESHOLD
)


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

    if not os.path.exists(STATE_FILE):

        return {
            "pending_events": 0,
            "training_required": False
        }

    with open(
        STATE_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def save_state(state):

    directory = os.path.dirname(
        STATE_FILE
    )

    os.makedirs(
        directory,
        exist_ok=True
    )

    # Write to a temporary file before replacing
    # the previous state file.
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


def process_training_event(event):

    event_type = event.get(
        "event_type",
        ""
    )

    if event_type not in RELEVANT_EVENTS:

        print(
            "Event does not require timetable training."
        )

        return False

    state = load_state()

    state["pending_events"] += 1

    if state["pending_events"] >= RETRAIN_THRESHOLD:

        state["training_required"] = True

    save_state(state)

    print(
        "Relevant events:",
        state["pending_events"]
    )

    return state["training_required"]
