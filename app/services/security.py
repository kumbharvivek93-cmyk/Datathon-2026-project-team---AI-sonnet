"""Password, redirect, and bootstrap-account security helpers."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin, urlparse

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def hash_password(password: str) -> str:
    """Validate and hash a user password using Werkzeug's secure default."""
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("Passwords must contain at least 8 characters.")
    return generate_password_hash(password)


def verify_password(password_hash: str, candidate_password: str) -> bool:
    """Safely compare a supplied password to an existing hash."""
    if not password_hash or not isinstance(candidate_password, str):
        return False
    return check_password_hash(password_hash, candidate_password)


def is_safe_redirect_target(target: str | None, host_url: str) -> bool:
    """Allow redirects only to paths on the current host."""
    if not target:
        return False
    reference = urlparse(host_url)
    candidate = urlparse(urljoin(host_url, target))
    return candidate.scheme in {"http", "https"} and candidate.netloc == reference.netloc


def seed_demo_admin() -> bool:
    """Create the configured development administrator if it does not exist.

    The function expects schema creation or migrations to have run already. It
    returns ``True`` only when it creates a new account, making startup logs
    and tests easy to interpret.
    """
    from app.models import Role, User

    username = current_app.config["DEMO_ADMIN_USERNAME"].strip()
    email = current_app.config["DEMO_ADMIN_EMAIL"].strip().lower()
    existing_user = User.query.filter(
        db.or_(User.username == username, User.email == email)
    ).first()
    if existing_user:
        return False

    admin = User(
        username=username,
        email=email,
        full_name=current_app.config["DEMO_ADMIN_NAME"],
        role=Role.ADMIN.value,
        last_login_at=None,
    )
    admin.set_password(current_app.config["DEMO_ADMIN_PASSWORD"])
    db.session.add(admin)
    db.session.commit()
    current_app.logger.info("Created configured demo administrator '%s'.", username)
    return True


def record_successful_login(user) -> None:
    """Persist the time of a successful interactive login."""
    user.last_login_at = datetime.utcnow()
    db.session.commit()
