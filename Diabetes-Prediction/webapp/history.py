"""
history.py
-----------
Prediction history blueprint: searchable list, per-record detail (with the
same probability-gauge and feature-profile charts used in the PDF report,
reused via report_generator's public image helpers), delete, and clear-all.

Reuses app.database.Database and app.utils.risk_suggestions -- the same
functions the desktop app's History tab and HistoryDetailWindow use.
"""

from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.report_generator import get_feature_profile_image, get_probability_gauge_image
from app.utils import risk_suggestions
from webapp.reports import get_patient_profile_dict, image_to_base64, row_to_inputs

history_bp = Blueprint("history", __name__, url_prefix="/history")


@history_bp.route("/")
@login_required
def list_view():
    db = current_app.db
    search = request.args.get("q", "").strip()
    rows = db.get_history(current_user.username, search=search)
    return render_template("history.html", rows=rows, search=search)


@history_bp.route("/<int:record_id>")
@login_required
def detail(record_id: int):
    db = current_app.db
    rows = db.get_history(current_user.username)
    row = next((r for r in rows if r["id"] == record_id), None)
    if row is None:
        flash("Prediction record not found.", "danger")
        return redirect(url_for("history.list_view"))

    inputs = row_to_inputs(row)
    suggestions = risk_suggestions(row["risk_level"])
    profile_row = db.get_profile(current_user.username)

    gauge_b64 = image_to_base64(get_probability_gauge_image(row["probability"], row["risk_level"]))
    feature_b64 = image_to_base64(get_feature_profile_image(inputs))

    return render_template(
        "history_detail.html",
        row=row, inputs=inputs, suggestions=suggestions,
        gauge_image=gauge_b64, feature_image=feature_b64,
        profile_row=profile_row,
    )


@history_bp.route("/<int:record_id>/delete", methods=["POST"])
@login_required
def delete(record_id: int):
    current_app.db.delete_prediction(record_id, current_user.username)
    flash("Prediction record deleted.", "info")
    return redirect(url_for("history.list_view"))


@history_bp.route("/clear", methods=["POST"])
@login_required
def clear_all():
    current_app.db.clear_history(current_user.username)
    flash("Prediction history cleared.", "info")
    return redirect(url_for("history.list_view"))
