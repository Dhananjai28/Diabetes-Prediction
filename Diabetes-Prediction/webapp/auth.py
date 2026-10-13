"""
auth.py
--------
Authentication blueprint: login, registration, logout, forgot password.

Reuses the exact same validation (app.validators) and persistence
(app.database.Database, shared via current_app.db) as the desktop app --
no business logic is duplicated here, only the web request/response
plumbing and Flask-Login session integration.
"""

from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import UserMixin, login_required, login_user, logout_user

from app.database import DatabaseError
from app.validators import (
    validate_email,
    validate_password,
    validate_passwords_match,
    validate_username,
)

auth_bp = Blueprint("auth", __name__)


class WebUser(UserMixin):
    """Thin Flask-Login wrapper around a username. All actual account data
    lives in the shared Database -- this class carries no state beyond the
    id Flask-Login needs for the session cookie."""

    def __init__(self, username: str):
        self.username = username

    def get_id(self) -> str:
        return self.username


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        result = validate_username(username)
        if not result:
            flash(result.errors[0], "danger")
            return render_template("login.html")

        db = current_app.db
        if db.authenticate(username, password):
            login_user(WebUser(username))
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard.home"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        security_answer = request.form.get("security_answer", "").strip()

        errors: list[str] = []
        for result in (
            validate_username(username),
            validate_email(email),
            validate_password(password),
            validate_passwords_match(password, confirm),
        ):
            if not result:
                errors.extend(result.errors)
        if not security_answer:
            errors.append("Security answer cannot be empty.")

        if errors:
            for message in errors:
                flash(message, "danger")
            return render_template(
                "register.html",
                form_values={"username": username, "email": email},
            )

        try:
            current_app.db.create_user(username, email, password, security_answer)
            flash("Account created! Please log in.", "success")
            return redirect(url_for("auth.login"))
        except DatabaseError as exc:
            flash(str(exc), "danger")
            return render_template(
                "register.html",
                form_values={"username": username, "email": email},
            )

    return render_template("register.html", form_values={})


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Reuses login.html with its "forgot password" panel expanded, rather
    than a separate template, to stay within the project's specified
    template list."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        answer = request.form.get("security_answer", "").strip()
        new_password = request.form.get("new_password", "")

        pw_result = validate_password(new_password)
        if not pw_result:
            flash(pw_result.errors[0], "danger")
            return render_template("login.html", show_forgot=True)

        db = current_app.db
        if not db.verify_security_answer(username, answer):
            flash("Username or security answer is incorrect.", "danger")
            return render_template("login.html", show_forgot=True)

        try:
            db.reset_password(username, new_password)
            flash("Password reset! Please log in.", "success")
            return redirect(url_for("auth.login"))
        except DatabaseError as exc:
            flash(str(exc), "danger")
            return render_template("login.html", show_forgot=True)

    return render_template("login.html", show_forgot=True)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
