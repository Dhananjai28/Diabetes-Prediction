"""
profile.py
-----------
Patient Profile domain module.

Holds the constants (blood groups, genders) and pure calculations (age from
date of birth, BMI from height/weight) shared by the profile form (main.py),
validation (validators.py), and PDF reports (report_generator.py). No
Tkinter or database code lives here, matching the existing pattern of
predictor.py / validators.py: domain logic stays independently testable and
separate from the GUI layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

GENDERS = ["Male", "Female", "Other"]
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "A1B+"]

# Earliest selectable birth year in the profile form's date picker.
MIN_BIRTH_YEAR = 1900


def calculate_age(dob: date, as_of: date | None = None) -> int:
    """Whole years of age as of `as_of` (defaults to today)."""
    as_of = as_of or date.today()
    years = as_of.year - dob.year
    if (as_of.month, as_of.day) < (dob.month, dob.day):
        years -= 1
    return max(years, 0)


def calculate_bmi(height_cm: float, weight_kg: float) -> float:
    """Body Mass Index = weight(kg) / height(m)^2, rounded to 1 decimal."""
    if height_cm <= 0:
        return 0.0
    height_m = height_cm / 100
    return round(weight_kg / (height_m ** 2), 1)


@dataclass
class PatientProfile:
    """Typed, convenient view over a patient_profile database row."""

    username: str
    patient_name: str
    gender: str
    date_of_birth: str  # ISO "YYYY-MM-DD"
    age: int
    blood_group: str
    phone: str
    email: str
    height: float
    weight: float
    bmi: float
    address: str
    emergency_contact_name: str
    emergency_contact_number: str
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row) -> "PatientProfile":
        """Build a PatientProfile from a sqlite3.Row (patient_profile table)."""
        return cls(
            username=row["username"],
            patient_name=row["patient_name"],
            gender=row["gender"],
            date_of_birth=row["date_of_birth"],
            age=row["age"],
            blood_group=row["blood_group"],
            phone=row["phone"],
            email=row["email"],
            height=row["height"],
            weight=row["weight"],
            bmi=row["bmi"],
            address=row["address"] or "",
            emergency_contact_name=row["emergency_contact_name"] or "",
            emergency_contact_number=row["emergency_contact_number"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def initials(self) -> str:
        """1-2 letter initials for the profile-picture placeholder."""
        parts = [p for p in self.patient_name.strip().split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][0].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def report_dict(self) -> dict:
        """Shape expected by report_generator's patient-information section."""
        return {
            "patient_name": self.patient_name,
            "gender": self.gender,
            "age": self.age,
            "date_of_birth": self.date_of_birth,
            "blood_group": self.blood_group,
            "phone": self.phone,
            "bmi": self.bmi,
            "height": self.height,
            "weight": self.weight,
            "emergency_contact_name": self.emergency_contact_name,
            "emergency_contact_number": self.emergency_contact_number,
        }
