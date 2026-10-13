import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from model import evaluate_model


class TestModelEvaluation(unittest.TestCase):
    def test_confusion_and_roc_plots_generate(self):
        df = pd.read_csv(ROOT_DIR / "data" / "processed.csv")
        model = evaluate_model.joblib.load(ROOT_DIR / "model" / "diabetes_model.pkl")
        scaler = evaluate_model.joblib.load(ROOT_DIR / "model" / "scaler.pkl")

        evaluate_model.plot_confusion_and_roc(df, model, scaler)

        expected_files = [
            ROOT_DIR / "screenshots" / "07_confusion_matrix.png",
            ROOT_DIR / "screenshots" / "08_roc_curve.png",
        ]
        for path in expected_files:
            self.assertTrue(path.exists(), f"Expected plot was not generated: {path}")


if __name__ == "__main__":
    unittest.main()
