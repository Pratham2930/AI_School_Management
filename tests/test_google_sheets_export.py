import os
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

import app as school_app
from google_sheets_export_worker import (
    EXPORT_HEADERS,
    _upsert_record,
    _write_values,
    process_next_export
)


class GoogleSheetsExportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_app = Flask("isolated-google-sheets-export-tests")
        self.test_app.config.update(
            SQLALCHEMY_DATABASE_URI=(
                "sqlite:///"
                + os.path.join(self.temp_dir.name, "sheets-export-tests.db")
            ),
            SQLALCHEMY_TRACK_MODIFICATIONS=False
        )
        school_app.db.init_app(self.test_app)
        with self.test_app.app_context():
            school_app.GoogleSheetExport.__table__.create(
                bind=school_app.db.engine,
                checkfirst=True
            )

    def tearDown(self):
        with self.test_app.app_context():
            school_app.db.session.remove()
            school_app.GoogleSheetExport.__table__.drop(
                bind=school_app.db.engine,
                checkfirst=True
            )
            school_app.db.engine.dispose()
        self.temp_dir.cleanup()

    def test_export_queue_can_be_committed_or_rolled_back_with_record(self):
        with self.test_app.app_context():
            school_app.queue_google_sheet_export("admissions", 42)
            school_app.db.session.rollback()
            self.assertEqual(school_app.GoogleSheetExport.query.count(), 0)

            school_app.queue_google_sheet_export("admissions", 42)
            school_app.db.session.commit()
            queued = school_app.GoogleSheetExport.query.one()
            self.assertEqual(queued.record_type, "admissions")
            self.assertEqual(queued.record_id, 42)

    def test_existing_stable_id_updates_existing_google_sheet_row(self):
        spreadsheet_id = "a" * 30
        headers = EXPORT_HEADERS["teachers"]
        existing_values = [headers, ["TCH-2026-0001", "Old Name"]]
        new_values = ["TCH-2026-0001", "New Name", "new@example.com", "123", ""]
        calls = []

        def fake_api_request(method, path, body=None):
            calls.append((method, path, body))
            if method == "GET" and "/values/" in path:
                return {"values": existing_values}
            if method == "GET" and path.startswith("spreadsheets/"):
                return {"sheets": [{"properties": {"title": "Teachers"}}]}
            return {}

        with patch.dict(
            os.environ,
            {"GOOGLE_SHEETS_TEACHERS_SPREADSHEET_ID": spreadsheet_id}
        ), patch(
            "google_sheets_export_worker._api_request",
            side_effect=fake_api_request
        ), patch(
            "google_sheets_export_worker._write_values"
        ) as write_values:
            _upsert_record("teachers", new_values)

        write_values.assert_called_once_with(
            spreadsheet_id,
            "Teachers",
            "'Teachers'!A2:E2",
            [new_values]
        )

    def test_duplicate_stable_ids_block_ambiguous_sheet_update(self):
        headers = EXPORT_HEADERS["admissions"]
        values = [
            headers,
            ["ADM-2026-0001"],
            ["ADM-2026-0001"]
        ]
        with patch.dict(
            os.environ,
            {"GOOGLE_SHEETS_ADMISSIONS_SPREADSHEET_ID": "a" * 30}
        ), patch(
            "google_sheets_export_worker._api_request",
            side_effect=[
                {"sheets": [{"properties": {"title": "Admissions"}}]},
                {"values": values}
            ]
        ):
            with self.assertRaisesRegex(RuntimeError, "duplicate stable ID"):
                _upsert_record("admissions", ["ADM-2026-0001"] + [""] * 18)

    def test_values_api_uses_correct_update_and_append_paths(self):
        spreadsheet_id = "a" * 30
        values = [["TCH-2026-0001", "Teacher"]]
        with patch(
            "google_sheets_export_worker._api_request",
            return_value={}
        ) as api_request:
            _write_values(
                spreadsheet_id,
                "Teachers",
                "'Teachers'!A2:E2",
                values
            )
            update_call = api_request.call_args
            self.assertEqual(update_call.args[0], "PUT")
            self.assertIn("/values/%27Teachers%27%21A2%3AE2?", update_call.args[1])
            self.assertNotIn("%3AE2%3A?", update_call.args[1])

            _write_values(
                spreadsheet_id,
                "Teachers",
                "'Teachers'!A:E",
                values,
                append=True
            )
            append_call = api_request.call_args
            self.assertEqual(append_call.args[0], "POST")
            self.assertIn("/values/%27Teachers%27%21A%3AE:append?", append_call.args[1])
            self.assertIn("insertDataOption=INSERT_ROWS", append_call.args[1])

    def test_failed_export_is_persisted_for_retry_and_success_is_marked(self):
        with self.test_app.app_context():
            school_app.db.session.add(
                school_app.GoogleSheetExport(
                    record_type="teachers",
                    record_id=17
                )
            )
            school_app.db.session.commit()

            with patch(
                "google_sheets_export_worker._export_row",
                return_value=["TCH-2026-0017", "Teacher"]
            ), patch(
                "google_sheets_export_worker._upsert_record",
                side_effect=RuntimeError("Sheets temporarily unavailable")
            ):
                self.assertTrue(process_next_export())

            queued = school_app.GoogleSheetExport.query.one()
            self.assertEqual(queued.attempts, 1)
            self.assertIsNone(queued.exported_at)
            self.assertEqual(queued.last_error, "Sheets temporarily unavailable")
            self.assertIsNotNone(queued.next_attempt_at)

            queued.next_attempt_at = None
            school_app.db.session.commit()
            with patch(
                "google_sheets_export_worker._export_row",
                return_value=["TCH-2026-0017", "Teacher"]
            ), patch(
                "google_sheets_export_worker._upsert_record"
            ) as upsert_record:
                self.assertTrue(process_next_export())

            upsert_record.assert_called_once()
            school_app.db.session.refresh(queued)
            self.assertEqual(queued.attempts, 2)
            self.assertIsNotNone(queued.exported_at)
            self.assertIsNone(queued.last_error)
            self.assertIsNone(queued.next_attempt_at)


if __name__ == "__main__":
    unittest.main()
