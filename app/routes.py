"""Login and logout routes for browser-based platform access."""

from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.routing import BuildError

from app.auth import auth_bp
from app.auth.forms import LoginForm
from app.extensions import login_manager
from app.models import User
from app.services.security import (
    is_safe_redirect_target,
    record_successful_login,
)


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Restore a user from a Flask-Login session identifier."""
    try:
        return User.query.get(int(user_id))
    except (TypeError, ValueError):
        return None


def _default_authenticated_destination() -> str:
    """Use the dashboard when available, otherwise the app's landing route."""
    try:
        return url_for("dashboard.index")
    except BuildError:
        return url_for("index")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate a user with CSRF-protected form handling."""
    if current_user.is_authenticated:
        return redirect(_default_authenticated_destination())

    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            record_successful_login(user)
            flash("Welcome back.", "success")

            next_url = request.args.get("next")
            if is_safe_redirect_target(next_url, request.host_url):
                return redirect(next_url)
            return redirect(_default_authenticated_destination())

        flash("Invalid username or password.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.post("/logout")
def logout():
    """End the current session. CSRF protection applies to this mutation."""
    if current_user.is_authenticated:
        logout_user()
        flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
