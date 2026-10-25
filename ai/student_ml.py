"""Train and load student-progress models from approved historical CSV data."""

import csv
import io
import json
import math
import os
import tempfile
import uuid
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline


REQUIRED_COLUMNS = {
    "student_id",
    "attendance_percentage",
    "average_marks",
    "final_percentage",
    "pass_fail",
}
OPTIONAL_FEATURES = (
    "previous_average_marks",
    "assignment_completion_percentage",
    "standard",
    "term_number",
)
FEATURE_COLUMNS = (
    "attendance_percentage",
    "average_marks",
    *OPTIONAL_FEATURES,
)
MINIMUM_ROWS = 50
MINIMUM_UNIQUE_STUDENTS = 30
MINIMUM_LABEL_STUDENTS = 5


class TrainingDataError(ValueError):
    """Raised when a dataset cannot support safe, meaningful training."""


def _parse_csv(file_bytes):
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise TrainingDataError("Upload a UTF-8 encoded CSV file.") from error

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise TrainingDataError("The CSV must include a header row.")

    headers = [header.strip().lower() for header in reader.fieldnames]
    if len(set(headers)) != len(headers):
        raise TrainingDataError("CSV column names must be unique.")

    missing = sorted(REQUIRED_COLUMNS - set(headers))
    if missing:
        raise TrainingDataError(
            "Missing required CSV columns: " + ", ".join(missing) + "."
        )

    rows = []
    for line_number, source in enumerate(reader, start=2):
        if None in source:
            raise TrainingDataError(
                f"Row {line_number} has more values than the header."
            )
        row = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in source.items()
        }
        if not any(row.values()):
            continue

        student_id = row.get("student_id", "")
        if not student_id:
            raise TrainingDataError(
                f"Row {line_number} is missing student_id; it is used only "
                "to keep each student's records together during evaluation."
            )

        numeric = {}
        for column in ("attendance_percentage", "average_marks", "final_percentage", *OPTIONAL_FEATURES):
            value = row.get(column, "")
            if not value:
                if column in {"attendance_percentage", "average_marks", "final_percentage"}:
                    raise TrainingDataError(
                        f"Row {line_number} is missing required value '{column}'."
                    )
                numeric[column] = np.nan
                continue
            try:
                numeric[column] = float(value)
            except ValueError as error:
                raise TrainingDataError(
                    f"Row {line_number} has a non-numeric '{column}' value."
                ) from error
            if not math.isfinite(numeric[column]):
                raise TrainingDataError(
                    f"Row {line_number} has a non-finite '{column}' value."
                )

        for column in (
            "attendance_percentage",
            "average_marks",
            "final_percentage",
            "previous_average_marks",
            "assignment_completion_percentage",
        ):
            value = numeric.get(column)
            if not np.isnan(value) and not 0 <= value <= 100:
                raise TrainingDataError(
                    f"Row {line_number} '{column}' must be between 0 and 100."
                )

        standard = numeric.get("standard")
        if not np.isnan(standard) and (
            not standard.is_integer() or not 1 <= standard <= 12
        ):
            raise TrainingDataError(
                f"Row {line_number} 'standard' must be a whole number from 1 to 12."
            )

        term_number = numeric.get("term_number")
        if not np.isnan(term_number) and (
            not term_number.is_integer() or term_number < 1
        ):
            raise TrainingDataError(
                f"Row {line_number} 'term_number' must be a positive whole number."
            )

        outcome = row.get("pass_fail", "").strip().lower()
        if outcome in {"pass", "passed", "yes", "true", "1"}:
            passed = 1
        elif outcome in {"fail", "failed", "no", "false", "0"}:
            passed = 0
        else:
            raise TrainingDataError(
                f"Row {line_number} 'pass_fail' must identify pass or fail."
            )

        rows.append(
            {
                "student_id": student_id,
                "features": numeric,
                "final_percentage": numeric["final_percentage"],
                "pass_fail": passed,
            }
        )

    if len(rows) < MINIMUM_ROWS:
        raise TrainingDataError(
            f"At least {MINIMUM_ROWS} labeled student-term records are required; "
            f"the CSV contains {len(rows)}."
        )

    unique_students = {row["student_id"] for row in rows}
    if len(unique_students) < MINIMUM_UNIQUE_STUDENTS:
        raise TrainingDataError(
            f"At least {MINIMUM_UNIQUE_STUDENTS} distinct students are required "
            "for a student-separated evaluation."
        )

    label_student_counts = {
        label: {
            row["student_id"] for row in rows if row["pass_fail"] == label
        }
        for label in (0, 1)
    }
    for label, name in ((0, "fail"), (1, "pass")):
        if len(label_student_counts[label]) < MINIMUM_LABEL_STUDENTS:
            raise TrainingDataError(
                f"At least {MINIMUM_LABEL_STUDENTS} distinct students with "
                f"'{name}' outcomes are required."
            )

    return rows


def validate_training_csv(file_bytes):
    """Validate data before queuing it and return its row count."""
    return len(_parse_csv(file_bytes))


def _split_by_student(groups, labels):
    for seed in range(42, 142):
        splitter = GroupShuffleSplit(
            n_splits=1,
            test_size=0.25,
            random_state=seed,
        )
        train_indices, test_indices = next(
            splitter.split(np.zeros(len(groups)), labels, groups)
        )
        if (
            set(labels[train_indices]) == {0, 1}
            and set(labels[test_indices]) == {0, 1}
            and len(set(groups[train_indices])) >= 10
        ):
            return train_indices, test_indices
    raise TrainingDataError(
        "Could not form a holdout set containing both pass and fail outcomes "
        "while keeping each student in only one split. Add more diverse "
        "historical student records."
    )


