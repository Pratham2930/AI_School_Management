import csv
import io
import json
import inspect
import os
import tempfile
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

import app as school_app


class GoogleSheetSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_app = Flask("isolated-google-sheet-sync-tests")
        self.test_app.config.update(
            SECRET_KEY="isolated-sync-tests",
            SQLALCHEMY_DATABASE_URI=(
                "sqlite:///"
                + os.path.join(self.temp_dir.name, "sheet-sync-tests.db")
            ),
            SQLALCHEMY_TRACK_MODIFICATIONS=False
        )
        self.test_app.add_url_rule(
            "/admin/google-sheets-sync",
            endpoint="admin_google_sheets_sync",
            view_func=lambda: ""
        )
        school_app.db.init_app(self.test_app)
        with self.test_app.app_context():
            school_app.db.create_all()
            self.admin = school_app.User(
                name="Test Admin",
                username="sheet-sync-admin",
                password="not-a-real-password",
                role="admin",
                active=True
            )
            self.school_class = school_app.SchoolClass(
                standard=6,
                stream="",
                division="A",
                academic_year="2026-27",
                capacity=30,
                active=True
            )
            school_app.db.session.add_all([self.admin, self.school_class])
            school_app.db.session.commit()
            self.admin_id = self.admin.id
            self.class_id = self.school_class.id

    def tearDown(self):
        with self.test_app.app_context():
            school_app.db.session.remove()
            school_app.db.drop_all()
            school_app.db.engine.dispose()
        self.temp_dir.cleanup()

    @staticmethod
    def csv_data(headers, rows):
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        return buffer.getvalue().encode("utf-8")

    def test_admission_preview_validates_stable_id_and_class(self):
        headers = [
            "admission_number", "name", "current_standard", "division",
            "academic_year", "previous_percentage", "guardian_name",
            "guardian_relationship", "guardian_phone"
        ]
        data = self.csv_data(headers, [[
            "ADM-2026-9001", "Student One", "6", "A", "2026-27", "82.5",
            "Parent One", "Parent", "9876543210"
        ]])
        with self.test_app.app_context(), patch.object(
            school_app,
            "_google_sheet_training_csv",
            return_value=data
        ):
            rows = school_app._preview_google_sheet_sync(
                "admissions",
                "a" * 30,
                "Admissions!A1:I2"
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stable_id"], "ADM-2026-9001")
        self.assertEqual(rows[0]["action"], "Create")
        self.assertEqual(rows[0]["payload"]["class_id"], self.class_id)
        self.assertEqual(rows[0]["errors"], [])

    def test_duplicate_sheet_ids_block_preview_approval(self):
        data = self.csv_data(
            ["employee_id", "name", "position"],
            [["STF-100", "First Person", "Office"], ["STF-100", "Second Person", "Office"]]
        )
        with self.test_app.app_context(), patch.object(
            school_app,
            "_google_sheet_training_csv",
            return_value=data
        ):
            rows = school_app._preview_google_sheet_sync(
                "staff",
                "b" * 30,
                "Staff!A1:C3"
            )

        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["errors"] for row in rows))
        self.assertTrue(all(
            "unique within the sheet" in row["errors"][0]
            for row in rows
        ))

    def test_staff_approval_applies_one_upsert_and_outbox_event(self):
        data = self.csv_data(
            ["employee_id", "name", "position", "phone"],
            [["STF-100", "Office Manager", "Office", "555-0100"]]
        )
        with self.test_app.app_context(), patch.object(
            school_app,
            "_google_sheet_training_csv",
            return_value=data
        ), patch.object(school_app, "queue_kafka_event") as queue_event:
            preview_rows = school_app._preview_google_sheet_sync(
                "staff",
                "c" * 30,
                "Staff!A1:D2"
            )
            batch = school_app.GoogleSheetSyncBatch(
                id="test-batch-staff",
                record_type="staff",
                spreadsheet_id="c" * 30,
                sheet_range="Staff!A1:D2",
                row_count=1,
                created_by=self.admin_id
            )
            school_app.db.session.add(batch)
            row = school_app.GoogleSheetSyncRow(
                batch_id=batch.id,
                row_number=preview_rows[0]["row_number"],
                stable_id=preview_rows[0]["stable_id"],
                action=preview_rows[0]["action"],
                payload_json=json.dumps(preview_rows[0]["payload"]),
                errors_json=json.dumps(preview_rows[0]["errors"])
            )
            school_app.db.session.add(row)
            school_app.db.session.commit()

            target_id, credentials = school_app._apply_google_sheet_sync_row(
                "staff",
                row,
                self.admin_id
            )
            school_app.db.session.commit()
            staff = school_app.db.session.get(school_app.Staff, target_id)

        self.assertIsNone(credentials)
        self.assertEqual(staff.employee_id, "STF-100")
        self.assertEqual(staff.name, "Office Manager")
        self.assertTrue(staff.active)
        queue_event.assert_called_once()
        self.assertEqual(
            queue_event.call_args.kwargs["event_type"],
            "staff.profile.imported"
        )

    def test_admission_creation_keeps_pending_status_and_links_allocation(self):
        data = self.csv_data(
            [
                "admission_number", "name", "current_standard", "division",
                "academic_year", "previous_percentage", "guardian_name",
                "guardian_relationship", "guardian_email"
            ],
            [[
                "ADM-2026-9002", "Student Two", "6", "A", "2026-27", "76",
                "Parent Two", "Parent", "parent@example.test"
            ]]
        )
        with self.test_app.app_context(), patch.object(
            school_app,
            "_google_sheet_training_csv",
            return_value=data
        ), patch.object(school_app, "queue_kafka_event") as queue_event:
            preview = school_app._preview_google_sheet_sync(
                "admissions",
                "d" * 30,
                "Admissions!A1:I2"
            )[0]
            row = school_app.GoogleSheetSyncRow(
                batch_id="test-batch-admission",
                row_number=preview["row_number"],
                stable_id=preview["stable_id"],
                action=preview["action"],
                payload_json=json.dumps(preview["payload"]),
                errors_json=json.dumps(preview["errors"])
            )
            target_id, _credentials = school_app._apply_google_sheet_sync_row(
                "admissions",
                row,
                self.admin_id
            )
            school_app.db.session.commit()
            student = school_app.db.session.get(school_app.Student, target_id)
            allocation = school_app.AdmissionAllocation.query.filter_by(
                student_id=target_id
            ).one()

        self.assertEqual(student.admission_number, "ADM-2026-9002")
        self.assertEqual(student.admission_status, "Pending")
        self.assertFalse(student.active)
        self.assertEqual(student.admission_date, date.today())
        self.assertEqual(allocation.guardian_email, "parent@example.test")
        self.assertEqual(allocation.final_class_id, self.class_id)
        self.assertEqual(queue_event.call_args.kwargs["event_type"], "student.admission.imported")

    def test_teacher_import_creates_account_with_generated_temporary_password(self):
        data = self.csv_data(
            ["employee_id", "name", "email", "phone", "qualification"],
            [["TCH-SHEET-100", "Teacher One", "teacher@example.test", "9876543210", "B.Ed"]]
        )
        with self.test_app.app_context(), patch.object(
            school_app,
            "_google_sheet_training_csv",
            return_value=data
        ), patch.object(school_app, "queue_kafka_event"):
            preview = school_app._preview_google_sheet_sync(
                "teachers",
                "e" * 30,
                "Teachers!A1:E2"
            )[0]
            self.assertEqual(preview["errors"], [])
            row = school_app.GoogleSheetSyncRow(
                batch_id="test-batch-teacher",
                row_number=preview["row_number"],
                stable_id=preview["stable_id"],
                action=preview["action"],
                payload_json=json.dumps(preview["payload"]),
                errors_json=json.dumps(preview["errors"])
            )
            target_id, credentials = school_app._apply_google_sheet_sync_row(
                "teachers",
                row,
                self.admin_id
            )
            school_app.db.session.commit()
            teacher = school_app.db.session.get(school_app.Teacher, target_id)
            user = school_app.db.session.get(school_app.User, teacher.user_id)

        self.assertEqual(teacher.employee_id, "TCH-SHEET-100")
        self.assertEqual(teacher.qualification, "B.Ed")
        self.assertEqual(user.username, "TCH-SHEET-100")
        self.assertEqual(user.role, "teacher")
        self.assertTrue(user.must_change_password)
        self.assertNotEqual(user.password, credentials["password"])
        self.assertEqual(len(credentials["password"]), 10)

    def test_approval_route_requires_explicit_confirmation_and_commits_batch(self):
        data = self.csv_data(
            ["employee_id", "name", "position"],
            [["STF-APPROVE-1", "Approved Person", "Secretary"]]
        )
        with self.test_app.app_context(), patch.object(
            school_app,
            "_google_sheet_training_csv",
            return_value=data
        ), patch.object(school_app, "queue_kafka_event"):
            preview = school_app._preview_google_sheet_sync(
                "staff",
                "f" * 30,
                "Staff!A1:C2"
            )[0]
            batch = school_app.GoogleSheetSyncBatch(
                id="test-batch-approval",
                record_type="staff",
                spreadsheet_id="f" * 30,
                sheet_range="Staff!A1:C2",
                row_count=1,
                created_by=self.admin_id
            )
            row = school_app.GoogleSheetSyncRow(
                batch_id=batch.id,
                row_number=preview["row_number"],
                stable_id=preview["stable_id"],
                action=preview["action"],
                payload_json=json.dumps(preview["payload"]),
                errors_json=json.dumps(preview["errors"])
            )
            school_app.db.session.add_all([batch, row])
            school_app.db.session.commit()

            route = inspect.unwrap(school_app.approve_google_sheets_sync)
            with self.test_app.test_request_context(
                "/admin/google-sheets-sync/test-batch-approval/approve",
                method="POST",
                data={"confirm_approval": "yes"}
            ), patch.object(
                school_app,
                "current_user",
                SimpleNamespace(id=self.admin_id)
            ):
                response = route(batch.id)

            self.assertEqual(response.status_code, 302)
            self.assertEqual(batch.status, "Approved")
            self.assertEqual(batch.applied_count, 1)
            self.assertEqual(
                school_app.Staff.query.filter_by(
                    employee_id="STF-APPROVE-1"
                ).count(),
                1
            )

    def test_failed_batch_application_rolls_back_every_row(self):
        data = self.csv_data(
            ["employee_id", "name", "position"],
            [
                ["STF-ROLLBACK-1", "First Person", "Office"],
                ["STF-ROLLBACK-2", "Second Person", "Office"]
            ]
        )
        with self.test_app.app_context(), patch.object(
            school_app,
            "_google_sheet_training_csv",
            return_value=data
        ), patch.object(school_app, "queue_kafka_event"):
            previews = school_app._preview_google_sheet_sync(
                "staff",
                "g" * 30,
                "Staff!A1:C3"
            )
            batch = school_app.GoogleSheetSyncBatch(
                id="test-batch-rollback",
                record_type="staff",
                spreadsheet_id="g" * 30,
                sheet_range="Staff!A1:C3",
                row_count=2,
                created_by=self.admin_id
            )
            rows = [
                school_app.GoogleSheetSyncRow(
                    batch_id=batch.id,
                    row_number=item["row_number"],
                    stable_id=item["stable_id"],
                    action=item["action"],
                    payload_json=json.dumps(item["payload"]),
                    errors_json=json.dumps(item["errors"])
                )
                for item in previews
            ]
            school_app.db.session.add_all([batch, *rows])
            school_app.db.session.commit()

            apply_row = school_app._apply_google_sheet_sync_row

            def fail_on_second_row(record_type, row, admin_id):
                if row.stable_id == "STF-ROLLBACK-2":
                    raise RuntimeError("simulated second-row failure")
                return apply_row(record_type, row, admin_id)

            route = inspect.unwrap(school_app.approve_google_sheets_sync)
            with self.test_app.test_request_context(
                "/admin/google-sheets-sync/test-batch-rollback/approve",
                method="POST",
                data={"confirm_approval": "yes"}
            ), patch.object(
                school_app,
                "current_user",
                SimpleNamespace(id=self.admin_id)
            ), patch.object(
                school_app,
                "_apply_google_sheet_sync_row",
                side_effect=fail_on_second_row
            ):
                response = route(batch.id)

            self.assertEqual(response.status_code, 302)
            self.assertEqual(
                school_app.Staff.query.filter(
                    school_app.Staff.employee_id.in_(
                        ["STF-ROLLBACK-1", "STF-ROLLBACK-2"]
                    )
                ).count(),
                0
            )
            persisted_batch = school_app.db.session.get(
                school_app.GoogleSheetSyncBatch,
                batch.id
            )
            self.assertEqual(persisted_batch.status, "Needs review")


if __name__ == "__main__":
    unittest.main()
