import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app import (
    AdmissionAllocation,
    GoogleSheetExport,
    SchoolClass,
    Student,
    Teacher,
    User,
    app,
    db
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
RETRY_BASE_SECONDS = 30
RETRY_MAX_SECONDS = 3600

EXPORT_HEADERS = {
    "admissions": [
        "admission_number", "name", "current_standard", "division",
        "academic_year", "previous_percentage", "guardian_name",
        "guardian_relationship", "stream", "date_of_birth", "gender",
        "phone", "email", "address", "previous_school",
        "previous_standard", "admission_fee", "guardian_phone",
        "guardian_email"
    ],
    "teachers": [
        "employee_id", "name", "email", "phone", "qualification"
    ]
}


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _spreadsheet_id(record_type):
    variable = (
        "GOOGLE_SHEETS_ADMISSIONS_SPREADSHEET_ID"
        if record_type == "admissions"
        else "GOOGLE_SHEETS_TEACHERS_SPREADSHEET_ID"
    )
    spreadsheet_id = os.environ.get(variable, "").strip()
    if not spreadsheet_id or not all(
        character.isalnum() or character in "_-" for character in spreadsheet_id
    ):
        raise RuntimeError(
            f"Set {variable} to the Google spreadsheet ID before starting "
            "the Sheets export worker."
        )
    return spreadsheet_id


def _api_request(method, path, body=None):
    from google.auth import default
    from google.auth.exceptions import GoogleAuthError
    from google.auth.transport.requests import Request

    try:
        credentials, _project_id = default(scopes=[SHEETS_SCOPE])
        credentials.refresh(Request())
    except (GoogleAuthError, OSError) as error:
        raise RuntimeError(
            "Google Sheets credentials are unavailable. Set "
            "GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON file "
            "with Editor access to both configured spreadsheets."
        ) from error

    if not credentials.token:
        raise RuntimeError(
            "Google Sheets credentials did not provide an access token."
        )

    request_data = None
    headers = {"Authorization": "Bearer " + credentials.token}
    if body is not None:
        request_data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    api_request = urllib.request.Request(
        "https://sheets.googleapis.com/v4/" + path,
        data=request_data,
        headers=headers,
        method=method
    )
    try:
        with urllib.request.urlopen(api_request, timeout=30) as response:
            response_body = response.read(10 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        logger.warning("Google Sheets API returned HTTP %s.", error.code)
        if error.code == 403:
            raise RuntimeError(
                "Google Sheets denied write access. Share each spreadsheet "
                "with the configured service-account email as an Editor and "
                "enable the Google Sheets API."
            ) from error
        if error.code == 404:
            raise RuntimeError(
                "A configured Google spreadsheet could not be found."
            ) from error
        raise RuntimeError(
            f"Google Sheets request failed (HTTP {error.code})."
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(
            "Could not connect to Google Sheets. Check network access."
        ) from error

    if len(response_body) > 10 * 1024 * 1024:
        raise RuntimeError("Google Sheets returned a response larger than 10 MB.")
    if not response_body:
        return {}
    try:
        return json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Google Sheets returned an invalid response.") from error


def _quoted_range(tab_name, columns):
    return f"'{tab_name}'!A:{columns}"


def _write_values(spreadsheet_id, tab_name, range_name, values, append=False):
    encoded_range = urllib.parse.quote(range_name, safe="")
    action = ":append" if append else ""
    path = (
        f"spreadsheets/{urllib.parse.quote(spreadsheet_id, safe='')}/values/"
        f"{encoded_range}{action}?valueInputOption=RAW"
    )
    if append:
        path += "&insertDataOption=INSERT_ROWS"
    return _api_request(
        "POST" if append else "PUT",
        path,
        {"majorDimension": "ROWS", "values": values}
    )


def _ensure_tab(spreadsheet_id, tab_name):
    encoded_id = urllib.parse.quote(spreadsheet_id, safe="")
    metadata = _api_request(
        "GET",
        f"spreadsheets/{encoded_id}?fields=sheets.properties.title"
    )
    tab_names = {
        sheet["properties"]["title"]
        for sheet in metadata.get("sheets", [])
        if "properties" in sheet and "title" in sheet["properties"]
    }
    if tab_name not in tab_names:
        _api_request(
            "POST",
            f"spreadsheets/{encoded_id}:batchUpdate",
            {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]}
        )


def _column_name(column_number):
    result = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _export_row(export):
    if export.record_type == "admissions":
        student = db.session.get(Student, export.record_id)
        if student is None:
            raise RuntimeError(
                f"Admission export {export.id} references a missing student."
            )
        school_class = db.session.get(SchoolClass, student.class_id)
        allocation = AdmissionAllocation.query.filter_by(
            student_id=student.id
        ).order_by(AdmissionAllocation.id.desc()).first()
        if school_class is None or allocation is None:
            raise RuntimeError(
                f"Admission export {export.id} is missing its class or "
                "guardian allocation."
            )
        values_by_header = {
            "admission_number": student.admission_number,
            "name": student.name,
            "current_standard": student.current_standard,
            "division": school_class.division,
            "academic_year": school_class.academic_year,
            "previous_percentage": allocation.previous_percentage,
            "guardian_name": allocation.guardian_name,
            "guardian_relationship": allocation.guardian_relationship,
            "stream": school_class.stream,
            "date_of_birth": (
                student.date_of_birth.isoformat()
                if student.date_of_birth else ""
            ),
            "gender": student.gender,
            "phone": student.phone,
            "email": student.email,
            "address": student.address,
            "previous_school": student.previous_school,
            "previous_standard": student.previous_standard,
            "admission_fee": student.admission_fee,
            "guardian_phone": allocation.guardian_phone,
            "guardian_email": allocation.guardian_email
        }
    elif export.record_type == "teachers":
        teacher = db.session.get(Teacher, export.record_id)
        if teacher is None:
            raise RuntimeError(
                f"Teacher export {export.id} references a missing teacher."
            )
        user = db.session.get(User, teacher.user_id)
        if user is None:
            raise RuntimeError(
                f"Teacher export {export.id} references a missing user account."
            )
        values_by_header = {
            "employee_id": teacher.employee_id,
            "name": user.name,
            "email": teacher.email,
            "phone": teacher.phone,
            "qualification": teacher.qualification
        }
    else:
        raise RuntimeError(
            f"Unsupported Google Sheets export type: {export.record_type}."
        )

    return [
        "" if values_by_header[header] is None else values_by_header[header]
        for header in EXPORT_HEADERS[export.record_type]
    ]


def _upsert_record(record_type, row):
    spreadsheet_id = _spreadsheet_id(record_type)
    tab_name = "Admissions" if record_type == "admissions" else "Teachers"
    headers = EXPORT_HEADERS[record_type]
    last_column = _column_name(len(headers))
    _ensure_tab(spreadsheet_id, tab_name)

    range_name = f"'{tab_name}'!A:{last_column}"
    result = _api_request(
        "GET",
        f"spreadsheets/{urllib.parse.quote(spreadsheet_id, safe='')}/values/"
        f"{urllib.parse.quote(range_name, safe='')}?majorDimension=ROWS"
    )
    existing_rows = result.get("values", [])
    if not existing_rows:
        _write_values(
            spreadsheet_id,
            tab_name,
            f"'{tab_name}'!A1:{last_column}1",
            [headers]
        )
        existing_rows = [headers]
    if existing_rows[0] != headers:
        raise RuntimeError(
            f"The {tab_name} tab must use the documented export header row "
            "in the expected column order."
        )

    stable_id = str(row[0])
    matching_rows = [
        row_number
        for row_number, existing_row in enumerate(existing_rows[1:], start=2)
        if existing_row and str(existing_row[0]).strip() == stable_id
    ]
    if len(matching_rows) > 1:
        raise RuntimeError(
            f"The {tab_name} tab contains duplicate stable ID {stable_id}; "
            "resolve duplicates before retrying the export."
        )
    if matching_rows:
        row_number = matching_rows[0]
        target_range = f"'{tab_name}'!A{row_number}:{last_column}{row_number}"
        _write_values(
            spreadsheet_id,
            tab_name,
            target_range,
            [row]
        )
        return

    append_range = _quoted_range(tab_name, last_column)
    _write_values(
        spreadsheet_id,
        tab_name,
        append_range,
        [row],
        append=True
    )


def process_next_export():
    now = _utcnow_naive()
    export = (
        GoogleSheetExport.query
        .filter(
            GoogleSheetExport.exported_at.is_(None),
            (GoogleSheetExport.next_attempt_at.is_(None))
            | (GoogleSheetExport.next_attempt_at <= now)
        )
        .order_by(GoogleSheetExport.id.asc())
        .first()
    )
    if export is None:
        return False

    export_id = export.id
    export.attempts += 1
    db.session.commit()
    try:
        row = _export_row(export)
        _upsert_record(export.record_type, row)
    except Exception as error:
        db.session.rollback()
        failed_export = db.session.get(GoogleSheetExport, export_id)
        if failed_export is None:
            raise RuntimeError(
                f"Google Sheets export {export_id} disappeared after failure."
            ) from error
        failed_export.last_error = str(error)[:2000]
        delay_seconds = min(
            RETRY_BASE_SECONDS * (2 ** min(failed_export.attempts - 1, 10)),
            RETRY_MAX_SECONDS
        )
        failed_export.next_attempt_at = (
            _utcnow_naive() + timedelta(seconds=delay_seconds)
        )
        db.session.commit()
        logger.exception(
            "Google Sheets export %s (%s:%s) failed on attempt %s.",
            export_id,
            failed_export.record_type,
            failed_export.record_id,
            failed_export.attempts
        )
        return True

    completed_export = db.session.get(GoogleSheetExport, export_id)
    if completed_export is None:
        raise RuntimeError(
            f"Google Sheets export {export_id} disappeared after publishing."
        )
    completed_export.exported_at = _utcnow_naive()
    completed_export.next_attempt_at = None
    completed_export.last_error = None
    db.session.commit()
    logger.info(
        "Exported %s record %s to Google Sheets.",
        completed_export.record_type,
        completed_export.record_id
    )
    return True


def run_worker():
    try:
        poll_interval = float(
            os.environ.get("GOOGLE_SHEETS_EXPORT_POLL_SECONDS", "5")
        )
    except ValueError as error:
        raise RuntimeError(
            "GOOGLE_SHEETS_EXPORT_POLL_SECONDS must be a positive number."
        ) from error
    if poll_interval <= 0:
        raise RuntimeError(
            "GOOGLE_SHEETS_EXPORT_POLL_SECONDS must be a positive number."
        )

    _spreadsheet_id("admissions")
    _spreadsheet_id("teachers")
    with app.app_context():
        if not inspect(db.engine).has_table("google_sheet_export"):
            raise RuntimeError(
                "The Google Sheets export table is not initialized. Start "
                "Flask once, then restart the Sheets export worker."
            )

    logger.info("Google Sheets record export worker started.")
    while True:
        try:
            with app.app_context():
                did_work = process_next_export()
        except SQLAlchemyError:
            logger.exception("Database error while exporting records to Sheets.")
            db.session.rollback()
            did_work = False
        except KeyboardInterrupt:
            logger.info("Google Sheets export worker stopping.")
            return
        if not did_work:
            time.sleep(poll_interval)


if __name__ == "__main__":
    run_worker()
