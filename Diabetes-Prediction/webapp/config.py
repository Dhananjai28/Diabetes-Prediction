"""
config.py
----------
Flask configuration for the web application. Kept minimal and separate
from app.py so config values (secret key, CSRF settings) don't get lost in
app-factory wiring.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # project root (same as app/'s ROOT_DIR)


class Config:
    # In production, set the SECRET_KEY environment variable to a long
    # random value -- this fallback is fine for local development only.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    WTF_CSRF_ENABLED = True
    TEMPLATES_AUTO_RELOAD = True

    # Session cookies expire when the browser closes by default; Flask-Login
    # handles "remember me" separately if added later.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Where generated PDF reports are temporarily written before being
    # streamed to the browser and cleaned up (see webapp/reports.py).
    REPORT_TEMP_DIR = BASE_DIR / "webapp" / "_tmp_reports"
