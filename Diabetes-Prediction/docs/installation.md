# Installation Guide

## Prerequisites

- Python 3.12+
- pip
- (Windows/macOS/Linux all supported — CustomTkinter is cross-platform)

## 1. Clone and enter the project

```bash
git clone https://github.com/<your-username>/Diabetes-Prediction.git
cd Diabetes-Prediction
```

## 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Provide the dataset

`data/diabetes.csv` ships with a statistically-realistic **synthetic**
stand-in for the Pima Indians Diabetes Dataset (same columns, same
approximate feature means/std-devs and outcome rate — see the header note
in `model/train_model.py`'s docstring). For a portfolio/production run,
replace it with the real dataset:

- Kaggle: search "Pima Indians Diabetes Database"
- UCI Machine Learning Repository: "Pima Indians Diabetes Dataset"

Keep the same column names: `Pregnancies, Glucose, BloodPressure,
SkinThickness, Insulin, BMI, DiabetesPedigreeFunction, Age, Outcome`.

## 5. Train the model

```bash
python model/train_model.py
```

This creates `model/diabetes_model.pkl`, `model/scaler.pkl`,
`model/metrics.json`, and `data/processed.csv`.

## 6. (Optional) Generate EDA/evaluation plots

```bash
python model/evaluate_model.py
```

Plots are written to `/screenshots`.

## 7. Run the application

```bash
python app/main.py
```

On first run, register an account from the login screen, then log in.

## 8. Run the test suite

```bash
python -m unittest discover tests
```

## Troubleshooting

| Issue | Fix |
|---|---|
| `ModelNotFoundError` when opening the app | Run `python model/train_model.py` first. |
| `ModuleNotFoundError: customtkinter` | Re-run `pip install -r requirements.txt` inside your active virtual environment. |
| Tkinter not found (Linux) | Install your distro's Tk package, e.g. `sudo apt install python3-tk`. |
| Blank/garbled fonts | The app defaults to "Segoe UI"; on Linux/macOS Tk will substitute a system font automatically — this doesn't affect functionality. |
