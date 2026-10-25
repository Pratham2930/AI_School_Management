import inspect
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import app as school_app


class EmptyLeaveQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


class TeacherLeaveEventTests(unittest.TestCase):
    def setUp(self):
        self.app_context = school_app.app.app_context()
        self.app_context.push()
        self.addCleanup(self.app_context.pop)
        self.leave_request = SimpleNamespace(
            id=17,
            status="Pending",
            requester_type="teacher",
            teacher_id=42,
            start_date=date(2026, 11, 3),
            end_date=date(2026, 11, 5),
            review_note=None,
            reviewed_by=None,
            reviewed_at=None
        )
        self.get_patch = patch.object(
            school_app.db.session,
            "get",
            return_value=self.leave_request
        )
        self.commit_patch = patch.object(school_app.db.session, "commit")
        self.rollback_patch = patch.object(
            school_app.db.session,
            "rollback"
        )
        self.query_patch = patch.object(
            school_app.LeaveRequest,
            "query",
            EmptyLeaveQuery()
        )
        self.current_user_patch = patch.object(
            school_app,
            "current_user",
            SimpleNamespace(id=5)
        )
        self.get_patch.start()
        self.commit_mock = self.commit_patch.start()
        self.rollback_mock = self.rollback_patch.start()
        self.query_patch.start()
        self.current_user_patch.start()
        self.addCleanup(self.current_user_patch.stop)
        self.addCleanup(self.query_patch.stop)
        self.addCleanup(self.rollback_patch.stop)
        self.addCleanup(self.commit_patch.stop)
        self.addCleanup(self.get_patch.stop)

    def invoke_review(self, decision):
        route = inspect.unwrap(school_app.review_leave_request)
        with school_app.app.test_request_context(
            "/admin/leave-requests/17/" + decision,
            method="POST",
            data={"review_note": "Reviewed"}
        ):
            return route(17, decision)

    def test_teacher_approval_stages_availability_event_before_commit(self):
        operations = []
        self.commit_mock.side_effect = lambda: operations.append("commit")
        with patch.object(
            school_app,
            "queue_kafka_event",
            side_effect=lambda **kwargs: operations.append(("event", kwargs))
        ) as queue_event:
            response = self.invoke_review("approve")

        self.assertEqual(302, response.status_code)
        self.assertEqual("Approved", self.leave_request.status)
        self.assertEqual(["event", "commit"], [
            item if item == "commit" else item[0]
            for item in operations
        ])
        queue_event.assert_called_once_with(
            event_type="teacher.availability.updated",
            entity_id=17,
            payload={
                "action": "leave_approved",
                "leave_request_id": 17,
                "teacher_id": 42,
                "start_date": "2026-11-03",
                "end_date": "2026-11-05"
            }
        )

    def test_rejecting_teacher_leave_does_not_stage_availability_event(self):
        with patch.object(
            school_app,
            "queue_kafka_event"
        ) as queue_event:
            response = self.invoke_review("reject")

        self.assertEqual(302, response.status_code)
        self.assertEqual("Rejected", self.leave_request.status)
        queue_event.assert_not_called()
        self.commit_mock.assert_called_once()

    def test_failed_commit_rolls_back_leave_and_outbox_transaction(self):
        self.commit_mock.side_effect = RuntimeError(
            "database unavailable"
        )
        with patch.object(school_app, "queue_kafka_event") as queue_event:
            response = self.invoke_review("approve")

        self.assertEqual(302, response.status_code)
        queue_event.assert_called_once()
        self.rollback_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
