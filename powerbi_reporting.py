"""Privacy-minimized, star-schema-friendly school reporting extracts."""

import hashlib
import hmac
import json
import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime


DATASET_COLUMNS = {
    "dim_date": ["date_key", "date", "year", "quarter", "month", "day", "weekday"],
    "dim_class": [
        "class_key", "standard", "stream", "division", "academic_year",
        "capacity", "active", "enrollment_count"
    ],
    "dim_subject": ["subject_key", "subject_code", "subject_name"],
    "dim_student": [
        "student_key", "class_key", "current_standard", "active",
        "admission_status"
    ],
    "dim_teacher": ["teacher_key", "active"],
    "dim_staff": ["staff_key", "position", "active"],
    "fact_admissions": [
        "student_key", "class_key", "date_key", "admission_date",
        "current_standard", "admission_status", "active"
    ],
    "fact_attendance": [
        "attendance_key", "student_key", "class_key", "teacher_key",
        "date_key", "attendance_date", "attendance_status"
    ],
    "fact_exam_results": [
        "result_key", "assessment_source", "assessment_key", "assessment_name",
        "student_key", "class_key", "subject_key", "teacher_key", "date_key",
        "assessment_date", "marks_obtained", "maximum_marks", "score_percent",
        "absent", "attempt_status", "passed"
    ],
    "fact_teacher_assignments": [
        "assignment_key", "teacher_key", "class_key", "subject_key"
    ],
    "fact_teacher_availability": [
        "leave_key", "teacher_key", "start_date", "end_date", "leave_days",
        "leave_status"
    ],
    "fact_teacher_workload": [
        "teacher_key", "schedule_state", "assignment_count",
        "scheduled_period_count"
    ],
    "fact_timetable": [
        "timetable_key", "schedule_state", "draft_key", "class_key",
        "teacher_key", "subject_key", "day", "period_number", "start_time",
        "end_time", "room"
    ],
    "fact_timetable_conflicts": [
        "conflict_key", "conflict_type", "day", "left_schedule_state",
        "left_class_key", "left_teacher_key", "left_period_number",
        "right_schedule_state", "right_class_key", "right_teacher_key",
        "right_period_number", "room"
    ],
    "fact_timetable_quality": [
        "draft_key", "class_key", "created_date", "draft_status",
        "required_periods", "generated_periods", "completeness_percent",
        "preference_percent", "quality_score"
    ],
    "agg_google_sheets_sync": [
        "record_type", "batch_status", "batch_count", "row_count",
        "applied_count"
    ],
    "agg_google_sheets_exports": [
        "record_type", "export_status", "export_count", "attempt_count"
    ],
    "agg_kafka_processing": [
        "event_type", "processing_status", "event_count", "attempt_count"
    ],
    "fact_ml_training": [
        "training_job_key", "created_at", "completed_at", "job_status",
        "row_count", "pass_fail_accuracy", "pass_fail_balanced_accuracy",
        "final_percentage_mae", "final_percentage_r2"
    ]
}

DATASET_DESCRIPTIONS = {
    "dim_date": "Calendar dimension; date_key is YYYYMMDD.",
    "dim_class": "Class/division dimension and current enrollment counts.",
    "dim_subject": "Subject dimension.",
    "dim_student": "Student dimension using a keyed pseudonymous student key; no direct identifiers.",
    "dim_teacher": "Teacher dimension using a keyed pseudonymous teacher key.",
    "dim_staff": "Staff dimension using a keyed pseudonymous staff key.",
    "fact_admissions": "One row per current student admission record; guardian and fee fields are excluded.",
    "fact_attendance": "One row per attendance record.",
    "fact_exam_results": "One row per recorded mark or submitted online exam attempt; answer text is excluded.",
    "fact_teacher_assignments": "One row per teacher/class/subject assignment.",
    "fact_teacher_availability": "Approved teacher leave date ranges only; reasons and notes are excluded.",
    "fact_teacher_workload": "Teacher counts by current live schedule or draft schedule state.",
    "fact_timetable": "Live timetable periods and reviewable AI draft periods.",
    "fact_timetable_conflicts": "Pairwise teacher or named-room time overlaps in exported schedules.",
    "fact_timetable_quality": "AI timetable draft completeness and preference/quality scores.",
    "agg_google_sheets_sync": "Aggregated import batch status; spreadsheet IDs and row contents are excluded.",
    "agg_google_sheets_exports": "Aggregated export queue status; record IDs and error text are excluded.",
    "agg_kafka_processing": "Aggregated outbox delivery status; payloads and entity IDs are excluded.",
    "fact_ml_training": "Training-job outcomes and allow-listed evaluation metrics only."
}


