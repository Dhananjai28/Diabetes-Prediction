"""
patient.py
-----------
Patient profile blueprint: view, create, and edit the single patient
profile per user (exactly one row per user in patient_profile, guaranteed
by Database.upsert_profile()). Reuses app.profile and app.validators --
the same modules the desktop app's ProfileFormWindow uses -- so validation
rules and age/BMI calculations never drift between the two interfaces.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.database import DatabaseError
from app.profile import BLOOD_GROUPS, GENDERS, MIN_BIRTH_YEAR, calculate_age, calculate_bmi
from app.profile import PatientProfile
from app.validators import validate_profile_form

patient_bp = Blueprint("patient", __name__, url_prefix="/profile")


def _row_to_form_values(row) -> dict:
    year, month, day = row["date_of_birth"].split("-")
    return {
        "patient_name": row["patient_name"],
        "gender": row["gender"],
        "year": year, "month": month, "day": day,
        "blood_group": row["blood_group"],
        "phone": row["phone"],
        "email": row["email"],
        "height": row["height"],
        "weight": row["weight"],
        "address": row["address"] or "",
        "emergency_contact_name": row["emergency_contact_name"] or "",
        "emergency_contact_number": row["emergency_contact_number"] or "",
    }


@patient_bp.route("/")
@login_required
def view():
    db = current_app.db
    row = db.get_profile(current_user.username)
    if row is None:
        flash("Complete your patient profile to get started.", "info")
        return redirect(url_for("patient.edit"))

    history = db.get_history(current_user.username)
    total = len(history)
    latest = history[0] if history else None
    avg_probability = (
        (sum(r["probability"] for r in history) / total) * 100 if total else 0.0
    )

    return render_template(
        "overview.html",
        profile=PatientProfile.from_row(row),
        total=total, latest=latest, avg_probability=avg_probability,
    )


@patient_bp.route("/edit", methods=["GET", "POST"])
@login_required
def edit():
    db = current_app.db
    existing_row = db.get_profile(current_user.username)

    if request.method == "POST":
        values = {
            "patient_name": request.form.get("patient_name", ""),
            "gender": request.form.get("gender", ""),
            "year": request.form.get("year", ""),
            "month": request.form.get("month", ""),
            "day": request.form.get("day", ""),
            "blood_group": request.form.get("blood_group", ""),
            "phone": request.form.get("phone", ""),
            "email": request.form.get("email", ""),
            "height": request.form.get("height", ""),
            "weight": request.form.get("weight", ""),
            "address": request.form.get("address", ""),
            "emergency_contact_name": request.form.get("emergency_contact_name", ""),
            "emergency_contact_number": request.form.get("emergency_contact_number", ""),
        }
        result = validate_profile_form(values)
        if not result:
            for message in result.errors:
                flash(message, "danger")
            return render_template(
                "patient_profile.html", genders=GENDERS, blood_groups=BLOOD_GROUPS,
                values=values, min_year=MIN_BIRTH_YEAR, current_year=date.today().year,
                is_new=existing_row is None,
            )

        dob = date(int(values["year"]), int(values["month"]), int(values["day"]))
        height, weight = float(values["height"]), float(values["weight"])

        try:
            db.upsert_profile(
                username=current_user.username,
                patient_name=values["patient_name"].strip(),
                gender=values["gender"],
                date_of_birth=dob.isoformat(),
                age=calculate_age(dob),
                blood_group=values["blood_group"],
                phone=values["phone"].strip(),
                email=values["email"].strip(),
                height=height,
                weight=weight,
                bmi=calculate_bmi(height, weight),
                address=values["address"].strip(),
                emergency_contact_name=values["emergency_contact_name"].strip(),
                emergency_contact_number=values["emergency_contact_number"].strip(),
            )
            flash("Profile saved successfully.", "success")
            return redirect(url_for("patient.view"))
        except DatabaseError as exc:
            flash(str(exc), "danger")
            return render_template(
                "patient_profile.html", genders=GENDERS, blood_groups=BLOOD_GROUPS,
                values=values, min_year=MIN_BIRTH_YEAR, current_year=date.today().year,
                is_new=existing_row is None,
            )

    values = _row_to_form_values(existing_row) if existing_row is not None else {}
    return render_template(
        "patient_profile.html", genders=GENDERS, blood_groups=BLOOD_GROUPS,
        values=values, min_year=MIN_BIRTH_YEAR, current_year=date.today().year,
        is_new=existing_row is None,
    )
