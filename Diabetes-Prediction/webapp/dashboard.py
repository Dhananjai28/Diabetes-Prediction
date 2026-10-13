"""
dashboard.py
-------------
Main dashboard blueprint: the authenticated landing page combining the
patient info card, prediction summary, statistics, quick actions, and
recent history -- the web equivalent of the desktop app's Overview tab.
"""

from __future__ import annotations

from flask import Blueprint, current_app, render_template
from flask_login import current_user, login_required

from app.profile import PatientProfile

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def home():
    db = current_app.db
    username = current_user.username

    profile_row = db.get_profile(username)
    profile = PatientProfile.from_row(profile_row) if profile_row else None

    history = db.get_history(username)
    total = len(history)
    latest = history[0] if history else None
    diabetic_count = sum(1 for r in history if r["prediction"] == "Diabetic")
    avg_probability = (
        (sum(r["probability"] for r in history) / total) * 100 if total else 0.0
    )

    risk_counts = {"Green": 0, "Yellow": 0, "Red": 0}
    for r in history:
        risk_counts[r["risk_level"]] = risk_counts.get(r["risk_level"], 0) + 1

    # Oldest-to-newest slice of the most recent 10 predictions, for the
    # "Prediction Trend" line chart.
    trend = list(reversed(history[:10]))

    return render_template(
        "dashboard.html",
        profile=profile,
        recent_history=history[:5],
        total=total,
        latest=latest,
        diabetic_count=diabetic_count,
        avg_probability=avg_probability,
        risk_counts=risk_counts,
        trend=trend,
        model_error=current_app.model_error,
    )