def train_student_models(file_bytes, output_directory):
    """Train/evaluate both targets and atomically publish a versioned artifact."""
    rows = _parse_csv(file_bytes)
    available_features = [
        column
        for column in FEATURE_COLUMNS
        if any(not np.isnan(row["features"][column]) for row in rows)
    ]
    if not {"attendance_percentage", "average_marks"}.issubset(available_features):
        raise TrainingDataError(
            "Attendance and average-mark features must be present."
        )

    feature_matrix = np.asarray(
        [
            [row["features"][column] for column in available_features]
            for row in rows
        ],
        dtype=float,
    )
    groups = np.asarray([row["student_id"] for row in rows], dtype=object)
    pass_labels = np.asarray([row["pass_fail"] for row in rows], dtype=int)
    final_percentages = np.asarray(
        [row["final_percentage"] for row in rows],
        dtype=float,
    )
    train_indices, test_indices = _split_by_student(groups, pass_labels)

    classifier = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=200,
                    min_samples_leaf=2,
                    class_weight="balanced",
                    random_state=42,
                    n_jobs=1,
                ),
            ),
        ]
    )
    regressor = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                RandomForestRegressor(
                    n_estimators=200,
                    min_samples_leaf=2,
                    random_state=42,
                    n_jobs=1,
                ),
            ),
        ]
    )

    classifier.fit(feature_matrix[train_indices], pass_labels[train_indices])
    regressor.fit(feature_matrix[train_indices], final_percentages[train_indices])

    pass_predictions = classifier.predict(feature_matrix[test_indices])
    percentage_predictions = np.clip(
        regressor.predict(feature_matrix[test_indices]),
        0,
        100,
    )
    pass_metrics = {
        "accuracy": round(float(accuracy_score(pass_labels[test_indices], pass_predictions)), 4),
        "balanced_accuracy": round(
            float(balanced_accuracy_score(pass_labels[test_indices], pass_predictions)),
            4,
        ),
        "macro_f1": round(
            float(f1_score(pass_labels[test_indices], pass_predictions, average="macro")),
            4,
        ),
        "pass_precision": round(
            float(precision_score(pass_labels[test_indices], pass_predictions, zero_division=0)),
            4,
        ),
        "pass_recall": round(
            float(recall_score(pass_labels[test_indices], pass_predictions, zero_division=0)),
            4,
        ),
    }
    percentage_metrics = {
        "mae_percentage_points": round(
            float(mean_absolute_error(final_percentages[test_indices], percentage_predictions)),
            3,
        ),
        "rmse_percentage_points": round(
            float(
                np.sqrt(
                    mean_squared_error(
                        final_percentages[test_indices],
                        percentage_predictions,
                    )
                )
            ),
            3,
        ),
        "r2": round(float(r2_score(final_percentages[test_indices], percentage_predictions)), 4),
    }

    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    metadata = {
        "schema_version": 1,
        "model_version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_records": len(rows),
        "unique_students": len(set(groups)),
        "training_students": len(set(groups[train_indices])),
        "holdout_students": len(set(groups[test_indices])),
        "training_rows": len(train_indices),
        "holdout_rows": len(test_indices),
        "features": available_features,
        "targets": ["pass_fail", "final_percentage"],
        "metrics": {
            "pass_fail": pass_metrics,
            "final_percentage": percentage_metrics,
        },
        "evaluation_note": (
            "Metrics are measured on a held-out set of students. They do not "
            "guarantee future accuracy and should not be used alone for high-stakes decisions."
        ),
    }
    artifact = {
        "metadata": metadata,
        "classifier": classifier,
        "regressor": regressor,
    }

    output_path = os.path.abspath(output_directory)
    os.makedirs(output_path, exist_ok=True)
    versioned_path = os.path.join(output_path, f"student_progress_{version}.joblib")
    latest_path = os.path.join(output_path, "student_progress_latest.joblib")
    latest_metadata_path = os.path.join(output_path, "student_progress_latest.json")

    temporary_files = []
    try:
        for destination, writer in (
            (versioned_path, lambda handle: joblib.dump(artifact, handle)),
            (latest_metadata_path, lambda handle: handle.write(json.dumps(metadata, indent=2))),
        ):
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=".student-progress-",
                suffix=".tmp",
                dir=output_path,
            )
            temporary_files.append(temporary_path)
            with os.fdopen(descriptor, "wb" if destination.endswith(".joblib") else "w", encoding=None if destination.endswith(".joblib") else "utf-8") as handle:
                writer(handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, destination)
            temporary_files.remove(temporary_path)

        descriptor, temporary_latest = tempfile.mkstemp(
            prefix=".student-progress-latest-",
            suffix=".tmp",
            dir=output_path,
        )
        temporary_files.append(temporary_latest)
        with os.fdopen(descriptor, "wb") as handle:
            joblib.dump(artifact, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_latest, latest_path)
        temporary_files.remove(temporary_latest)
    finally:
        for temporary_path in temporary_files:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass

    return metadata


def load_latest_student_models(model_directory):
    """Load the latest locally trained artifact, if one exists."""
    path = os.path.join(model_directory, "student_progress_latest.joblib")
    if not os.path.isfile(path):
        return None
    return joblib.load(path)
