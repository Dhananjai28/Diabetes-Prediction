# Architecture

## Overview

The project is split into three independent layers so that each can be
developed, tested, and reasoned about in isolation:

```
┌─────────────────────────────┐
│   app/main.py (GUI layer)   │  CustomTkinter windows & event handlers
└──────────────┬───────────────┘
               │ calls
┌──────────────▼───────────────┐
│ app/predictor.py, database.py │  Business logic: inference, persistence
│ app/validators.py, utils.py    │  Validation & shared helpers
└──────────────┬───────────────┘
               │ loads artifacts from
┌──────────────▼───────────────┐
│  model/train_model.py         │  Offline training pipeline
│  model/diabetes_model.pkl      │  Persisted best model
│  model/scaler.pkl               │  Persisted StandardScaler
└───────────────────────────────┘
```

## Module responsibilities

| Module | Responsibility |
|---|---|
| `model/train_model.py` | Loads raw data, cleans it, trains 6 classifiers, selects the best by F1, persists `diabetes_model.pkl` + `scaler.pkl` + `metrics.json`. Run offline, not at app startup. |
| `model/evaluate_model.py` | Generates all EDA and evaluation plots (histograms, heatmap, boxplots, ROC, confusion matrix, feature importance) into `/screenshots`. |
| `app/predictor.py` | Loads the persisted model/scaler once; exposes `DiabetesPredictor.predict(inputs) -> PredictionOutcome`. No Tkinter code, so it is independently unit-testable. |
| `app/database.py` | SQLite access layer: `users`, `prediction_history`, `settings` tables. All queries are parameterised. Wraps every write in a transaction with rollback on error. |
| `app/validators.py` | Pure functions validating form fields (ranges, types, SQL-injection patterns) and auth fields (username/password/email rules). No side effects. |
| `app/theme.py` | Centralised color palette, fonts, and a `ThemeManager` that persists the light/dark choice per user via `settings`. |
| `app/utils.py` | Logging setup, password hashing (PBKDF2-HMAC-SHA256 + per-user salt), risk-level/suggestion mapping, timestamp formatting. |
| `app/main.py` | A single persistent `App(ctk.CTk)` root window that swaps `ctk.CTkFrame` screens in and out of itself: `LoginFrame`, `RegisterFrame`, `ForgotPasswordFrame`, `DashboardFrame` (sidebar + Overview/Prediction/History/About/Help tabs). `SplashScreen` is a `ctk.CTkToplevel` shown once at startup. |

## Why this split?

- **Testability** — `predictor.py`, `database.py`, and `validators.py` have
  zero GUI dependencies, so `tests/` can exercise real logic without
  spinning up any windows.
- **Single source of truth for styling** — every window pulls colors/fonts
  from `theme.py` instead of hard-coding hex values, so a future re-skin
  touches one file.
- **Security by layering** — validators reject malformed/SQL-injection-like
  input early with friendly messages; the database layer additionally uses
  parameterised queries regardless, so no single layer is a single point of
  failure.
- **Offline vs. online separation** — training is a deliberate, logged,
  repeatable offline step (`train_model.py`) that produces artifacts the GUI
  simply loads; the GUI never re-trains at runtime.

## GUI architecture: one root window, many frames

CustomTkinter (like the Tkinter it wraps) only supports **one** root window
(`ctk.CTk()`) per process — it owns the single underlying Tcl interpreter.
`App(ctk.CTk)` is created exactly once and lives for the whole program.
Every screen is a `ctk.CTkFrame` that `App.switch_to()` packs into and
destroys from that single root, resizing/centering the root window to match
each screen's dimensions. The splash screen is the one exception — it's a
`ctk.CTkToplevel` (a *child* window), which is safe to create because it
isn't a second root.

## Gotcha: don't name a method `_register`

Every Tkinter widget has an internal method called `_register`
(`tkinter.Misc._register`), used for callback bookkeeping. An earlier
version of the registration screen named its submit handler `_register`,
which silently **overrode** that internal method on the widget instance.
When CustomTkinter's internals later tried to call the real `_register` for
something unrelated, it hit the app's version instead and crashed with
`_register() takes 1 positional argument but N were given`. The fix: the
registration handler is named `_handle_register`, not `_register`. More
generally, avoid naming any widget subclass method the same as a
Tkinter/Misc internal (`_register`, `_options`, `_configure`,
`_nametowidget`, `config`, `bind`, `after`, etc.) unless you're
deliberately overriding it.

## Data flow for a single prediction

1. User fills the 8-field form in `DashboardFrame._show_prediction`.
2. `validators.validate_prediction_form()` checks ranges/types/injection.
3. `DiabetesPredictor.predict()` scales the input with the persisted
   `scaler.pkl` and calls the persisted `diabetes_model.pkl`.
4. The result (`label`, `probability`, `risk`, `suggestions`) is rendered in
   the UI and simultaneously persisted via `Database.add_prediction()`.
