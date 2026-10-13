"""
utils.py
---------
Small, reusable helpers shared across the application: logging setup,
password hashing, PDF report generation, and misc formatting helpers.
Keeping these in one module avoids duplicating boilerplate in main.py,
database.py, and predictor.py.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_logger(name: str) -> logging.Logger:
    """Return a module-level logger that writes to both console and a
    rotating-ish daily log file under /logs. Called once per module."""
    logger = logging.getLogger(name)
    if logger.handlers:  # avoid duplicate handlers on repeated calls
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_file = LOG_DIR / f"{datetime.now():%Y-%m-%d}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """
    Hash a password with PBKDF2-HMAC-SHA256 and a random salt.
    Returns (hashed_hex, salt_hex). Store both in the database.
    """
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000
    )
    return hashed.hex(), salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    """Verify a plaintext password against a stored hash + salt."""
    candidate, _ = hash_password(password, salt)
    return secrets.compare_digest(candidate, hashed)


def risk_level(probability: float) -> str:
    """Map a diabetes probability (0-1) to a traffic-light risk band."""
    if probability < 0.34:
        return "Green"
    if probability < 0.67:
        return "Yellow"
    return "Red"


def risk_suggestions(level: str) -> list[str]:
    """Return lifestyle suggestions appropriate to the risk band.

    These are general wellness pointers, not medical advice — the app
    always recommends a licensed clinician for diagnosis and treatment.
    """
    common = ["Consult a doctor for a confirmed clinical diagnosis."]
    if level == "Green":
        return common + [
            "Maintain a balanced diet rich in whole grains and vegetables.",
            "Keep up regular physical activity (150+ minutes/week).",
        ]
    if level == "Yellow":
        return common + [
            "Reduce refined sugar and processed carbohydrate intake.",
            "Aim for at least 30 minutes of moderate exercise most days.",
            "Schedule a routine blood glucose check.",
        ]
    return common + [
        "Book a clinical consultation soon for a confirmed diagnosis.",
        "Monitor blood glucose levels closely.",
        "Adopt a low-glycemic, portion-controlled diet under medical guidance.",
        "Increase physical activity gradually, as advised by a professional.",
    ]


def format_timestamp(dt: datetime | None = None) -> str:
    """Consistent timestamp format used throughout the app and database."""
    dt = dt or datetime.now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def ensure_dirs(paths: Iterable[Path]) -> None:
    """Create any missing directories in `paths`."""
    for p in paths:
        os.makedirs(p, exist_ok=True)
