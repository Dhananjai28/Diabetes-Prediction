import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import Database
from app.profile import (
    BLOOD_GROUPS,
    MAX_CUSTOM_BLOOD_GROUP_LENGTH,
    OTHER_BLOOD_GROUP,
    STANDARD_BLOOD_GROUPS,
    blood_group_form_values,
)
from app.validators import validate_blood_group
from webapp.app import app


class TestBloodGroupValidation(unittest.TestCase):
    def test_dropdown_has_requested_options(self):
        self.assertEqual(
            BLOOD_GROUPS,
            [
                "Not specified", "A+", "A-", "B+", "B-", "AB+", "AB-",
                "O+", "O-", "Other",
            ],
        )
        self.assertEqual(len(STANDARD_BLOOD_GROUPS), 8)

    def test_other_requires_non_empty_custom_value(self):
        self.assertFalse(validate_blood_group(OTHER_BLOOD_GROUP, ""))
        self.assertFalse(validate_blood_group(OTHER_BLOOD_GROUP, "  \t "))

    def test_other_accepts_custom_value_after_trimming(self):
        self.assertTrue(validate_blood_group(OTHER_BLOOD_GROUP, "  Bombay phenotype  "))
        self.assertEqual(
            blood_group_form_values("  Bombay phenotype  "),
            (OTHER_BLOOD_GROUP, "  Bombay phenotype  "),
        )

    def test_other_rejects_unsafe_and_overlong_values(self):
        self.assertFalse(validate_blood_group("A1B+"))
        self.assertFalse(validate_blood_group(OTHER_BLOOD_GROUP, "<b>Bombay</b>"))
        self.assertFalse(
            validate_blood_group(
                OTHER_BLOOD_GROUP, "B" * (MAX_CUSTOM_BLOOD_GROUP_LENGTH + 1)
            )
        )
        self.assertTrue(
            validate_blood_group(
                OTHER_BLOOD_GROUP, "B" * MAX_CUSTOM_BLOOD_GROUP_LENGTH
            )
        )

    def test_saved_standard_and_empty_values_load_into_the_dropdown(self):
        self.assertEqual(blood_group_form_values("A+"), ("A+", ""))
        self.assertEqual(blood_group_form_values(""), ("Not specified", ""))
        self.assertEqual(blood_group_form_values(None), ("Not specified", ""))

    def test_saved_unlisted_values_load_as_other(self):
        self.assertEqual(
            blood_group_form_values("A1B+"),
            (OTHER_BLOOD_GROUP, "A1B+"),
        )


class TestBloodGroupProfileRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_db = app.db
        cls.original_testing = app.config.get("TESTING", False)
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db = Database(Path(cls.temp_dir.name) / "profiles.db")
        cls.db.create_user("alice", "alice@example.com", "Secret123", "answer")
        cls.db.create_user("bob", "bob@example.com", "Secret123", "answer")
        app.db = cls.db
        app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        app.db = cls.original_db
        app.config["TESTING"] = cls.original_testing
        cls.temp_dir.cleanup()

    def setUp(self):
        connection = sqlite3.connect(self.db.db_path)
        try:
            connection.execute("DELETE FROM patient_profile")
            connection.commit()
        finally:
            connection.close()
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = "alice"
            session["_fresh"] = True

    @staticmethod
    def _form_values(blood_group: str, custom_blood_group: str = "") -> dict[str, str]:
        return {
            "patient_name": "Alice Example",
            "gender": "Female",
            "year": "1990",
            "month": "01",
            "day": "01",
            "blood_group": blood_group,
            "custom_blood_group": custom_blood_group,
            "phone": "1234567890",
            "email": "alice@example.com",
            "height": "165",
            "weight": "60",
            "address": "123 Main Street",
            "emergency_contact_name": "Bob Example",
            "emergency_contact_number": "0987654321",
        }

    def _post_profile(self, blood_group: str, custom_blood_group: str = "", **extra):
        page = self.client.get("/profile/edit")
        self.assertEqual(page.status_code, 200)
        match = re.search(
            r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"',
            page.get_data(as_text=True),
        )
        self.assertIsNotNone(match, "Profile form should include a CSRF token.")
        values = self._form_values(blood_group, custom_blood_group)
        values.update(extra)
        values["csrf_token"] = match.group(1)
        return self.client.post("/profile/edit", data=values)

    def _seed_profile(self, username: str, blood_group: str) -> None:
        self.db.upsert_profile(
            username=username,
            patient_name="Alice Example",
            gender="Female",
            date_of_birth="1990-01-01",
            age=36,
            blood_group=blood_group,
            phone="1234567890",
            email=f"{username}@example.com",
            height=165,
            weight=60,
            bmi=22.0,
            address="123 Main Street",
            emergency_contact_name="Bob Example",
            emergency_contact_number="0987654321",
        )

    def test_each_standard_blood_group_is_saved(self):
        for blood_group in STANDARD_BLOOD_GROUPS:
            with self.subTest(blood_group=blood_group):
                response = self._post_profile(blood_group, "ignored custom value")
                self.assertEqual(response.status_code, 302)
                self.assertEqual(
                    self.db.get_profile("alice")["blood_group"], blood_group
                )

    def test_other_saves_and_displays_custom_value(self):
        response = self._post_profile(OTHER_BLOOD_GROUP, "Bombay phenotype")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.db.get_profile("alice")["blood_group"], "Bombay phenotype"
        )
        profile_page = self.client.get("/profile/")
        self.assertEqual(profile_page.status_code, 200)
        self.assertIn("Blood Group", profile_page.get_data(as_text=True))
        self.assertIn("Bombay phenotype", profile_page.get_data(as_text=True))

    def test_empty_other_value_is_rejected(self):
        response = self._post_profile(OTHER_BLOOD_GROUP, " ")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.db.get_profile("alice"))
        self.assertIn(
            b"Enter a blood group for the Other option", response.data
        )

    def test_custom_value_is_trimmed_before_storage(self):
        response = self._post_profile(OTHER_BLOOD_GROUP, "  Bombay phenotype  ")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.db.get_profile("alice")["blood_group"], "Bombay phenotype"
        )

    def test_existing_custom_value_shows_other_and_custom_input(self):
        self._seed_profile("alice", "Bombay phenotype")
        response = self.client.get("/profile/edit")
        html = response.get_data(as_text=True)
        self.assertIn('<option value="Other" selected>Other</option>', html)
        self.assertIn('id="custom_blood_group"', html)
        self.assertIn('value="Bombay phenotype"', html)

    def test_changing_from_other_to_standard_discards_custom_value(self):
        self._seed_profile("alice", "Bombay phenotype")
        response = self._post_profile("A+", "Bombay phenotype")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.db.get_profile("alice")["blood_group"], "A+")

    def test_not_specified_saves_empty_string(self):
        response = self._post_profile("Not specified", "ignored custom value")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.db.get_profile("alice")["blood_group"], "")

    def test_existing_profile_without_blood_group_remains_editable(self):
        self._seed_profile("alice", "")
        response = self.client.get("/profile/edit")
        html = response.get_data(as_text=True)
        self.assertIn('<option value="Not specified" selected>', html)
        self.assertIn('id="customBloodGroupContainer" hidden', html)
        saved = self._post_profile("Not specified")
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(self.db.get_profile("alice")["blood_group"], "")

    def test_profile_updates_are_scoped_to_authenticated_user(self):
        self._seed_profile("bob", "O+")
        response = self._post_profile("A+", username="bob")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.db.get_profile("alice")["blood_group"], "A+")
        self.assertEqual(self.db.get_profile("bob")["blood_group"], "O+")

    def test_unauthenticated_profile_update_is_blocked(self):
        client = app.test_client()
        response = client.get("/profile/edit", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_profile_update_requires_csrf_token(self):
        response = self.client.post(
            "/profile/edit", data=self._form_values("A+")
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.db.get_profile("alice"))


if __name__ == "__main__":
    unittest.main()
