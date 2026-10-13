"""
predictor.py
-------------
Loads the trained model + scaler produced by model/train_model.py and
exposes a simple, typed prediction API for the GUI to call. Keeping this
separate from main.py means the ML logic can be unit tested (see
tests/test_predictor.py) without touching any Tkinter code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.utils import risk_level, risk_suggestions, setup_logger
from app.validators import FEATURE_RANGES

ROOT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT_DIR / "model" / "diabetes_model.pkl"
SCALER_PATH = ROOT_DIR / "model" / "scaler.pkl"

FEATURE_ORDER = list(FEATURE_RANGES.keys())

logger = setup_logger("predictor")


class ModelNotFoundError(Exception):
    """Raised when diabetes_model.pkl or scaler.pkl is missing."""


@dataclass
class PredictionOutcome:
    label: str              # "Diabetic" or "Non-Diabetic"
    probability: float      # probability of the Diabetic class, 0-1
    risk: str                # "Green" | "Yellow" | "Red"
    suggestions: list[str]


class DiabetesPredictor:
    """Loads the persisted model/scaler once and serves predictions."""

    def __init__(self, model_path: Path = MODEL_PATH, scaler_path: Path = SCALER_PATH):
        if not model_path.exists() or not scaler_path.exists():
            raise ModelNotFoundError(
                "Trained model artifacts not found. Run "
                "`python model/train_model.py` first to generate "
                f"{model_path.name} and {scaler_path.name}."
            )
        self.model = joblib.load(model_path)
        self.scaler = joblib.load(scaler_path)
        logger.info("Loaded model %s and scaler from disk.", type(self.model).__name__)

    def predict(self, inputs: dict[str, float]) -> PredictionOutcome:
        """
        inputs: dict keyed by the 8 clinical feature names (see
        validators.FEATURE_RANGES for the exact keys expected).
        """
        ordered = [inputs[name] for name in FEATURE_ORDER]
        X = pd.DataFrame([ordered], columns=FEATURE_ORDER)
        X_scaled = self.scaler.transform(X)

        pred = int(self.model.predict(X_scaled)[0])
        if hasattr(self.model, "predict_proba"):
            proba = float(self.model.predict_proba(X_scaled)[0][1])
        else:
            # Fallback for estimators without predict_proba: use decision
            # function passed through a logistic squashing function.
            score = float(self.model.decision_function(X_scaled)[0])
            proba = 1 / (1 + np.exp(-score))

        label = "Diabetic" if pred == 1 else "Non-Diabetic"
        risk = risk_level(proba)
        suggestions = risk_suggestions(risk)

        logger.info("Prediction: %s (%.2f%%), risk=%s", label, proba * 100, risk)
        return PredictionOutcome(
            label=label, probability=proba, risk=risk, suggestions=suggestions
        )
