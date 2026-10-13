# Development & ML Workflow

## 1. Data preparation

`model/train_model.py::clean_dataset()`:
1. Drop exact duplicate rows.
2. Treat biologically-impossible zeros (`Glucose`, `BloodPressure`,
   `SkinThickness`, `Insulin`, `BMI`) as missing values.
3. Impute missing values with the column median.
4. Winsorise outliers to the 1st/99th percentile per feature.

The cleaned dataset is saved to `data/processed.csv` for transparency and
reuse by `evaluate_model.py`.

## 2. Train / test split

An 80/20 stratified split (`sklearn.model_selection.train_test_split`,
`stratify=y`) keeps the diabetic/non-diabetic ratio consistent between the
training and test sets.

## 3. Feature scaling

`StandardScaler` is fit **only on the training split** and then applied to
both splits, avoiding data leakage from the test set into training.

## 4. Model comparison

Six classifiers are trained with fixed `random_state=42` for reproducibility:

| Model | Notes |
|---|---|
| Logistic Regression | Baseline linear model |
| Decision Tree | `max_depth=5` to limit overfitting |
| Random Forest | 300 trees, `max_depth=8` |
| Support Vector Machine | RBF kernel, `probability=True` for ROC/AUC |
| K-Nearest Neighbours | `n_neighbors=11` |
| Gradient Boosting | 200 estimators, `max_depth=3` |

Each is scored on accuracy, precision, recall, F1, ROC-AUC, and a confusion
matrix. **F1 score** (not accuracy) drives model selection, since the
dataset is moderately imbalanced (~65% non-diabetic / 35% diabetic) and F1
balances precision and recall rather than rewarding the majority class.

## 5. Persistence

The winning model and the fitted scaler are saved with `joblib` to
`model/diabetes_model.pkl` and `model/scaler.pkl`. A `metrics.json` summary
captures every model's scores for the README and `docs/`.

## 6. EDA & evaluation plots

`model/evaluate_model.py` regenerates, from the same cleaned dataset and
saved model:
- Feature histograms
- Correlation heatmap
- Class-balance countplot
- Boxplots per feature by outcome
- KDE distribution plots by outcome
- Feature importance (tree-based models)
- Confusion matrix and ROC curve on the held-out test set

All are written to `/screenshots` and referenced by the README and
`docs/screenshots.md`.

## 7. Application workflow

1. `python model/train_model.py` — train and persist the model (run once,
   or whenever `data/diabetes.csv` changes).
2. `python model/evaluate_model.py` — regenerate plots (optional, for docs).
3. `python app/main.py` — launch the desktop app. Splash screen → Login →
   Register/Forgot Password if needed → Dashboard (Overview, New Prediction,
   History, About, Help).

## 8. Testing workflow

`python -m unittest discover tests` runs:
- `tests/test_validator.py` — field/form/auth validation rules.
- `tests/test_predictor.py` — model loading, inference sanity, and the full
  database lifecycle (create user, authenticate, reset password, prediction
  history CRUD, settings) against a temporary SQLite file.
