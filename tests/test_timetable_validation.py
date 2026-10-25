import os
import tempfile
import unittest
from types import SimpleNamespace

from flask import Flask

import app as school_app


class TimetableValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_app = Flask("isolated-timetable-validation-tests")
        self.test_app.config.update(
            SQLALCHEMY_DATABASE_URI=(
                "sqlite:///"
                + os.path.join(self.temp_dir.name, "timetable-tests.db")
            ),
            SQLALCHEMY_TRACK_MODIFICATIONS=False
        )
        school_app.db.init_app(self.test_app)
        with self.test_app.app_context():
            school_app.db.create_all()
            self.teacher_user = school_app.User(
                name="Teacher One",
                username="timetable-teacher-1",
                password="test-password",
                role="teacher",
                active=True
            )
            self.other_teacher_user = school_app.User(
                name="Teacher Two",
                username="timetable-teacher-2",
                password="test-password",
                role="teacher",
                active=True
            )
            self.class_one = school_app.SchoolClass(
                standard=6,
                stream="",
                division="A",
                academic_year="2026-27",
                capacity=30,
                active=True
            )
            self.class_two = school_app.SchoolClass(
                standard=6,
                stream="",
                division="B",
                academic_year="2026-27",
                capacity=30,
                active=True
            )
            self.subject = school_app.Subject(
                name="Mathematics",
                code="MATH-6"
            )
            school_app.db.session.add_all([
                self.teacher_user,
                self.other_teacher_user,
                self.class_one,
                self.class_two,
                self.subject
            ])
            school_app.db.session.flush()
            self.teacher = school_app.Teacher(
                employee_id="TCH-TEST-1",
                user_id=self.teacher_user.id
            )
            self.other_teacher = school_app.Teacher(
                employee_id="TCH-TEST-2",
                user_id=self.other_teacher_user.id
            )
            school_app.db.session.add_all([self.teacher, self.other_teacher])
            school_app.db.session.flush()
            self.requirement = school_app.SubjectRequirement(
                class_id=self.class_one.id,
                subject_id=self.subject.id,
                periods_per_week=1,
                max_periods_per_day=1
            )
            self.assignment = school_app.TeacherAssignment(
                class_id=self.class_one.id,
                subject_id=self.subject.id,
                teacher_id=self.teacher.id
            )
            school_app.db.session.add_all([
                self.requirement,
                self.assignment
            ])
            school_app.db.session.commit()
            self.class_one_id = self.class_one.id
            self.class_two_id = self.class_two.id
            self.subject_id = self.subject.id
            self.teacher_id = self.teacher.id
            self.other_teacher_id = self.other_teacher.id
            self.assignment_id = self.assignment.id

    def tearDown(self):
        with self.test_app.app_context():
            school_app.db.session.remove()
            school_app.db.drop_all()
            school_app.db.engine.dispose()
        self.temp_dir.cleanup()

    def make_draft_period(self, **changes):
        values = {
            "class_id": self.class_one_id,
            "teacher_id": self.teacher_id,
            "subject_id": self.subject_id,
            "day": "Monday",
            "period_number": 1,
            "start_time": "09:00",
            "end_time": "09:45",
            "room": "Lab 1"
        }
        values.update(changes)
        return SimpleNamespace(**values)

    def make_draft(self):
        return SimpleNamespace(
            class_id=self.class_one_id,
            required_periods=1,
            generated_periods=1
        )

    def test_valid_complete_draft_passes_publish_checks(self):
        with self.test_app.app_context():
            errors = school_app._validate_timetable_draft_for_publish(
                self.make_draft(),
                [self.make_draft_period()]
            )
        self.assertEqual(errors, [])

    def test_cp_sat_generator_produces_required_weekly_periods(self):
        with self.test_app.app_context():
            school_class = school_app.db.session.get(
                school_app.SchoolClass,
                self.class_one_id
            )
            result = school_app.generate_optimized_timetable(school_class)

        self.assertTrue(
            result["success"],
            result.get("message", str(result))
        )
        self.assertEqual(result["required_periods"], 1)
        self.assertEqual(result["generated_periods"], 1)
        self.assertEqual(len(result["schedule"]), 1)
        self.assertEqual(result["schedule"][0]["subject_id"], self.subject_id)
        self.assertEqual(result["schedule"][0]["teacher_id"], self.teacher_id)

    def test_publish_rejects_removed_teacher_assignment(self):
        with self.test_app.app_context():
            assignment = school_app.db.session.get(
                school_app.TeacherAssignment,
                self.assignment_id
            )
            school_app.db.session.delete(assignment)
            school_app.db.session.commit()
            errors = school_app._validate_timetable_draft_for_publish(
                self.make_draft(),
                [self.make_draft_period()]
            )
        self.assertTrue(any("no longer assigned" in error for error in errors))

    def test_publish_rejects_overlapping_room_booking(self):
        with self.test_app.app_context():
            school_app.db.session.add(school_app.Timetable(
                class_id=self.class_two_id,
                teacher_id=self.other_teacher_id,
                subject_id=self.subject_id,
                day="Monday",
                period_number=1,
                start_time="09:00",
                end_time="09:45",
                room=" lab 1 "
            ))
            school_app.db.session.commit()
            errors = school_app._validate_timetable_draft_for_publish(
                self.make_draft(),
                [self.make_draft_period()]
            )
        self.assertTrue(any("overlapping live booking" in error for error in errors))

    def test_manual_room_check_uses_case_insensitive_time_overlap(self):
        with self.test_app.app_context():
            school_app.db.session.add(school_app.Timetable(
                class_id=self.class_two_id,
                teacher_id=self.other_teacher_id,
                subject_id=self.subject_id,
                day="Tuesday",
                period_number=1,
                start_time="09:00",
                end_time="09:45",
                room="Lab 1"
            ))
            school_app.db.session.commit()
            conflict = school_app._find_timetable_room_conflict(
                "Tuesday",
                "09:30",
                "10:15",
                " lab 1 "
            )
            no_conflict = school_app._find_timetable_room_conflict(
                "Tuesday",
                "09:45",
                "10:30",
                "LAB 1"
            )
        self.assertIsNotNone(conflict)
        self.assertIsNone(no_conflict)


if __name__ == "__main__":
    unittest.main()
