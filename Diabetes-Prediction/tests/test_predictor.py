"""
test_predictor.py
-------------------
Unit tests for app/predictor.py (ML inference) and app/database.py
(SQLite data layer). Uses a temporary database file so tests never touch
the real app/assets/diabetes_app.db.

Requires the model to already be trained:
    python model/train_model.py

Run with:  python -m unittest discover tests
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import Database, DatabaseError
from app.predictor import DiabetesPredictor, ModelNotFoundError

SAMPLE_INPUT = {
    "Pregnancies": 2, "Glucose": 130, "BloodPressure": 74, "SkinThickness": 22,
    "Insulin": 90, "BMI": 28.5, "DiabetesPedigreeFunction": 0.45, "Age": 35,
}


class TestPredictor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.predictor = DiabetesPredictor()
        except ModelNotFoundError:
            cls.predictor = None

    def test_model_loads(self):
        if self.predictor is None:
            self.skipTest("Model artifacts not found; run model/train_model.py first.")
        self.assertIsNotNone(self.predictor.model)
        self.assertIsNotNone(self.predictor.scaler)

    def test_predict_returns_valid_outcome(self):
        if self.predictor is None:
            self.skipTest("Model artifacts not found; run model/train_model.py first.")
        outcome = self.predictor.predict(SAMPLE_INPUT)
        self.assertIn(outcome.label, ("Diabetic", "Non-Diabetic"))
        self.assertTrue(0.0 <= outcome.probability <= 1.0)
        self.assertIn(outcome.risk, ("Green", "Yellow", "Red"))
        self.assertGreater(len(outcome.suggestions), 0)

    def test_high_glucose_increases_probability(self):
        if self.predictor is None:
            self.skipTest("Model artifacts not found; run model/train_model.py first.")
        low = dict(SAMPLE_INPUT, Glucose=80)
        high = dict(SAMPLE_INPUT, Glucose=190)
        low_outcome = self.predictor.predict(low)
        high_outcome = self.predictor.predict(high)
        self.assertGreaterEqual(high_outcome.probability, low_outcome.probability)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(db_path=Path(self._tmpdir.name) / "test.db")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_create_and_authenticate_user(self):
        self.db.create_user("alice", "alice@example.com", "Secret123", "paris")
        self.assertTrue(self.db.authenticate("alice", "Secret123"))
        self.assertFalse(self.db.authenticate("alice", "WrongPass1"))

    def test_duplicate_username_rejected(self):
        self.db.create_user("bob", "bob@example.com", "Secret123", "london")
        with self.assertRaises(DatabaseError):
            self.db.create_user("bob", "bob2@example.com", "Secret123", "london")

    def test_duplicate_email_rejected(self):
        self.db.create_user("carol", "carol@example.com", "Secret123", "tokyo")
        with self.assertRaises(DatabaseError):
            self.db.create_user("carol2", "carol@example.com", "Secret123", "tokyo")

    def test_security_answer_and_password_reset(self):
        self.db.create_user("dave", "dave@example.com", "Secret123", "berlin")
        self.assertTrue(self.db.verify_security_answer("dave", "Berlin"))  # case-insensitive
        self.db.reset_password("dave", "NewPass456")
        self.assertTrue(self.db.authenticate("dave", "NewPass456"))
        self.assertFalse(self.db.authenticate("dave", "Secret123"))

    def test_prediction_history_lifecycle(self):
        self.db.create_user("erin", "erin@example.com", "Secret123", "rome")
        self.db.add_prediction("erin", SAMPLE_INPUT, "Diabetic", 0.82, "Red")
        self.db.add_prediction("erin", SAMPLE_INPUT, "Non-Diabetic", 0.12, "Green")

        history = self.db.get_history("erin")
        self.assertEqual(len(history), 2)

        filtered = self.db.get_history("erin", search="Red")
        self.assertEqual(len(filtered), 1)

        self.db.delete_prediction(history[0]["id"], "erin")
        self.assertEqual(len(self.db.get_history("erin")), 1)

        self.db.clear_history("erin")
        self.assertEqual(len(self.db.get_history("erin")), 0)

    def test_settings_roundtrip(self):
        self.db.create_user("frank", "frank@example.com", "Secret123", "cairo")
        self.assertIsNone(self.db.get_setting("frank", "theme"))
        self.db.set_setting("frank", "theme", "light")
        self.assertEqual(self.db.get_setting("frank", "theme"), "light")
        self.db.set_setting("frank", "theme", "dark")
        self.assertEqual(self.db.get_setting("frank", "theme"), "dark")


if __name__ == "__main__":
    unittest.main()
