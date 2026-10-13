"""
test_validator.py
-------------------
Unit tests for app/validators.py: field-level, form-level, and auth validation.
Run with:  python -m unittest discover tests
"""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.validators import (
    validate_email,
    validate_numeric_field,
    validate_password,
    validate_passwords_match,
    validate_prediction_form,
    validate_username,
)


class TestNumericFieldValidation(unittest.TestCase):
    def test_valid_glucose(self):
        self.assertTrue(validate_numeric_field("Glucose", "120"))

    def test_empty_field_rejected(self):
        result = validate_numeric_field("Glucose", "")
        self.assertFalse(result)
        self.assertIn("cannot be empty", result.errors[0])

    def test_negative_value_rejected(self):
        result = validate_numeric_field("BMI", "-5")
        self.assertFalse(result)

    def test_non_numeric_rejected(self):
        result = validate_numeric_field("Age", "abc")
        self.assertFalse(result)

    def test_out_of_range_rejected(self):
        result = validate_numeric_field("Age", "500")
        self.assertFalse(result)

    def test_sql_injection_rejected(self):
        result = validate_numeric_field("Glucose", "120; DROP TABLE users;")
        self.assertFalse(result)

    def test_unknown_field(self):
        result = validate_numeric_field("NotAField", "10")
        self.assertFalse(result)


class TestPredictionFormValidation(unittest.TestCase):
    VALID_FORM = {
        "Pregnancies": "2", "Glucose": "120", "BloodPressure": "70",
        "SkinThickness": "20", "Insulin": "80", "BMI": "24.5",
        "DiabetesPedigreeFunction": "0.5", "Age": "30",
    }

    def test_valid_form_passes(self):
        self.assertTrue(validate_prediction_form(self.VALID_FORM))

    def test_missing_field_fails(self):
        form = dict(self.VALID_FORM)
        form["Age"] = ""
        self.assertFalse(validate_prediction_form(form))

    def test_multiple_errors_collected(self):
        form = dict(self.VALID_FORM)
        form["Age"] = ""
        form["BMI"] = "-1"
        result = validate_prediction_form(form)
        self.assertFalse(result)
        self.assertGreaterEqual(len(result.errors), 2)


class TestAuthValidation(unittest.TestCase):
    def test_valid_username(self):
        self.assertTrue(validate_username("john_doe1"))

    def test_username_too_short(self):
        self.assertFalse(validate_username("jo"))

    def test_username_sql_injection(self):
        self.assertFalse(validate_username("admin'--"))

    def test_valid_password(self):
        self.assertTrue(validate_password("Secret123"))

    def test_password_missing_uppercase(self):
        self.assertFalse(validate_password("secret123"))

    def test_password_missing_digit(self):
        self.assertFalse(validate_password("SecretPass"))

    def test_password_too_short(self):
        self.assertFalse(validate_password("Sh0rt"))

    def test_passwords_match(self):
        self.assertTrue(validate_passwords_match("Secret123", "Secret123"))

    def test_passwords_do_not_match(self):
        self.assertFalse(validate_passwords_match("Secret123", "Different123"))

    def test_valid_email(self):
        self.assertTrue(validate_email("user@example.com"))

    def test_invalid_email(self):
        self.assertFalse(validate_email("not-an-email"))


if __name__ == "__main__":
    unittest.main()
