"""
theme.py
---------
Centralised color palette, fonts, and spacing constants for the CustomTkinter
GUI, plus a ThemeManager that persists the user's light/dark choice between
sessions (backed by the `settings` table in database.py).

Keeping styling here means every window (login, dashboard, prediction,
history, ...) pulls from one source of truth instead of hard-coding colors.
"""

from __future__ import annotations

import customtkinter as ctk

# --------------------------------------------------------------------------- #
# Brand
# --------------------------------------------------------------------------- #
# Centralised here (not in main.py) so every screen pulls the same wording,
# the same way every screen pulls the same colors below.

BRAND_FULL_NAME = "Professional Diabetes Prediction & Patient Management System"
BRAND_SHORT_NAME = "Diabetes Prediction"
BRAND_TAGLINE = "Patient Management System"
BRAND_ICON = "🩺"

# --------------------------------------------------------------------------- #
# Palette -- a clinical teal/navy scheme (professional medical-portal look)
# rather than a generic app-blue, matching the project's "Professional
# Diabetes Prediction & Patient Management System" positioning.
# --------------------------------------------------------------------------- #

COLORS = {
    "light": {
        "bg": "#F3F7F8",
        "surface": "#FFFFFF",
        "sidebar": "#0B3B45",
        "sidebar_text": "#D7E7E9",
        "primary": "#0F766E",
        "primary_hover": "#0D9488",
        "accent": "#6366F1",
        "text": "#0F2B33",
        "muted_text": "#5B7B82",
        "success": "#15803D",
        "warning": "#B45309",
        "danger": "#B91C1C",
        "danger_hover": "#7F1D1D",
        "border": "#DCE7EA",
    },
    "dark": {
        "bg": "#0B1A1F",
        "surface": "#12262C",
        "sidebar": "#081418",
        "sidebar_text": "#C7DADD",
        "primary": "#14B8A6",
        "primary_hover": "#2DD4BF",
        "accent": "#A78BFA",
        "text": "#E7F1F2",
        "muted_text": "#8FA9AE",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "danger": "#EF4444",
        "danger_hover": "#DC2626",
        "border": "#1E3A40",
    },
}

RISK_COLORS = {
    "Green": {"light": "#15803D", "dark": "#22C55E"},
    "Yellow": {"light": "#B45309", "dark": "#F59E0B"},
    "Red": {"light": "#B91C1C", "dark": "#EF4444"},
}

FONT_FAMILY = "Segoe UI"
DATA_FONT_FAMILY = "Consolas"  # monospace readout face for clinical numbers
# (probabilities, vitals-style values) -- gives the portal a clinical
# "monitor readout" character instead of using the UI face for everything.

FONTS = {
    "h1": (FONT_FAMILY, 26, "bold"),
    "h2": (FONT_FAMILY, 19, "bold"),
    "h3": (FONT_FAMILY, 15, "bold"),
    "body": (FONT_FAMILY, 13),
    "small": (FONT_FAMILY, 11),
    "button": (FONT_FAMILY, 13, "bold"),
    "data_lg": (DATA_FONT_FAMILY, 28, "bold"),
    "data": (DATA_FONT_FAMILY, 15, "bold"),
}

RADIUS = 12
PADDING = 16


class ThemeManager:
    """Reads/writes the persisted theme preference and applies it globally."""

    def __init__(self, db, username: str | None = None):
        self.db = db
        self.username = username
        self.mode = self._load_saved_mode()
        self.apply()

    def _load_saved_mode(self) -> str:
        saved = self.db.get_setting(self.username, "theme") if self.username else None
        return saved or "dark"

    def colors(self) -> dict:
        return COLORS[self.mode]

    def toggle(self) -> str:
        self.mode = "light" if self.mode == "dark" else "dark"
        self.apply()
        if self.username:
            self.db.set_setting(self.username, "theme", self.mode)
        return self.mode

    def apply(self) -> None:
        ctk.set_appearance_mode(self.mode)
        ctk.set_default_color_theme("blue")
