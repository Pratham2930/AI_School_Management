
from datetime import date

from .permissions import is_admin


def generate_response(
    message,
    user,
    Student,
    Teacher,
    Staff,
    Attendance,
    SchoolClass
):
    question = " ".join(message.lower().split())

    if question in ("hi", "hello", "hey"):
        return (
            f"Hello {user.name}! "
            "Welcome to your AI School Assistant."
        )

    if question in ("help", "what can you do?"):
        if is_admin(user):
            return (
                "I can show total students, teachers, "
                "staff, classes and today's attendance."
            )

        return (
            "I can help you navigate the school system. "
            "Personal academic information will be "
            "available after account verification."
        )

    # School-wide statistics require admin access.
    if not is_admin(user):
        return (
            "I cannot access school-wide records for "
            "your role. Type 'help' for assistance."
        )

    if (
        "student" in question
        and any(
            term in question
            for term in ("total", "count", "how many")
        )
    ):
        return (
            f"Total students: {Student.query.count()}"
        )

    if (
        "teacher" in question
        and any(
            term in question
            for term in ("total", "count", "how many")
        )
    ):
        return (
            f"Total teachers: {Teacher.query.count()}"
        )

    if (
        "staff" in question
        and any(
            term in question
            for term in ("total", "count", "how many")
        )
    ):
        return (
            f"Total staff: {Staff.query.count()}"
        )

    if (
        "class" in question
        and any(
            term in question
            for term in ("total", "count", "how many")
        )
    ):
        return (
            f"Total classes: {SchoolClass.query.count()}"
        )

    if "attendance" in question and "today" in question:
        count = Attendance.query.filter_by(
            attendance_date=date.today()
        ).count()

        return (
            f"Attendance records entered today: {count}"
        )

    return (
        "I don't have an answer for that question yet. "
        "Type 'help' to see supported questions."
    )
