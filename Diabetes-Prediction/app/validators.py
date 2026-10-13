"""
validators.py
--------------
Input validation for the clinical prediction form, the auth forms
(login/registration), and the patient profile form. Centralising validation
here keeps main.py focused on layout/event-wiring and makes the rules
independently unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.profile import BLOOD_GROUPS, GENDERS

# Clinically plausible ranges for each input feature: (min, max, label).
# Used both to reject nonsense values and to populate helper text in the UI.
FEATURE_RANGES: dict[str, tuple[float, float, str]] = {
    "Pregnancies": (0, 20, "Pregnancies"),
    "Glucose": (0, 300, "Glucose (mg/dL)"),
    "BloodPressure": (0, 200, "Blood Pressure (mm Hg)"),
    "SkinThickness": (0, 100, "Skin Thickness (mm)"),
    "Insulin": (0, 900, "Insulin (mu U/ml)"),
    "BMI": (10, 70, "BMI"),
    "DiabetesPedigreeFunction": (0.0, 3.0, "Diabetes Pedigree Function"),
    "Age": (1, 120, "Age"),
}

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
NAME_RE = re.compile(r"^[A-Za-z ]+$")
PHONE_RE = re.compile(r"^\d{10}$")
# SQL-injection style tokens we reject outright, even though parameterised
# queries in database.py already prevent injection at the DB layer — this is
# defense in depth plus friendlier, earlier error messages.
SQLI_PATTERN = re.compile(
    r"(;|--|/\*|\*/|xp_|'\s*or\s*'1'\s*=\s*'1|union\s+select|drop\s+table)",
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]

    def __bool__(self) -> bool:
        return self.is_valid


def _reject_sql_injection(value: str) -> bool:
    return bool(SQLI_PATTERN.search(value))


def validate_username(username: str) -> ValidationResult:
    errors = []
    if not username:
        errors.append("Username cannot be empty.")
    elif _reject_sql_injection(username):
        errors.append("Username contains disallowed characters.")
    elif not USERNAME_RE.match(username):
        errors.append(
            "Username must be 3-20 characters: letters, numbers, underscore only."
        )
    return ValidationResult(len(errors) == 0, errors)


def validate_password(password: str) -> ValidationResult:
    errors = []
    if not password:
        errors.append("Password cannot be empty.")
    elif len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    elif not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    elif not re.search(r"[0-9]", password):
        errors.append("Password must contain at least one digit.")
    return ValidationResult(len(errors) == 0, errors)


def validate_passwords_match(password: str, confirm: str) -> ValidationResult:
    if password != confirm:
        return ValidationResult(False, ["Passwords do not match."])
    return ValidationResult(True, [])


def validate_email(email: str) -> ValidationResult:
    errors = []
    if not email:
        errors.append("Email cannot be empty.")
    elif _reject_sql_injection(email):
        errors.append("Email contains disallowed characters.")
    elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors.append("Enter a valid email address.")
    return ValidationResult(len(errors) == 0, errors)


def validate_numeric_field(field_name: str, raw_value: str) -> ValidationResult:
    """Validate a single clinical input field against FEATURE_RANGES."""
    errors = []
    if field_name not in FEATURE_RANGES:
        return ValidationResult(False, [f"Unknown field: {field_name}"])

    lo, hi, label = FEATURE_RANGES[field_name]
    raw_value = (raw_value or "").strip()

    if raw_value == "":
        errors.append(f"{label} cannot be empty.")
        return ValidationResult(False, errors)

    if _reject_sql_injection(raw_value):
        errors.append(f"{label} contains disallowed characters.")
        return ValidationResult(False, errors)

    try:
        value = float(raw_value)
    except ValueError:
        errors.append(f"{label} must be a number.")
        return ValidationResult(False, errors)

    if value < 0:
        errors.append(f"{label} cannot be negative.")
    elif value < lo or value > hi:
        errors.append(f"{label} must be between {lo} and {hi}.")

    return ValidationResult(len(errors) == 0, errors)


def validate_prediction_form(values: dict[str, str]) -> ValidationResult:
    """Validate the full 8-field prediction form at once."""
    all_errors: list[str] = []
    for field_name in FEATURE_RANGES:
        result = validate_numeric_field(field_name, values.get(field_name, ""))
        all_errors.extend(result.errors)
    return ValidationResult(len(all_errors) == 0, all_errors)


def sanitize_text(value: str) -> str:
    """Strip whitespace and neutralise characters commonly used in SQL
    injection or script injection attempts, for defense-in-depth on any
    free-text field (search boxes, notes, etc.)."""
    value = value.strip()
    value = re.sub(r"[;'\"<>]", "", value)
    return value


# --------------------------------------------------------------------------- #
# Patient profile validation
# --------------------------------------------------------------------------- #

def validate_patient_name(name: str) -> ValidationResult:
    errors = []
    name = (name or "").strip()
    if not name:
        errors.append("Patient name cannot be empty.")
    elif _reject_sql_injection(name):
        errors.append("Patient name contains disallowed characters.")
    elif not NAME_RE.match(name):
        errors.append("Patient name must contain only letters and spaces.")
    return ValidationResult(len(errors) == 0, errors)


def validate_gender(value: str) -> ValidationResult:
    if value not in GENDERS:
        return ValidationResult(False, ["Select a valid gender."])
    return ValidationResult(True, [])


def validate_blood_group(value: str) -> ValidationResult:
    if value not in BLOOD_GROUPS:
        return ValidationResult(False, ["Select a valid blood group."])
    return ValidationResult(True, [])


def validate_phone(phone: str, label: str = "Phone number") -> ValidationResult:
    errors = []
    phone = (phone or "").strip()
    if not phone:
        errors.append(f"{label} cannot be empty.")
    elif not PHONE_RE.match(phone):
        errors.append(f"{label} must be exactly 10 digits.")
    return ValidationResult(len(errors) == 0, errors)


def validate_height_cm(raw_value: str) -> ValidationResult:
    errors = []
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return ValidationResult(False, ["Height cannot be empty."])
    try:
        value = float(raw_value)
    except ValueError:
        return ValidationResult(False, ["Height must be a number."])
    if value < 50 or value > 250:
        errors.append("Height must be between 50 and 250 cm.")
    return ValidationResult(len(errors) == 0, errors)


def validate_weight_kg(raw_value: str) -> ValidationResult:
    errors = []
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return ValidationResult(False, ["Weight cannot be empty."])
    try:
        value = float(raw_value)
    except ValueError:
        return ValidationResult(False, ["Weight must be a number."])
    if value < 10 or value > 300:
        errors.append("Weight must be between 10 and 300 kg.")
    return ValidationResult(len(errors) == 0, errors)


def validate_date_of_birth(year: int, month: int, day: int) -> ValidationResult:
    """Age itself is always calculated automatically (never entered
    directly), but the date components still need to form a real,
    non-future, plausible date of birth."""
    try:
        dob = date(year, month, day)
    except ValueError:
        return ValidationResult(False, ["Enter a valid date of birth."])

    errors = []
    today = date.today()
    if dob > today:
        errors.append("Date of birth cannot be in the future.")
    elif (today.year - dob.year) > 120:
        errors.append("Date of birth must result in a plausible age (0-120).")
    return ValidationResult(len(errors) == 0, errors)


def validate_non_empty_text(value: str, label: str) -> ValidationResult:
    errors = []
    value = (value or "").strip()
    if not value:
        errors.append(f"{label} cannot be empty.")
    elif _reject_sql_injection(value):
        errors.append(f"{label} contains disallowed characters.")
    return ValidationResult(len(errors) == 0, errors)


def validate_profile_form(values: dict[str, str]) -> ValidationResult:
    """Validate the full patient profile form at once.

    Expected keys: patient_name, gender, year, month, day, blood_group,
    phone, email, height, weight, address, emergency_contact_name,
    emergency_contact_number. Age and BMI are never validated directly —
    they're always derived from date_of_birth / height+weight.
    """
    all_errors: list[str] = []
    for result in (
        validate_patient_name(values.get("patient_name", "")),
        validate_gender(values.get("gender", "")),
        validate_blood_group(values.get("blood_group", "")),
        validate_phone(values.get("phone", ""), "Phone number"),
        validate_email(values.get("email", "")),
        validate_height_cm(values.get("height", "")),
        validate_weight_kg(values.get("weight", "")),
        validate_non_empty_text(values.get("address", ""), "Address"),
        validate_non_empty_text(
            values.get("emergency_contact_name", ""), "Emergency contact name"
        ),
        validate_phone(
            values.get("emergency_contact_number", ""), "Emergency contact number"
        ),
    ):
        all_errors.extend(result.errors)

    try:
        year = int(values.get("year", ""))
        month = int(values.get("month", ""))
        day = int(values.get("day", ""))
    except (TypeError, ValueError):
        all_errors.append("Select a valid date of birth.")
    else:
        all_errors.extend(validate_date_of_birth(year, month, day).errors)

    return ValidationResult(len(all_errors) == 0, all_errors)
