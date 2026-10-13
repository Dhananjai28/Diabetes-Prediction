"""
evaluate_model.py
------------------
Generates the exploratory data analysis (EDA) and model-evaluation plots for
the Diabetes Prediction project, and saves them to /screenshots so they can
be embedded in the README and docs/screenshots.md.

Must be run AFTER model/train_model.py (it reuses the saved model, scaler,
and processed dataset).

Run directly:
    python model/evaluate_model.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")  # headless-safe backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import ConfusionMatrixDisplay, RocCurveDisplay

ROOT_DIR = Path(__file__).resolve().parent.parent
PROCESSED_PATH = ROOT_DIR / "data" / "processed.csv"
MODEL_PATH = ROOT_DIR / "model" / "diabetes_model.pkl"
SCALER_PATH = ROOT_DIR / "model" / "scaler.pkl"
METRICS_PATH = ROOT_DIR / "model" / "metrics.json"
PLOTS_DIR = ROOT_DIR / "screenshots"

FEATURE_COLUMNS = [
    "Pregnancies", "Glucose", "BloodPressure", "SkinThickness",
    "Insulin", "BMI", "DiabetesPedigreeFunction", "Age",
]

sns.set_theme(style="whitegrid")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("evaluate_model")


def save_fig(fig, name: str) -> None:
    path = PLOTS_DIR / name
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved plot: %s", path)


def plot_histograms(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 4, figsize=(18, 8))
    for ax, col in zip(axes.flatten(), FEATURE_COLUMNS):
        sns.histplot(df[col], kde=True, ax=ax, color="#3b82f6")
        ax.set_title(col)
    fig.suptitle("Feature Distributions (Histograms)")
    fig.tight_layout()
    save_fig(fig, "01_histograms.png")
    # Observation: Glucose, BMI, and Age are right-skewed; Insulin shows the
    # heaviest skew, consistent with real-world clinical measurement spread.


def plot_correlation_heatmap(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 7))
    corr = df[FEATURE_COLUMNS + ["Outcome"]].corr()
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", ax=ax)
    ax.set_title("Correlation Matrix")
    save_fig(fig, "02_correlation_heatmap.png")
    # Observation: Glucose has the strongest correlation with Outcome,
    # followed by BMI and Age -- consistent with clinical expectations.


def plot_outcome_countplot(df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.countplot(x="Outcome", data=df, palette=["#22c55e", "#ef4444"], ax=ax)
    ax.set_xticklabels(["Non-Diabetic", "Diabetic"])
    ax.set_title("Class Balance")
    save_fig(fig, "03_outcome_countplot.png")
    # Observation: the dataset is moderately imbalanced (~65/35), which is
    # why F1 score rather than raw accuracy is used to select the best model.


def plot_boxplots(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 4, figsize=(18, 8))
    for ax, col in zip(axes.flatten(), FEATURE_COLUMNS):
        sns.boxplot(x="Outcome", y=col, data=df, ax=ax, palette=["#22c55e", "#ef4444"])
        ax.set_title(col)
    fig.suptitle("Feature Spread by Outcome (Boxplots)")
    fig.tight_layout()
    save_fig(fig, "04_boxplots.png")
    # Observation: Glucose and BMI show the clearest separation in median
    # values between diabetic and non-diabetic groups.


def plot_distributions_by_outcome(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 4, figsize=(18, 8))
    for ax, col in zip(axes.flatten(), FEATURE_COLUMNS):
        sns.kdeplot(
            data=df, x=col, hue="Outcome", fill=True, common_norm=False,
            palette=["#22c55e", "#ef4444"], ax=ax,
        )
        ax.set_title(col)
    fig.suptitle("Distribution by Outcome (KDE)")
    fig.tight_layout()
    save_fig(fig, "05_distribution_by_outcome.png")
    # Observation: Glucose distributions for the two classes are the most
    # visibly separated, reinforcing its predictive importance.


def plot_feature_importance(model) -> None:
    if not hasattr(model, "feature_importances_"):
        logger.info("Model has no feature_importances_ attribute, skipping plot.")
        return
    importances = pd.Series(model.feature_importances_, index=FEATURE_COLUMNS)
    importances = importances.sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(8, 6))
    importances.plot(kind="barh", ax=ax, color="#6366f1")
    ax.set_title(f"Feature Importance ({type(model).__name__})")
    save_fig(fig, "06_feature_importance.png")
    # Observation: Glucose and BMI dominate the model's decision-making,
    # matching the correlation and boxplot findings above.


def plot_confusion_and_roc(df: pd.DataFrame, model, scaler) -> None:
    from sklearn.model_selection import train_test_split

    X = df[FEATURE_COLUMNS]
    y = df["Outcome"]
    _, X_test, _, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    X_test_scaled = scaler.transform(X_test)

    fig, ax = plt.subplots(figsize=(5, 5))
    ConfusionMatrixDisplay.from_estimator(
        model, X_test_scaled, y_test, ax=ax, cmap="Blues",
        display_labels=["Non-Diabetic", "Diabetic"],
    )
    ax.set_title("Confusion Matrix (Best Model)")
    save_fig(fig, "07_confusion_matrix.png")

    fig, ax = plt.subplots(figsize=(5, 5))
    RocCurveDisplay.from_estimator(model, X_test_scaled, y_test, ax=ax)
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray")
    ax.set_title("ROC Curve (Best Model)")
    save_fig(fig, "08_roc_curve.png")
    # Observation: the ROC curve sits well above the diagonal, indicating the
    # model discriminates diabetic vs non-diabetic cases substantially
    # better than chance.


def main() -> None:
    PLOTS_DIR.mkdir(exist_ok=True)
    df = pd.read_csv(PROCESSED_PATH)
    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    metrics = json.loads(METRICS_PATH.read_text())

    plot_histograms(df)
    plot_correlation_heatmap(df)
    plot_outcome_countplot(df)
    plot_boxplots(df)
    plot_distributions_by_outcome(df)
    plot_feature_importance(model)
    plot_confusion_and_roc(df, model, scaler)

    logger.info("Best model per metrics.json: %s", metrics["best_model"])
    logger.info("All plots saved to %s", PLOTS_DIR)


if __name__ == "__main__":
    main()
