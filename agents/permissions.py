
ALLOWED_ROLES = {
    "super_admin",
    "admin",
    "teacher",
    "student",
    "parent",
    "staff"
}


def can_use_assistant(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.role in ALLOWED_ROLES
    )


def is_admin(user):
    return (
        can_use_assistant(user)
        and user.role in {"super_admin", "admin"}
    )
