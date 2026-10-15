"""
app.py
-------
Flask application factory for the Diabetes Prediction web app.

This is a second interface onto the exact same backend the desktop app
(app/main.py) uses: same SQLite database (app/database.py), same trained
model (app/predictor.py), same validation (app/validators.py), same PDF
generation (app/report_generator.py). Nothing in app/ is modified or
duplicated -- this module only wires that existing backend up to Flask,
Flask-Login, and Flask-WTF's CSRF protection.

Run:
    python webapp/app.py    (from the project root, after training the model
                              -- see docs/installation.md)
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from datetime import datetime

from flask import Flask
from flask_login import LoginManager
from flask_wtf import CSRFProtect

from app.branding import BRAND_FULL_NAME, BRAND_ICON, BRAND_SHORT_NAME, BRAND_TAGLINE
from app.database import Database
from app.predictor import DiabetesPredictor, ModelNotFoundError
from webapp.auth import WebUser
from webapp.config import Config
from webapp.routes import register_blueprints


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    secret_key = app.config.get("SECRET_KEY")
    if isinstance(secret_key, str) and not secret_key.strip():
        secret_key = None
    production = (
        os.environ.get("RENDER", "").lower() == "true"
        or os.environ.get("FLASK_ENV", "").lower() == "production"
    )
    if production and (
        not isinstance(secret_key, str) or len(secret_key.strip()) < 32
    ):
        raise RuntimeError(
            "SECRET_KEY must be configured with at least 32 characters in production."
        )
    if not secret_key:
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        app.logger.warning(
            "SECRET_KEY is not set; using a temporary key for local development. "
            "Set SECRET_KEY to keep sessions valid across restarts."
        )

    # -- shared backend: one Database + one DiabetesPredictor per process,
    # exactly like the desktop app's App class in main.py. sqlite3
    # connections are opened/closed per-call inside Database, so sharing
    # this single instance across Flask's request threads is safe. -- #
    app.db = Database()
    try:
        app.predictor = DiabetesPredictor()
        app.model_error = None
    except ModelNotFoundError as exc:
        app.predictor = None
        app.model_error = str(exc)
        app.logger.error("Prediction model is unavailable: %s", exc)

    CSRFProtect(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(username: str):
        return WebUser(username) if app.db.get_user(username) else None

    register_blueprints(app)

    @app.context_processor
    def inject_brand():
        """Available in every template without each view passing it explicitly --
        the same brand identity (name/icon/tagline) the desktop app uses."""
        return {
            "brand_full_name": BRAND_FULL_NAME,
            "brand_short_name": BRAND_SHORT_NAME,
            "brand_icon": BRAND_ICON,
            "brand_tagline": BRAND_TAGLINE,
            "current_year": datetime.now().year,
        }

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