class ReportingExportError(ValueError):
    """Raised when an extract contains values that cannot be exported safely."""


def safe_spreadsheet_cell(value):
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + value
    return value


def build_csv_export(dataset_name, rows):
    if dataset_name not in DATASET_COLUMNS:
        raise ReportingExportError("Unknown reporting dataset.")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=DATASET_COLUMNS[dataset_name],
        extrasaction="raise",
        lineterminator="\r\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({
            key: safe_spreadsheet_cell(value)
            for key, value in row.items()
        })
    return output.getvalue()


def build_excel_export(datasets):
    from openpyxl import Workbook

    for name, rows in datasets.items():
        if len(rows) + 1 > 1_048_576:
            raise ReportingExportError(
                f"Dataset {name} exceeds Excel's worksheet row limit."
            )

    workbook = Workbook(write_only=True)
    for name, rows in datasets.items():
        sheet = workbook.create_sheet(title=name[:31])
        sheet.append(DATASET_COLUMNS[name])
        for row in rows:
            sheet.append([
                safe_spreadsheet_cell(row.get(column))
                for column in DATASET_COLUMNS[name]
            ])
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def _date_text(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _datetime_text(value):
    return value.isoformat() if value is not None else ""


def _date_key(value):
    text = _date_text(value)
    return int(text.replace("-", "")) if text else None


def _pseudonymous_key(secret_key, entity_type, entity_id):
    if not secret_key:
        raise ReportingExportError(
            "A stable Flask SECRET_KEY is required to export pseudonymous keys."
        )
    digest = hmac.new(
        secret_key.encode("utf-8"),
        f"{entity_type}:{entity_id}".encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return f"{entity_type}_{digest[:32]}"


def _time_minutes(value):
    try:
        hour, minute = str(value).split(":", 1)
        hour, minute = int(hour), int(minute[:2])
    except (TypeError, ValueError):
        return None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return hour * 60 + minute


def _safe_metrics(metrics_json):
    try:
        metrics = json.loads(metrics_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(metrics, dict):
        return {}
    models = metrics.get("metrics", metrics)
    if not isinstance(models, dict):
        return {}
    models = models.get("models", models)
    if not isinstance(models, dict):
        return {}
    classifier = models.get("pass_fail", {})
    regressor = models.get("final_percentage", {})
    if not isinstance(classifier, dict):
        classifier = {}
    if not isinstance(regressor, dict):
        regressor = {}
    return {
        "pass_fail_accuracy": classifier.get("accuracy"),
        "pass_fail_balanced_accuracy": classifier.get("balanced_accuracy"),
        "final_percentage_mae": regressor.get("mae_percentage_points"),
        "final_percentage_r2": regressor.get("r2")
    }


def build_powerbi_datasets(models, secret_key):
    """Return deterministic tabular extracts without direct student PII."""
    SchoolClass = models["SchoolClass"]
    Subject = models["Subject"]
    Student = models["Student"]
    Teacher = models["Teacher"]
    User = models["User"]
    Staff = models["Staff"]
    Attendance = models["Attendance"]
    Mark = models["Mark"]
    Exam = models["Exam"]
    OnlineExam = models["OnlineExam"]
    StudentExamAttempt = models["StudentExamAttempt"]
    TeacherAssignment = models["TeacherAssignment"]
    LeaveRequest = models["LeaveRequest"]
    Timetable = models["Timetable"]
    TimetableDraft = models["TimetableDraft"]
    TimetableDraftPeriod = models["TimetableDraftPeriod"]
    GoogleSheetSyncBatch = models["GoogleSheetSyncBatch"]
    GoogleSheetExport = models["GoogleSheetExport"]
    KafkaOutboxEvent = models["KafkaOutboxEvent"]
    StudentModelTrainingJob = models["StudentModelTrainingJob"]

    classes = SchoolClass.query.order_by(SchoolClass.id).all()
    subjects = Subject.query.order_by(Subject.id).all()
    students = Student.query.order_by(Student.id).all()
    teachers = Teacher.query.order_by(Teacher.id).all()
    school_exams = {
        record.id: record
        for record in Exam.query.all()
    }
    online_exams = {
        record.id: record
        for record in OnlineExam.query.all()
    }
    users = {
        user.id: user
        for user in User.query.all()
    }
    staff = Staff.query.order_by(Staff.id).all()
    class_by_id = {record.id: record for record in classes}
    subject_by_id = {record.id: record for record in subjects}
    student_by_id = {record.id: record for record in students}
    teacher_by_id = {record.id: record for record in teachers}
    student_key = {
        record.id: _pseudonymous_key(secret_key, "student", record.id)
        for record in students
    }
    teacher_key = {
        record.id: _pseudonymous_key(secret_key, "teacher", record.id)
        for record in teachers
    }
    staff_key = {
        record.id: _pseudonymous_key(secret_key, "staff", record.id)
        for record in staff
    }
    enrollment_count = Counter(
        student.class_id for student in students if student.active
    )

    datasets = {
        name: []
        for name in DATASET_COLUMNS
    }
    date_values = set()

    for school_class in classes:
        datasets["dim_class"].append({
            "class_key": school_class.id,
            "standard": school_class.standard,
            "stream": school_class.stream,
            "division": school_class.division,
            "academic_year": school_class.academic_year,
            "capacity": school_class.capacity,
            "active": bool(school_class.active),
            "enrollment_count": enrollment_count[school_class.id]
        })
    for subject in subjects:
        datasets["dim_subject"].append({
            "subject_key": subject.id,
            "subject_code": subject.code,
            "subject_name": subject.name
        })
    for student in students:
        datasets["dim_student"].append({
            "student_key": student_key[student.id],
            "class_key": student.class_id,
            "current_standard": student.current_standard,
            "active": bool(student.active),
            "admission_status": student.admission_status
        })
        admission_date = _date_text(student.admission_date)
        if admission_date:
            date_values.add(admission_date)
        datasets["fact_admissions"].append({
            "student_key": student_key[student.id],
            "class_key": student.class_id,
            "date_key": _date_key(student.admission_date),
            "admission_date": admission_date,
            "current_standard": student.current_standard,
            "admission_status": student.admission_status,
            "active": bool(student.active)
        })
    for teacher in teachers:
        user = users.get(teacher.user_id)
        datasets["dim_teacher"].append({
            "teacher_key": teacher_key[teacher.id],
            "active": bool(user.active) if user else False
        })
    for staff_member in staff:
        datasets["dim_staff"].append({
            "staff_key": staff_key[staff_member.id],
            "position": staff_member.position,
            "active": bool(staff_member.active)
        })

    for record in Attendance.query.order_by(Attendance.id).all():
        student = student_by_id.get(record.student_id)
        if student is None:
            continue
        day = _date_text(record.attendance_date)
        if day:
            date_values.add(day)
        datasets["fact_attendance"].append({
            "attendance_key": record.id,
            "student_key": student_key[student.id],
            "class_key": student.class_id,
            "teacher_key": teacher_key.get(record.teacher_id, ""),
            "date_key": _date_key(record.attendance_date),
            "attendance_date": day,
            "attendance_status": record.status
        })

    for mark in Mark.query.order_by(Mark.id).all():
        student = student_by_id.get(mark.student_id)
        if student is None:
            continue
        exam = school_exams.get(mark.exam_id)
        subject = subject_by_id.get(mark.subject_id)
        mark_date = exam.exam_date if exam and exam.exam_date else mark.created_at
        date_values.add(_date_text(mark_date)) if mark_date else None
        score_percent = (
            round(mark.marks_obtained / mark.maximum_marks * 100, 2)
            if mark.maximum_marks and mark.maximum_marks > 0 and not mark.absent
            else None
        )
        datasets["fact_exam_results"].append({
            "result_key": f"mark_{mark.id}",
            "assessment_source": "school_mark",
            "assessment_key": mark.exam_id,
            "assessment_name": exam.name if exam else "",
            "student_key": student_key[student.id],
            "class_key": student.class_id,
            "subject_key": mark.subject_id,
            "teacher_key": teacher_key.get(mark.teacher_id, ""),
            "date_key": _date_key(mark_date),
            "assessment_date": _date_text(mark_date),
            "marks_obtained": mark.marks_obtained if not mark.absent else None,
            "maximum_marks": mark.maximum_marks,
            "score_percent": score_percent,
            "absent": bool(mark.absent),
            "attempt_status": "",
            "passed": None
        })

    for attempt in StudentExamAttempt.query.order_by(StudentExamAttempt.id).all():
        student = student_by_id.get(attempt.student_id)
        exam = online_exams.get(attempt.exam_id)
        if student is None or exam is None:
            continue
        assessment_day = attempt.submitted_at or attempt.started_at
        if assessment_day:
            date_values.add(_date_text(assessment_day))
        score_percent = (
            round(attempt.score / exam.total_marks * 100, 2)
            if exam.total_marks > 0
            else None
        )
        passed = (
            score_percent >= exam.passing_percentage
            if score_percent is not None and attempt.status == "Submitted"
            else None
        )
        datasets["fact_exam_results"].append({
            "result_key": f"online_{attempt.id}",
            "assessment_source": "online_exam",
            "assessment_key": exam.id,
            "assessment_name": exam.title,
            "student_key": student_key[student.id],
            "class_key": exam.class_id,
            "subject_key": exam.subject_id,
            "teacher_key": teacher_key.get(exam.teacher_id, ""),
            "date_key": _date_key(assessment_day),
            "assessment_date": _date_text(assessment_day),
            "marks_obtained": attempt.score,
            "maximum_marks": exam.total_marks,
            "score_percent": score_percent,
            "absent": False,
            "attempt_status": attempt.status,
            "passed": passed
        })

    assignments_by_teacher = Counter()
    for assignment in TeacherAssignment.query.order_by(TeacherAssignment.id).all():
        if assignment.teacher_id not in teacher_key:
            continue
        assignments_by_teacher[assignment.teacher_id] += 1
        datasets["fact_teacher_assignments"].append({
            "assignment_key": assignment.id,
            "teacher_key": teacher_key[assignment.teacher_id],
            "class_key": assignment.class_id,
            "subject_key": assignment.subject_id
        })

    for leave in (
        LeaveRequest.query
        .filter_by(requester_type="teacher", status="Approved")
        .order_by(LeaveRequest.id)
        .all()
    ):
        if leave.teacher_id not in teacher_key:
            continue
        days = (leave.end_date - leave.start_date).days + 1
        datasets["fact_teacher_availability"].append({
            "leave_key": leave.id,
            "teacher_key": teacher_key[leave.teacher_id],
            "start_date": _date_text(leave.start_date),
            "end_date": _date_text(leave.end_date),
            "leave_days": days,
            "leave_status": leave.status
        })

    timetable_entries = []
    for period in Timetable.query.order_by(Timetable.id).all():
        timetable_entries.append({
            "timetable_key": f"live_{period.id}",
            "schedule_state": "Live",
            "draft_key": "",
            "class_key": period.class_id,
            "teacher_id": period.teacher_id,
            "teacher_key": teacher_key.get(period.teacher_id, ""),
            "subject_key": period.subject_id,
            "day": period.day,
            "period_number": period.period_number,
            "start_time": period.start_time,
            "end_time": period.end_time,
            "room": period.room or ""
        })
    draft_by_id = {
        draft.id: draft
        for draft in TimetableDraft.query.all()
    }
    for period in TimetableDraftPeriod.query.order_by(TimetableDraftPeriod.id).all():
        draft = draft_by_id.get(period.draft_id)
        if draft is None or draft.status != "Draft":
            continue
        timetable_entries.append({
            "timetable_key": f"draft_{period.id}",
            "schedule_state": "Draft",
            "draft_key": draft.id,
            "class_key": period.class_id,
            "teacher_id": period.teacher_id,
            "teacher_key": teacher_key.get(period.teacher_id, ""),
            "subject_key": period.subject_id,
            "day": period.day,
            "period_number": period.period_number,
            "start_time": period.start_time,
            "end_time": period.end_time,
            "room": period.room or ""
        })
    for entry in timetable_entries:
        datasets["fact_timetable"].append({
            key: value
            for key, value in entry.items()
            if key != "teacher_id"
        })
    for state in ("Live", "Draft"):
        state_entries = [
            entry for entry in timetable_entries
            if entry["schedule_state"] == state
        ]
        periods_by_teacher = Counter(
            entry["teacher_id"] for entry in state_entries
        )
        for teacher in teachers:
            datasets["fact_teacher_workload"].append({
                "teacher_key": teacher_key[teacher.id],
                "schedule_state": state,
                "assignment_count": assignments_by_teacher[teacher.id],
                "scheduled_period_count": periods_by_teacher[teacher.id]
            })

    conflicts = []
    entries_by_day = defaultdict(list)
    for entry in timetable_entries:
        entries_by_day[entry["day"]].append(entry)
    for day, entries in entries_by_day.items():
        for index, left in enumerate(entries):
            left_start = _time_minutes(left["start_time"])
            left_end = _time_minutes(left["end_time"])
            if left_start is None or left_end is None or left_end <= left_start:
                continue
            for right in entries[index + 1:]:
                if left["class_key"] == right["class_key"]:
                    continue
                right_start = _time_minutes(right["start_time"])
                right_end = _time_minutes(right["end_time"])
                if (
                    right_start is None
                    or right_end is None
                    or right_end <= right_start
                    or max(left_start, right_start) >= min(left_end, right_end)
                ):
                    continue
                conflict_type = ""
                room = ""
                if (
                    left["teacher_id"] == right["teacher_id"]
                    and left["teacher_id"] is not None
                ):
                    conflict_type = "teacher_overlap"
                elif (
                    left["room"]
                    and right["room"]
                    and left["room"].strip().casefold()
                    == right["room"].strip().casefold()
                ):
                    conflict_type = "room_overlap"
                    room = left["room"]
                if not conflict_type:
                    continue
                conflicts.append({
                    "conflict_key": f"conflict_{len(conflicts) + 1}",
                    "conflict_type": conflict_type,
                    "day": day,
                    "left_schedule_state": left["schedule_state"],
                    "left_class_key": left["class_key"],
                    "left_teacher_key": left["teacher_key"],
                    "left_period_number": left["period_number"],
                    "right_schedule_state": right["schedule_state"],
                    "right_class_key": right["class_key"],
                    "right_teacher_key": right["teacher_key"],
                    "right_period_number": right["period_number"],
                    "room": room
                })
    datasets["fact_timetable_conflicts"] = conflicts

    for draft in sorted(draft_by_id.values(), key=lambda item: item.id):
        if draft.status != "Draft":
            continue
        created_date = _date_text(draft.created_at)
        if created_date:
            date_values.add(created_date)
        completeness = (
            round(draft.generated_periods / draft.required_periods * 100, 2)
            if draft.required_periods > 0
            else 0
        )
        datasets["fact_timetable_quality"].append({
            "draft_key": draft.id,
            "class_key": draft.class_id,
            "created_date": created_date,
            "draft_status": draft.status,
            "required_periods": draft.required_periods,
            "generated_periods": draft.generated_periods,
            "completeness_percent": completeness,
            "preference_percent": draft.preference_percentage,
            "quality_score": draft.quality_score
        })

    sheet_sync_groups = defaultdict(lambda: [0, 0, 0])
    for batch in GoogleSheetSyncBatch.query.all():
        group = sheet_sync_groups[(batch.record_type, batch.status)]
        group[0] += 1
        group[1] += batch.row_count
        group[2] += batch.applied_count
    datasets["agg_google_sheets_sync"] = [
        {
            "record_type": record_type,
            "batch_status": status,
            "batch_count": counts[0],
            "row_count": counts[1],
            "applied_count": counts[2]
        }
        for (record_type, status), counts in sorted(sheet_sync_groups.items())
    ]

    export_groups = defaultdict(lambda: [0, 0])
    for export in GoogleSheetExport.query.all():
        status = "Exported" if export.exported_at else (
            "Retry scheduled" if export.last_error else "Pending"
        )
        group = export_groups[(export.record_type, status)]
        group[0] += 1
        group[1] += export.attempts
    datasets["agg_google_sheets_exports"] = [
        {
            "record_type": record_type,
            "export_status": status,
            "export_count": values[0],
            "attempt_count": values[1]
        }
        for (record_type, status), values in sorted(export_groups.items())
    ]

    kafka_groups = defaultdict(lambda: [0, 0])
    for event in KafkaOutboxEvent.query.all():
        status = (
            "Published" if event.published_at else
            "Failed" if event.failed_at else
            "Pending"
        )
        group = kafka_groups[(event.event_type, status)]
        group[0] += 1
        group[1] += event.attempts
    datasets["agg_kafka_processing"] = [
        {
            "event_type": event_type,
            "processing_status": status,
            "event_count": values[0],
            "attempt_count": values[1]
        }
        for (event_type, status), values in sorted(kafka_groups.items())
    ]

    for job in StudentModelTrainingJob.query.order_by(
        StudentModelTrainingJob.id
    ).all():
        metrics = _safe_metrics(job.metrics_json)
        datasets["fact_ml_training"].append({
            "training_job_key": _pseudonymous_key(
                secret_key,
                "training",
                job.id
            ),
            "created_at": _datetime_text(job.created_at),
            "completed_at": _datetime_text(job.completed_at),
            "job_status": job.status,
            "row_count": job.row_count,
            "pass_fail_accuracy": metrics.get("pass_fail_accuracy"),
            "pass_fail_balanced_accuracy": metrics.get(
                "pass_fail_balanced_accuracy"
            ),
            "final_percentage_mae": metrics.get("final_percentage_mae"),
            "final_percentage_r2": metrics.get("final_percentage_r2")
        })

    datasets["dim_date"] = [
        {
            "date_key": int(value.replace("-", "")),
            "date": value,
            "year": int(value[:4]),
            "quarter": (int(value[5:7]) - 1) // 3 + 1,
            "month": int(value[5:7]),
            "day": int(value[8:10]),
            "weekday": date.fromisoformat(value).strftime("%A")
        }
        for value in sorted(date_values)
    ]

    for name, rows in datasets.items():
        columns = DATASET_COLUMNS[name]
        for row in rows:
            unexpected = set(row) - set(columns)
            if unexpected:
                raise ReportingExportError(
                    f"Dataset {name} contains unexpected columns."
                )
        datasets[name] = [
            {column: row.get(column) for column in columns}
            for row in rows
        ]
    return datasets
