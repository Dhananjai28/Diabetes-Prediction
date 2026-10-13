"""
prediction.py
--------------
Prediction form blueprint. Reuses app.predictor.DiabetesPredictor (the
same trained model + scaler the desktop app loads) and
app.validators.validate_prediction_form -- the ML inference and validation
logic is never duplicated here, only the web form handling.
"""

from __future__ import annotations

from flask import Blueprint, current_app, flash, render_template, request
from flask_login import current_user, login_required

from app.validators import FEATURE_RANGES, validate_prediction_form

prediction_bp = Blueprint("prediction", __name__, url_prefix="/prediction")


@prediction_bp.route("/", methods=["GET", "POST"])
@login_required
def new():
    db = current_app.db
    predictor = current_app.predictor
    result = None
    values: dict = {}

    if request.method == "POST":
        if predictor is None:
            flash(
                current_app.model_error
                or "Model not found. Run `python model/train_model.py` first.",
                "danger",
            )
            return render_template("prediction.html", feature_ranges=FEATURE_RANGES, values={})

        values = {field: request.form.get(field, "") for field in FEATURE_RANGES}
        validation = validate_prediction_form(values)
        if not validation:
            for message in validation.errors:
                flash(message, "danger")
            return render_template(
                "prediction.html", feature_ranges=FEATURE_RANGES, values=values,
            )

        numeric_values = {k: float(v) for k, v in values.items()}
        outcome = predictor.predict(numeric_values)
        db.add_prediction(
            current_user.username, numeric_values, outcome.label,
            outcome.probability, outcome.risk,
        )

        # The record we just inserted is the most recent one for this user;
        # fetch its id so the result page can link to the same PDF route
        # used by the History page's "Generate PDF" button.
        history = db.get_history(current_user.username)
        latest_row = history[0] if history else None

        result = {
            "label": outcome.label,
            "probability": outcome.probability,
            "risk": outcome.risk,
            "suggestions": outcome.suggestions,
            "record_id": latest_row["id"] if latest_row else None,
        }

    return render_template(
        "prediction.html", feature_ranges=FEATURE_RANGES, values=values, result=result,
    )
