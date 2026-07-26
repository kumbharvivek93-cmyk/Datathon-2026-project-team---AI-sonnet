"""Reusable role-based authorization decorators."""

from __future__ import annotations

from functools import wraps

from flask import abort
from flask_login import current_user

from app.models import Role


def roles_required(*roles: Role | str):
    """Require an authenticated user with at least one of ``roles``."""
    if not roles:
        raise ValueError("At least one role must be supplied.")

    normalized_roles = tuple(
        role.value if isinstance(role, Role) else str(role).lower()
        for role in roles
    )

    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not current_user.has_role(*normalized_roles):
                abort(403)
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def role_required(role: Role | str):
    """Singular convenience alias for ``roles_required``."""
    return roles_required(role)


def admin_required(view):
    """Restrict a view to platform administrators."""
    return roles_required(Role.ADMIN)(view)
