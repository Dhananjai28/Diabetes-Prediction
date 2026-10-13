"""
database.py
------------
SQLite data-access layer for the Diabetes Prediction application.

Tables:
    users              -- registered accounts (hashed passwords, never plaintext)
    prediction_history  -- every prediction made, tied to a username
    settings            -- per-user key/value preferences (e.g. theme)
    patient_profile     -- exactly one patient profile per user

All queries use parameterised statements ("?" placeholders) — never string
formatting — which is the standard defense against SQL injection regardless
of what validators.py already rejects at the UI layer.
"""

from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.utils import format_timestamp, hash_password, setup_logger, verify_password

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "app" / "assets" / "diabetes_app.db"

logger = setup_logger("database")


class DatabaseError(Exception):
    """Raised for any recoverable database-layer failure."""


class Database:
    """Thin wrapper around sqlite3 exposing typed, validated operations."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    # -- connection helpers ------------------------------------------------ #

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            logger.exception("Database error, rolled back transaction.")
            raise DatabaseError(str(exc)) from exc
        finally:
            conn.close()

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    username        TEXT UNIQUE NOT NULL,
                    email           TEXT UNIQUE NOT NULL,
                    password_hash   TEXT NOT NULL,
                    salt            TEXT NOT NULL,
                    security_answer_hash TEXT NOT NULL,
                    security_answer_salt TEXT NOT NULL,
                    created_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS prediction_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    username        TEXT NOT NULL,
                    created_at      TEXT NOT NULL,
                    pregnancies     REAL,
                    glucose         REAL,
                    blood_pressure  REAL,
                    skin_thickness  REAL,
                    insulin         REAL,
                    bmi             REAL,
                    dpf             REAL,
                    age             REAL,
                    prediction      TEXT NOT NULL,
                    probability     REAL NOT NULL,
                    risk_level      TEXT NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS settings (
                    username    TEXT NOT NULL,
                    key         TEXT NOT NULL,
                    value       TEXT NOT NULL,
                    PRIMARY KEY (username, key)
                );

                CREATE TABLE IF NOT EXISTS patient_profile (
                    profile_id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    username                TEXT UNIQUE NOT NULL,
                    patient_name            TEXT NOT NULL,
                    gender                  TEXT NOT NULL,
                    date_of_birth           TEXT NOT NULL,
                    age                     INTEGER NOT NULL,
                    blood_group             TEXT NOT NULL,
                    phone                   TEXT NOT NULL,
                    email                   TEXT NOT NULL,
                    height                  REAL NOT NULL,
                    weight                  REAL NOT NULL,
                    bmi                     REAL NOT NULL,
                    address                 TEXT,
                    emergency_contact_name  TEXT,
                    emergency_contact_number TEXT,
                    created_at              TEXT NOT NULL,
                    updated_at              TEXT NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
                );
                """
            )
        logger.info("Database schema ready at %s", self.db_path)

    # -- users --------------------------------------------------------------- #

    def create_user(
        self, username: str, email: str, password: str, security_answer: str
    ) -> None:
        if self.get_user(username) is not None:
            raise DatabaseError(f"Username '{username}' is already taken.")
        if self.get_user_by_email(email) is not None:
            raise DatabaseError(f"An account with email '{email}' already exists.")

        pw_hash, pw_salt = hash_password(password)
        ans_hash, ans_salt = hash_password(security_answer.lower().strip())

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO users
                   (username, email, password_hash, salt,
                    security_answer_hash, security_answer_salt, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (username, email, pw_hash, pw_salt, ans_hash, ans_salt,
                 format_timestamp()),
            )
        logger.info("Created new user account: %s", username)

    def get_user(self, username: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
            return cur.fetchone()

    def get_user_by_email(self, email: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM users WHERE email = ?", (email,))
            return cur.fetchone()

    def authenticate(self, username: str, password: str) -> bool:
        user = self.get_user(username)
        if user is None:
            return False
        return verify_password(password, user["password_hash"], user["salt"])

    def verify_security_answer(self, username: str, answer: str) -> bool:
        user = self.get_user(username)
        if user is None:
            return False
        return verify_password(
            answer.lower().strip(),
            user["security_answer_hash"],
            user["security_answer_salt"],
        )

    def reset_password(self, username: str, new_password: str) -> None:
        pw_hash, pw_salt = hash_password(new_password)
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
                (pw_hash, pw_salt, username),
            )
            if cur.rowcount == 0:
                raise DatabaseError(f"No such user: {username}")
        logger.info("Password reset for user: %s", username)

    # -- prediction history --------------------------------------------------- #

    def add_prediction(
        self,
        username: str,
        inputs: dict[str, float],
        prediction: str,
        probability: float,
        risk_level: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO prediction_history
                   (username, created_at, pregnancies, glucose, blood_pressure,
                    skin_thickness, insulin, bmi, dpf, age, prediction,
                    probability, risk_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    username, format_timestamp(),
                    inputs.get("Pregnancies"), inputs.get("Glucose"),
                    inputs.get("BloodPressure"), inputs.get("SkinThickness"),
                    inputs.get("Insulin"), inputs.get("BMI"),
                    inputs.get("DiabetesPedigreeFunction"), inputs.get("Age"),
                    prediction, probability, risk_level,
                ),
            )
        logger.info("Saved prediction for %s: %s (%.1f%%)", username, prediction,
                    probability * 100)

    def get_history(self, username: str, search: str = "") -> list[sqlite3.Row]:
        query = "SELECT * FROM prediction_history WHERE username = ?"
        params: list[Any] = [username]
        if search:
            query += " AND (prediction LIKE ? OR risk_level LIKE ? OR created_at LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like])
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            cur = conn.execute(query, params)
            return cur.fetchall()

    def delete_prediction(self, record_id: int, username: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM prediction_history WHERE id = ? AND username = ?",
                (record_id, username),
            )
        logger.info("Deleted prediction record %s for %s", record_id, username)

    def clear_history(self, username: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM prediction_history WHERE username = ?", (username,)
            )
        logger.info("Cleared all prediction history for %s", username)

    def export_history_to_csv(self, username: str, out_path: Path) -> Path:
        rows = self.get_history(username)
        headers = rows[0].keys() if rows else [
            "id", "username", "created_at", "pregnancies", "glucose",
            "blood_pressure", "skin_thickness", "insulin", "bmi", "dpf",
            "age", "prediction", "probability", "risk_level",
        ]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in rows:
                writer.writerow([row[h] for h in headers])
        logger.info("Exported %d history rows for %s to %s", len(rows), username, out_path)
        return out_path

    # -- settings -------------------------------------------------------------- #

    def get_setting(self, username: str, key: str) -> str | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT value FROM settings WHERE username = ? AND key = ?",
                (username, key),
            )
            row = cur.fetchone()
            return row["value"] if row else None

    def set_setting(self, username: str, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO settings (username, key, value) VALUES (?, ?, ?)
                   ON CONFLICT(username, key) DO UPDATE SET value = excluded.value""",
                (username, key, value),
            )

    # -- patient profile ------------------------------------------------------- #
    # Exactly one profile per user: get_profile() is the single source of
    # truth for whether a profile exists, and upsert_profile() always checks
    # first so a second save UPDATEs the existing row instead of creating a
    # duplicate (the UNIQUE constraint on `username` is a DB-level backstop
    # for that same guarantee).

    def get_profile(self, username: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM patient_profile WHERE username = ?", (username,)
            )
            return cur.fetchone()

    def upsert_profile(
        self,
        username: str,
        patient_name: str,
        gender: str,
        date_of_birth: str,
        age: int,
        blood_group: str,
        phone: str,
        email: str,
        height: float,
        weight: float,
        bmi: float,
        address: str,
        emergency_contact_name: str,
        emergency_contact_number: str,
    ) -> None:
        now = format_timestamp()
        existing = self.get_profile(username)

        with self._connect() as conn:
            if existing is not None:
                conn.execute(
                    """UPDATE patient_profile SET
                        patient_name = ?, gender = ?, date_of_birth = ?, age = ?,
                        blood_group = ?, phone = ?, email = ?, height = ?,
                        weight = ?, bmi = ?, address = ?,
                        emergency_contact_name = ?, emergency_contact_number = ?,
                        updated_at = ?
                       WHERE username = ?""",
                    (
                        patient_name, gender, date_of_birth, age, blood_group,
                        phone, email, height, weight, bmi, address,
                        emergency_contact_name, emergency_contact_number,
                        now, username,
                    ),
                )
                logger.info("Updated patient profile for %s", username)
            else:
                conn.execute(
                    """INSERT INTO patient_profile
                       (username, patient_name, gender, date_of_birth, age,
                        blood_group, phone, email, height, weight, bmi, address,
                        emergency_contact_name, emergency_contact_number,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        username, patient_name, gender, date_of_birth, age,
                        blood_group, phone, email, height, weight, bmi, address,
                        emergency_contact_name, emergency_contact_number, now, now,
                    ),
                )
                logger.info("Created patient profile for %s", username)
