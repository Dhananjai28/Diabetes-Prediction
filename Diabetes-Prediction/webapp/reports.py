"""
reports.py
-----------
PDF download routes and shared chart/data helpers, all built entirely on
top of the existing app.report_generator module -- no PDF-building or
chart-plotting logic is duplicated here. This module also exposes
`row_to_inputs()` and `image_to_base64()`, which history.py and
prediction.py reuse so the History "View Details" page can embed the same
gauge/feature-profile charts used in the PDF without needing a separate
image-serving route.
"""

from __future__ import annotations

import base64
import io
import os
import tempfile
from pathlib import Path

from flask import (
    Blueprint, current_app, flash, redirect, render_template, send_file,
    url_for, after_this_request,
)
from flask_login import current_user, login_required

from app.profile import PatientProfile
from app.report_generator import generate_history_report, generate_prediction_report
from app.utils import risk_suggestions

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _make_temp_pdf_path() -> Path:
    """Create an empty temp file inside Config.REPORT_TEMP_DIR (created on
    first use) and return its path. Keeping generated PDFs in one
    project-local, easily-gitignored directory instead of the OS default
    temp dir makes cleanup failures (if any) easy to spot and clear."""
    temp_dir: Path = current_app.config["REPORT_TEMP_DIR"]
    temp_dir.mkdir(parents=True, exist_ok=True)
    fd, path_str = tempfile.mkstemp(suffix=".pdf", dir=temp_dir)
    os.close(fd)
    return Path(path_str)


@reports_bp.route("/")
@login_required
def picker():
    """A simple landing page: "Generate Full Report" (Quick Actions) and
    other report entry points land here, listing recent predictions so the
    user can pick one to download without going through History first."""
    db = current_app.db
    rows = db.get_history(current_user.username)[:10]
    return render_template("report.html", rows=rows)

# Maps prediction_history DB columns (snake_case) back to the
# FEATURE_RANGES-keyed names predictor.py / report_generator.py expect --
# the same bridge the desktop app's main.py uses.
HISTORY_DB_TO_FEATURE = {
    "pregnancies": "Pregnancies",
    "glucose": "Glucose",
    "blood_pressure": "BloodPressure",
    "skin_thickness": "SkinThickness",
    "insulin": "Insulin",
    "bmi": "BMI",
    "dpf": "DiabetesPedigreeFunction",
    "age": "Age",
}


def row_to_inputs(row) -> dict[str, float]:
    """Reconstruct the 8-field clinical inputs dict from a prediction_history row."""
    return {feature: row[col] for col, feature in HISTORY_DB_TO_FEATURE.items()}


def image_to_base64(pil_image) -> str:
    """Encode a PIL Image as base64 PNG, for inline <img src="data:...">
    embedding in templates -- avoids needing a separate image-serving route
    just to display report_generator's matplotlib charts in HTML."""
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def get_patient_profile_dict(db, username: str) -> dict | None:
    row = db.get_profile(username)
    return PatientProfile.from_row(row).report_dict() if row else None


def _find_history_row(db, username: str, record_id: int):
    rows = db.get_history(username)
    return next((r for r in rows if r["id"] == record_id), None)


def _cleanup_temp_file(path: Path) -> None:
    """Registered via after_this_request so the temp PDF is removed once
    Flask has finished streaming it to the client, rather than leaking
    files into REPORT_TEMP_DIR / the OS temp dir over time."""
    @after_this_request
    def _remove(response):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            current_app.logger.warning("Could not remove temp report file: %s", path)
        return response


@reports_bp.route("/prediction/<int:record_id>/pdf")
@login_required
def download_prediction_pdf(record_id: int):
    db = current_app.db
    row = _find_history_row(db, current_user.username, record_id)
    if row is None:
        flash("Prediction record not found.", "danger")
        return redirect(url_for("history.list_view"))

    inputs = row_to_inputs(row)
    suggestions = risk_suggestions(row["risk_level"])
    patient_profile = get_patient_profile_dict(db, current_user.username)

    tmp_path = _make_temp_pdf_path()
    generate_prediction_report(
        current_user.username, inputs, row["prediction"], row["probability"],
        row["risk_level"], suggestions, tmp_path, patient_profile=patient_profile,
    )
    _cleanup_temp_file(tmp_path)
    return send_file(
        tmp_path, as_attachment=True,
        download_name=f"{current_user.username}_prediction_{record_id}.pdf",
        mimetype="application/pdf",
    )


@reports_bp.route("/history/pdf")
@login_required
def download_history_pdf():
    db = current_app.db
    rows = db.get_history(current_user.username)
    patient_profile = get_patient_profile_dict(db, current_user.username)

    tmp_path = _make_temp_pdf_path()
    generate_history_report(
        current_user.username, rows, tmp_path, patient_profile=patient_profile,
    )
    _cleanup_temp_file(tmp_path)
    return send_file(
        tmp_path, as_attachment=True,
        download_name=f"{current_user.username}_prediction_history.pdf",
        mimetype="application/pdf",
    )
