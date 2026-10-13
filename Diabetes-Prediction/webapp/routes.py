"""
routes.py
----------
Central blueprint registration for the web app, kept separate from app.py
so the app factory stays focused on Flask/Flask-Login/db wiring. Also
defines the "/" root route, which just sends the browser to the dashboard
(if logged in) or the login page (Flask-Login's login_required redirect
handles the "not logged in" half automatically).
"""

from __future__ import annotations

from flask import Blueprint, Flask, redirect, render_template, url_for
from flask_login import current_user, login_required

from webapp.auth import auth_bp
from webapp.dashboard import dashboard_bp
from webapp.history import history_bp
from webapp.patient import patient_bp
from webapp.prediction import prediction_bp
from webapp.reports import reports_bp

root_bp = Blueprint("root", __name__)


@root_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))
    return redirect(url_for("auth.login"))


@root_bp.route("/about")
@login_required
def about():
    return render_template("about.html")


@root_bp.route("/help")
@login_required
def help_page():
    return render_template("help.html")


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(root_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(prediction_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(reports_bp)
