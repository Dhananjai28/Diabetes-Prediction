"""
train_model.py
----------------
End-to-end training pipeline for the Diabetes Prediction project.

Responsibilities:
    1. Load and clean the raw dataset (missing values, duplicates, outliers).
    2. Engineer a train/test split and scale features.
    3. Train six classifiers, evaluate them on consistent metrics.
    4. Persist the best-performing model and the fitted scaler to disk so the
       desktop application (app/predictor.py) can load them at runtime.

Run directly:
    python model/train_model.py

Author: Diabetes Prediction Project
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

# --------------------------------------------------------------------------- #
# Paths & Logging
# --------------------------------------------------------------------------- #

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT_DIR / "data" / "diabetes.csv"
PROCESSED_PATH = ROOT_DIR / "data" / "processed.csv"
MODEL_PATH = ROOT_DIR / "model" / "diabetes_model.pkl"
SCALER_PATH = ROOT_DIR / "model" / "scaler.pkl"
METRICS_PATH = ROOT_DIR / "model" / "metrics.json"

FEATURE_COLUMNS = [
    "Pregnancies",
    "Glucose",
    "BloodPressure",
    "SkinThickness",
    "Insulin",
    "BMI",
    "DiabetesPedigreeFunction",
    "Age",
]
TARGET_COLUMN = "Outcome"

# Columns where a recorded 0 is biologically implausible and really means
# "missing" in the Pima Indians Diabetes Dataset.
ZERO_AS_MISSING_COLUMNS = ["Glucose", "BloodPressure", "SkinThickness", "Insulin", "BMI"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("train_model")


# --------------------------------------------------------------------------- #
# Data containers
# --------------------------------------------------------------------------- #

@dataclass
class ModelResult:
    """Holds evaluation results for a single trained model."""

    name: str
    estimator: Any
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: float
    confusion: list = field(default_factory=list)
    fpr: list = field(default_factory=list)
    tpr: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "roc_auc": round(self.roc_auc, 4),
            "confusion_matrix": self.confusion,
        }


# --------------------------------------------------------------------------- #
# Preprocessing
# --------------------------------------------------------------------------- #

def load_raw_data(path: Path = DATA_PATH) -> pd.DataFrame:
    """Load the raw CSV dataset from disk."""
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {path}. Place the Pima Indians Diabetes "
            f"Dataset CSV there (see data/README note in docs/installation.md)."
        )
    logger.info("Loading raw dataset from %s", path)
    return pd.read_csv(path)


def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the raw dataset:
        - drop exact duplicate rows
        - treat biologically-impossible zeros as missing (NaN)
        - impute missing values with the median of each column
        - clip extreme outliers to the 1st/99th percentile (winsorising)
    """
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    logger.info("Dropped %d duplicate rows", before - len(df))

    df = df.copy()
    for col in ZERO_AS_MISSING_COLUMNS:
        df[col] = df[col].replace(0, np.nan)

    missing_report = df[FEATURE_COLUMNS].isna().sum()
    logger.info("Missing values per column before imputation:\n%s", missing_report)

    for col in ZERO_AS_MISSING_COLUMNS:
        median = df[col].median()
        df[col] = df[col].fillna(median)

    # Winsorise outliers per feature at the 1st/99th percentile.
    for col in FEATURE_COLUMNS:
        lower, upper = df[col].quantile(0.01), df[col].quantile(0.99)
        df[col] = df[col].clip(lower, upper)

    return df


def build_train_test_split(
    df: pd.DataFrame, test_size: float = 0.2, random_state: int = 42
):
    """Split features/target into stratified 80/20 train and test sets."""
    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN]
    return train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )


# --------------------------------------------------------------------------- #
# Model training & comparison
# --------------------------------------------------------------------------- #

def get_candidate_models() -> dict[str, Any]:
    """Return the dictionary of candidate models to train and compare."""
    return {
        "Logistic Regression": LogisticRegression(max_iter=1000, random_state=42),
        "Decision Tree": DecisionTreeClassifier(max_depth=5, random_state=42),
        "Random Forest": RandomForestClassifier(
            n_estimators=300, max_depth=8, random_state=42
        ),
        "Support Vector Machine": SVC(
            kernel="rbf", probability=True, random_state=42
        ),
        "K-Nearest Neighbours": KNeighborsClassifier(n_neighbors=11),
        "Gradient Boosting": GradientBoostingClassifier(
            n_estimators=200, max_depth=3, random_state=42
        ),
    }


def evaluate_model(name: str, model: Any, X_test, y_test) -> ModelResult:
    """Compute accuracy/precision/recall/F1/ROC-AUC and confusion matrix."""
    y_pred = model.predict(X_test)
    if hasattr(model, "predict_proba"):
        y_proba = model.predict_proba(X_test)[:, 1]
    else:
        y_proba = model.decision_function(X_test)

    fpr, tpr, _ = roc_curve(y_test, y_proba)

    return ModelResult(
        name=name,
        estimator=model,
        accuracy=accuracy_score(y_test, y_pred),
        precision=precision_score(y_test, y_pred, zero_division=0),
        recall=recall_score(y_test, y_pred, zero_division=0),
        f1=f1_score(y_test, y_pred, zero_division=0),
        roc_auc=roc_auc_score(y_test, y_proba),
        confusion=confusion_matrix(y_test, y_pred).tolist(),
        fpr=fpr.tolist(),
        tpr=tpr.tolist(),
    )


def train_and_compare(X_train, y_train, X_test, y_test) -> list[ModelResult]:
    """Train every candidate model and evaluate each on the held-out test set."""
    results = []
    for name, model in get_candidate_models().items():
        logger.info("Training %s ...", name)
        model.fit(X_train, y_train)
        result = evaluate_model(name, model, X_test, y_test)
        logger.info(
            "%s -> acc=%.4f precision=%.4f recall=%.4f f1=%.4f roc_auc=%.4f",
            name, result.accuracy, result.precision, result.recall,
            result.f1, result.roc_auc,
        )
        results.append(result)
    return results


def select_best_model(results: list[ModelResult]) -> ModelResult:
    """Pick the model with the highest F1 score (balances precision/recall,
    which matters more than raw accuracy for an imbalanced medical dataset)."""
    best = max(results, key=lambda r: r.f1)
    logger.info("Selected best model: %s (F1=%.4f)", best.name, best.f1)
    return best


# --------------------------------------------------------------------------- #
# Main pipeline
# --------------------------------------------------------------------------- #

def main() -> None:
    df_raw = load_raw_data()
    df_clean = clean_dataset(df_raw)
    df_clean.to_csv(PROCESSED_PATH, index=False)
    logger.info("Saved cleaned dataset to %s", PROCESSED_PATH)

    X_train, X_test, y_train, y_test = build_train_test_split(df_clean)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    results = train_and_compare(X_train_scaled, y_train, X_test_scaled, y_test)
    best = select_best_model(results)

    joblib.dump(best.estimator, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    logger.info("Saved best model to %s", MODEL_PATH)
    logger.info("Saved scaler to %s", SCALER_PATH)

    summary = {
        "best_model": best.name,
        "feature_order": FEATURE_COLUMNS,
        "models": [r.as_dict() for r in results],
    }
    METRICS_PATH.write_text(json.dumps(summary, indent=2))
    logger.info("Saved metrics summary to %s", METRICS_PATH)

    print("\n=== Model Comparison ===")
    table = pd.DataFrame([r.as_dict() for r in results]).drop(columns=["confusion_matrix"])
    print(table.sort_values("f1", ascending=False).to_string(index=False))
    print(f"\nBest model selected: {best.name}")


if __name__ == "__main__":
    main()
