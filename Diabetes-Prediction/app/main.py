"""
main.py
--------
Entry point and screen classes for the Diabetes Prediction desktop app,
built with CustomTkinter.

IMPORTANT ARCHITECTURE NOTE:
CustomTkinter (like Tkinter) only supports a single root window (ctk.CTk())
per process, so every screen below is a ctk.CTkFrame swapped in and out of
one persistent App(ctk.CTk) root rather than its own root window; the
splash screen uses ctk.CTkToplevel, a child window, which is safe to create.

Separately: every Tkinter widget has an internal method called `_register`
(tkinter.Misc._register), used for callback bookkeeping. Naming an app
method `_register` on a widget subclass overrides that internal method and
breaks it, producing a `_register() takes 1 positional argument but N were
given` crash. For that reason the registration handler below is named
`_handle_register`, not `_register`.

Screens:
    SplashScreen   -- CTkToplevel shown briefly on startup
    LoginFrame      -- username/password login
    RegisterFrame    -- new account creation
    ForgotPasswordFrame -- security-question password reset
    DashboardFrame   -- sidebar-navigated shell hosting:
        - Overview (stat cards)
        - Prediction tab
        - History tab
        - About tab
        - Help tab

Run:
    python app/main.py    (from the project root, after training the model)
"""

from __future__ import annotations

import sys
import threading
import time
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from datetime import date
from pathlib import Path

import customtkinter as ctk

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import Database, DatabaseError
from app.predictor import DiabetesPredictor, ModelNotFoundError
from app.profile import (
    BLOOD_GROUPS,
    GENDERS,
    MIN_BIRTH_YEAR,
    OTHER_BLOOD_GROUP,
    PatientProfile,
    blood_group_form_values,
    calculate_age,
    calculate_bmi,
    resolve_blood_group,
)
from app.report_generator import (
    generate_history_report,
    generate_prediction_report,
    get_feature_profile_image,
    get_probability_gauge_image,
)
from app.theme import (
    BRAND_FULL_NAME,
    BRAND_ICON,
    BRAND_SHORT_NAME,
    BRAND_TAGLINE,
    COLORS,
    FONTS,
    RADIUS,
    ThemeManager,
)
from app.utils import risk_suggestions, setup_logger
from app.validators import (
    FEATURE_RANGES,
    validate_email,
    validate_password,
    validate_passwords_match,
    validate_prediction_form,
    validate_profile_form,
    validate_username,
)

logger = setup_logger("main")

APP_TITLE = BRAND_FULL_NAME

# Maps prediction_history DB columns (snake_case) back to the
# FEATURE_RANGES-keyed names predictor.py / report_generator.py expect.
# The database already stores all 8 clinical inputs per prediction record
# (see database.py's prediction_history schema), so no schema change is
# needed here -- this is purely a naming-convention bridge.
HISTORY_DB_TO_FEATURE = {
    "pregnancies": "Pregnancies",
    "glucose": "Glucose",
    "blood_pressure": "BloodPressure",
    "skin_thickness": "SkinThickness",
    "insulin": "Insulin",
    "bmi": "BMI",
    "dpf": "DiabetesPedigreeFunction",
    "age": "Age",
}


def _history_row_to_inputs(row) -> dict[str, float]:
    """Reconstruct the 8-field clinical inputs dict (keyed the way
    predictor.py / report_generator.py expect) from a prediction_history
    database row."""
    return {feature: row[db_col] for db_col, feature in HISTORY_DB_TO_FEATURE.items()}


def _prompt_and_generate_prediction_pdf(db: Database, username: str, row) -> None:
    """Shared handler for generating a single-prediction PDF report from a
    stored history record: prompts for a save location, calls
    report_generator.generate_prediction_report(), and shows a success or
    error dialog. Used by both the history list's quick "Generate PDF"
    button and the "Generate PDF Report" button inside the details window,
    so the save-dialog/error-handling logic lives in exactly one place.
    """
    inputs = _history_row_to_inputs(row)
    suggestions = risk_suggestions(row["risk_level"])
    profile_row = db.get_profile(username)
    patient_profile = PatientProfile.from_row(profile_row).report_dict() if profile_row else None

    path = filedialog.asksaveasfilename(
        defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
        initialfile=f"{username}_prediction_{row['id']}.pdf",
    )
    if not path:
        return
    try:
        generate_prediction_report(
            username, inputs, row["prediction"], row["probability"],
            row["risk_level"], suggestions, Path(path),
            patient_profile=patient_profile,
        )
        messagebox.showinfo("Report Saved", f"PDF report saved to:\n{path}")
    except Exception as exc:
        logger.exception("Failed to generate PDF report from history record")
        messagebox.showerror("Report Failed", f"Could not generate PDF report:\n{exc}")


def _make_pulse_line(parent, width: int, height: int, color: str, bg: str) -> tk.Canvas:
    """A small heartbeat/ECG-style line -- the portal's one signature visual
    motif, used under the brand wordmark (splash screen, sidebar) to signal
    "patient monitoring" rather than a generic logo mark. Plain tk.Canvas
    (not a CTk widget) since CustomTkinter has no drawing surface; `bg` must
    match the exact parent background color since Canvas has no transparent
    fill option."""
    canvas = tk.Canvas(parent, width=width, height=height, bg=bg, highlightthickness=0)
    waveform = [
        (0.00, 0.5), (0.16, 0.5), (0.24, 0.5), (0.29, 0.18), (0.34, 0.86),
        (0.39, 0.34), (0.44, 0.5), (0.58, 0.5), (0.66, 0.5), (0.71, 0.22),
        (0.76, 0.80), (0.81, 0.42), (0.86, 0.5), (1.00, 0.5),
    ]
    coords = []
    for fx, fy in waveform:
        coords.extend([fx * width, fy * height])
    canvas.create_line(*coords, fill=color, width=2, capstyle="round", joinstyle="round")
    return canvas


def _make_initials_avatar(parent, size: int, initials: str, bg: str, fill: str,
                           text_color: str) -> tk.Canvas:
    """A filled circle with centered initials -- the profile-picture
    placeholder used whenever no photo has been uploaded (this app doesn't
    implement photo upload at all, so this is always what's shown)."""
    canvas = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0)
    pad = 2
    canvas.create_oval(pad, pad, size - pad, size - pad, fill=fill, outline="")
    canvas.create_text(
        size / 2, size / 2, text=initials, fill=text_color,
        font=("Segoe UI", max(int(size * 0.36), 10), "bold"),
    )
    return canvas

# (width, height) for each screen -- the single root window is resized to
# match whichever screen is currently showing.
SCREEN_SIZES = {
    "login": (420, 560),
    "register": (440, 660),
    "forgot_password": (420, 480),
    "dashboard": (1100, 720),
}


# --------------------------------------------------------------------------- #
# Splash Screen (CTkToplevel -- a child window, safe to create once at startup)
# --------------------------------------------------------------------------- #

class SplashScreen(ctk.CTkToplevel):
    """Brief branded loading screen shown while the app initializes."""

    def __init__(self, master, on_done):
        super().__init__(master)
        self.overrideredirect(True)
        w, h = 420, 300
        self.update_idletasks()
        self.geometry(f"{w}x{h}+{(self.winfo_screenwidth() - w) // 2}+"
                      f"{(self.winfo_screenheight() - h) // 2}")
        self.configure(fg_color=COLORS["dark"]["bg"])
        self.attributes("-topmost", True)

        ctk.CTkLabel(self, text=BRAND_ICON, font=("Segoe UI", 48)).pack(pady=(36, 6))
        ctk.CTkLabel(
            self, text=BRAND_SHORT_NAME, font=FONTS["h1"],
            text_color=COLORS["dark"]["text"],
        ).pack()
        ctk.CTkLabel(
            self, text=BRAND_TAGLINE, font=FONTS["body"],
            text_color=COLORS["dark"]["muted_text"],
        ).pack(pady=(0, 10))

        pulse = _make_pulse_line(
            self, width=220, height=32,
            color=COLORS["dark"]["primary"], bg=COLORS["dark"]["bg"],
        )
        pulse.pack(pady=(0, 10))

        self.progress = ctk.CTkProgressBar(
            self, width=300, progress_color=COLORS["dark"]["primary"],
            fg_color=COLORS["dark"]["border"],
        )
        self.progress.pack(pady=8)
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(
            self, text="Loading model...", font=FONTS["small"],
            text_color=COLORS["dark"]["muted_text"],
        )
        self.status_label.pack()

        self.on_done = on_done
        threading.Thread(target=self._animate, daemon=True).start()

    def _animate(self) -> None:
        steps = [
            (0.25, "Loading trained model..."),
            (0.55, "Connecting to database..."),
            (0.8, "Preparing interface..."),
            (1.0, "Ready."),
        ]
        for value, text in steps:
            time.sleep(0.3)
            self.after(0, lambda v=value, t=text: (
                self.progress.set(v), self.status_label.configure(text=t)
            ))
        time.sleep(0.2)
        self.after(0, self._finish)

    def _finish(self) -> None:
        self.destroy()
        self.on_done()


# --------------------------------------------------------------------------- #
# History Detail Window (CTkToplevel -- a child window, safe to create
# multiple times since it isn't a second root)
# --------------------------------------------------------------------------- #

class HistoryDetailWindow(ctk.CTkToplevel):
    """Shows the full detail of a single stored prediction: all 8 clinical
    inputs, the prediction/probability/risk/suggestions, the timestamp, and
    the same probability-gauge and feature-profile charts used in the PDF
    report -- plus a button to generate that PDF directly from here."""

    def __init__(self, master, db: Database, username: str, theme: ThemeManager, row):
        super().__init__(master)
        self.db = db
        self.username = username
        self.theme = theme
        self.row = row
        c = theme.colors()

        self.title("Prediction Details")
        w, h = 640, 760
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.configure(fg_color=c["bg"])
        self.minsize(520, 500)
        self.transient(master)  # stays on top of / tied to the dashboard window
        self.grab_set()  # modal: keeps focus until closed

        inputs = _history_row_to_inputs(row)
        suggestions = risk_suggestions(row["risk_level"])
        risk_color = {"Green": c["success"], "Yellow": c["warning"], "Red": c["danger"]}.get(
            row["risk_level"], c["muted_text"]
        )

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            scroll, text=f"Prediction: {row['prediction']}", font=FONTS["h1"],
            text_color=c["text"],
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            scroll, text=f"Recorded: {row['created_at']}", font=FONTS["small"],
            text_color=c["muted_text"],
        ).pack(anchor="w", pady=(0, 12))

        summary_card = ctk.CTkFrame(scroll, corner_radius=RADIUS, fg_color=c["surface"])
        summary_card.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(
            summary_card, text=f"Probability: {row['probability'] * 100:.1f}%",
            font=FONTS["data"], text_color=c["text"],
        ).pack(anchor="w", padx=20, pady=(16, 4))
        ctk.CTkLabel(
            summary_card, text=f"  Risk Level: {row['risk_level']}  ", font=FONTS["button"],
            fg_color=risk_color, text_color="#FFFFFF", corner_radius=8,
        ).pack(anchor="w", padx=20, pady=(0, 12))

        ctk.CTkLabel(
            scroll, text="Clinical Inputs", font=FONTS["h3"], text_color=c["text"],
        ).pack(anchor="w", pady=(4, 6))
        inputs_card = ctk.CTkFrame(scroll, corner_radius=RADIUS, fg_color=c["surface"])
        inputs_card.pack(fill="x", pady=(0, 16))
        for field, (_lo, _hi, label) in FEATURE_RANGES.items():
            row_frame = ctk.CTkFrame(inputs_card, fg_color="transparent")
            row_frame.pack(fill="x", padx=20, pady=4)
            ctk.CTkLabel(row_frame, text=label, font=FONTS["body"], width=220,
                         anchor="w", text_color=c["muted_text"]).pack(side="left")
            ctk.CTkLabel(row_frame, text=str(inputs.get(field, "-")), font=FONTS["body"],
                         anchor="w", text_color=c["text"]).pack(side="left")
        ctk.CTkLabel(inputs_card, text="", height=1).pack(pady=4)

        ctk.CTkLabel(
            scroll, text="Suggestions", font=FONTS["h3"], text_color=c["text"],
        ).pack(anchor="w", pady=(4, 6))
        for tip in suggestions:
            ctk.CTkLabel(
                scroll, text=f"• {tip}", font=FONTS["body"], text_color=c["muted_text"],
                wraplength=560, justify="left",
            ).pack(anchor="w", pady=1)

        ctk.CTkLabel(
            scroll, text="Probability Gauge", font=FONTS["h3"], text_color=c["text"],
        ).pack(anchor="w", pady=(16, 6))
        gauge_pil = get_probability_gauge_image(row["probability"], row["risk_level"])
        gauge_ctk_img = ctk.CTkImage(
            light_image=gauge_pil, dark_image=gauge_pil,
            size=(380, int(380 * gauge_pil.height / gauge_pil.width)),
        )
        ctk.CTkLabel(scroll, image=gauge_ctk_img, text="").pack(pady=(0, 12))

        ctk.CTkLabel(
            scroll, text="Feature Profile", font=FONTS["h3"], text_color=c["text"],
        ).pack(anchor="w", pady=(4, 6))
        profile_pil = get_feature_profile_image(inputs)
        profile_ctk_img = ctk.CTkImage(
            light_image=profile_pil, dark_image=profile_pil,
            size=(560, int(560 * profile_pil.height / profile_pil.width)),
        )
        ctk.CTkLabel(scroll, image=profile_ctk_img, text="").pack(pady=(0, 16))

        ctk.CTkButton(
            scroll, text="📄 Generate PDF Report", height=42, corner_radius=RADIUS,
            font=FONTS["button"], fg_color=c["primary"], hover_color=c["primary_hover"],
            command=lambda: _prompt_and_generate_prediction_pdf(self.db, self.username, self.row),
        ).pack(anchor="w", pady=(0, 20))


# --------------------------------------------------------------------------- #
# Patient Profile Form (CTkToplevel -- used both for the mandatory
# first-time "Complete Your Profile" prompt and for "Edit Profile")
# --------------------------------------------------------------------------- #

class ProfileFormWindow(ctk.CTkToplevel):
    """Modal patient-profile form. `existing_row` is None for first-time
    setup ("Complete Your Profile") or a patient_profile row for editing.
    Age is calculated live from the Date of Birth pickers and BMI is
    calculated live from Height/Weight -- neither is ever entered directly.
    On Save, validates via validators.validate_profile_form() and persists
    through Database.upsert_profile(), which guarantees exactly one row per
    user (update in place rather than a duplicate).

    Design note: this window is modal (grab_set) while open, but the user
    can still cancel/close it without saving -- it isn't forced un-closable.
    If they cancel a first-time prompt, the Overview page falls back to a
    "Complete Your Profile" card with the same form available on demand, so
    the user is never blocked from the rest of the app.
    """

    def __init__(self, master, db: Database, theme: ThemeManager, username: str,
                 existing_row, on_saved):
        super().__init__(master)
        self.db = db
        self.theme = theme
        self.username = username
        self.existing_row = existing_row
        self.on_saved = on_saved
        c = theme.colors()

        is_new = existing_row is None
        self.title("Complete Your Profile" if is_new else "Edit Profile")
        w, h = 560, 780
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.configure(fg_color=c["bg"])
        self.minsize(460, 520)
        self.transient(master)
        self.grab_set()

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            scroll, text="Complete Your Profile" if is_new else "Edit Profile",
            font=FONTS["h1"], text_color=c["text"],
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            scroll, text="This information personalizes your dashboard and PDF reports.",
            font=FONTS["body"], text_color=c["muted_text"], wraplength=480, justify="left",
        ).pack(anchor="w", pady=(0, 16))

        form = ctk.CTkFrame(scroll, corner_radius=RADIUS, fg_color=c["surface"])
        form.pack(fill="x", pady=(0, 16))

        def field_label(text: str) -> ctk.CTkLabel:
            label = ctk.CTkLabel(
                form, text=text, font=FONTS["body"], text_color=c["text"],
                anchor="w",
            )
            label.pack(fill="x", padx=20, pady=(14, 2))
            return label

        field_label("Patient Name")
        self.name_entry = ctk.CTkEntry(form, height=36)
        self.name_entry.pack(fill="x", padx=20)

        field_label("Gender")
        self.gender_var = ctk.StringVar(value=GENDERS[0])
        ctk.CTkOptionMenu(form, values=GENDERS, variable=self.gender_var).pack(
            fill="x", padx=20
        )

        field_label("Date of Birth")
        dob_row = ctk.CTkFrame(form, fg_color="transparent")
        dob_row.pack(fill="x", padx=20)
        current_year = date.today().year
        years = [str(y) for y in range(current_year, MIN_BIRTH_YEAR - 1, -1)]
        months = [f"{m:02d}" for m in range(1, 13)]
        days = [f"{d:02d}" for d in range(1, 32)]
        self.year_var = ctk.StringVar(value=years[-1])
        self.month_var = ctk.StringVar(value=months[0])
        self.day_var = ctk.StringVar(value=days[0])
        ctk.CTkOptionMenu(
            dob_row, values=years, variable=self.year_var, width=100,
            command=lambda _choice: self._recalculate_age(),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(
            dob_row, values=months, variable=self.month_var, width=70,
            command=lambda _choice: self._recalculate_age(),
        ).pack(side="left", padx=6)
        ctk.CTkOptionMenu(
            dob_row, values=days, variable=self.day_var, width=70,
            command=lambda _choice: self._recalculate_age(),
        ).pack(side="left", padx=6)

        field_label("Age (calculated automatically)")
        self.age_label_var = ctk.StringVar(value="-")
        ctk.CTkLabel(form, textvariable=self.age_label_var, font=FONTS["data"],
                     text_color=c["primary"], anchor="w").pack(fill="x", padx=20)

        field_label("Blood Group")
        self.blood_group_var = ctk.StringVar(value=BLOOD_GROUPS[0])
        ctk.CTkOptionMenu(
            form, values=BLOOD_GROUPS, variable=self.blood_group_var,
            command=self._on_blood_group_change,
        ).pack(fill="x", padx=20)
        self.custom_blood_group_frame = ctk.CTkFrame(form, fg_color="transparent")
        ctk.CTkLabel(
            self.custom_blood_group_frame, text="Enter Blood Group",
            font=FONTS["body"], text_color=c["text"], anchor="w",
        ).pack(fill="x", pady=(10, 2))
        self.custom_blood_group_entry = ctk.CTkEntry(
            self.custom_blood_group_frame, height=36,
        )
        self.custom_blood_group_entry.pack(fill="x")
        self.phone_label = field_label("Phone Number")

        self.phone_entry = ctk.CTkEntry(form, height=36, placeholder_text="10 digits")
        self.phone_entry.pack(fill="x", padx=20)

        field_label("Email Address")
        self.email_entry = ctk.CTkEntry(form, height=36)
        self.email_entry.pack(fill="x", padx=20)

        field_label("Height (cm) and Weight (kg)")
        hw_row = ctk.CTkFrame(form, fg_color="transparent")
        hw_row.pack(fill="x", padx=20)
        self.height_entry = ctk.CTkEntry(hw_row, height=36, placeholder_text="Height (cm)")
        self.height_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.weight_entry = ctk.CTkEntry(hw_row, height=36, placeholder_text="Weight (kg)")
        self.weight_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.height_entry.bind("<KeyRelease>", lambda _e: self._recalculate_bmi())
        self.weight_entry.bind("<KeyRelease>", lambda _e: self._recalculate_bmi())

        field_label("BMI (calculated automatically)")
        self.bmi_label_var = ctk.StringVar(value="-")
        ctk.CTkLabel(form, textvariable=self.bmi_label_var, font=FONTS["data"],
                     text_color=c["primary"], anchor="w").pack(fill="x", padx=20)

        field_label("Address")
        self.address_entry = ctk.CTkTextbox(form, height=60)
        self.address_entry.pack(fill="x", padx=20)

        field_label("Emergency Contact Name")
        self.ec_name_entry = ctk.CTkEntry(form, height=36)
        self.ec_name_entry.pack(fill="x", padx=20)

        field_label("Emergency Contact Number")
        self.ec_phone_entry = ctk.CTkEntry(form, height=36, placeholder_text="10 digits")
        self.ec_phone_entry.pack(fill="x", padx=20, pady=(0, 16))

        self.error_label = ctk.CTkLabel(
            scroll, text="", text_color=c["danger"], wraplength=480, justify="left",
        )
        self.error_label.pack(anchor="w", pady=(4, 8))

        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 20))
        ctk.CTkButton(
            btn_row, text="Save", height=42, corner_radius=RADIUS, font=FONTS["button"],
            fg_color=c["primary"], hover_color=c["primary_hover"], command=self._save,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="Reset", height=42, corner_radius=RADIUS, font=FONTS["button"],
            fg_color="transparent", border_width=1, border_color=c["border"],
            text_color=c["text"], hover_color=c["border"], command=self._reset,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row, text="Cancel", height=42, corner_radius=RADIUS, font=FONTS["button"],
            fg_color=c["danger"], hover_color=c["danger_hover"], command=self.destroy,
        ).pack(side="left", padx=8)

        self._populate_initial_values()
        self._recalculate_age()
        self._recalculate_bmi()

    def _populate_initial_values(self) -> None:
        row = self.existing_row
        if row is None:
            return
        self.name_entry.insert(0, row["patient_name"])
        self.gender_var.set(row["gender"])
        try:
            y, m, d = row["date_of_birth"].split("-")
            self.year_var.set(y)
            self.month_var.set(m)
            self.day_var.set(d)
        except (ValueError, AttributeError):
            pass
        blood_group, custom_blood_group = blood_group_form_values(row["blood_group"])
        self.blood_group_var.set(blood_group)
        self.custom_blood_group_entry.insert(0, custom_blood_group)
        self._on_blood_group_change(blood_group, clear_when_hidden=False)
        self.phone_entry.insert(0, row["phone"])
        self.email_entry.insert(0, row["email"])
        self.height_entry.insert(0, str(row["height"]))
        self.weight_entry.insert(0, str(row["weight"]))
        self.address_entry.insert("1.0", row["address"] or "")
        self.ec_name_entry.insert(0, row["emergency_contact_name"] or "")
        self.ec_phone_entry.insert(0, row["emergency_contact_number"] or "")

    def _reset(self) -> None:
        for entry in (self.name_entry, self.phone_entry, self.email_entry,
                      self.height_entry, self.weight_entry,
                      self.ec_name_entry, self.ec_phone_entry):
            entry.delete(0, "end")
        self.address_entry.delete("1.0", "end")
        self.gender_var.set(GENDERS[0])
        self.blood_group_var.set(BLOOD_GROUPS[0])
        self.custom_blood_group_entry.delete(0, "end")
        self._on_blood_group_change(BLOOD_GROUPS[0])
        self.year_var.set(str(date.today().year))
        self.month_var.set("01")
        self.day_var.set("01")
        self._populate_initial_values()
        self._recalculate_age()
        self._recalculate_bmi()

    def _recalculate_age(self) -> None:
        try:
            y, m, d = int(self.year_var.get()), int(self.month_var.get()), int(self.day_var.get())
            self.age_label_var.set(f"{calculate_age(date(y, m, d))} years")
        except ValueError:
            self.age_label_var.set("-")

    def _on_blood_group_change(
        self, selection: str, clear_when_hidden: bool = True
    ) -> None:
        if selection == OTHER_BLOOD_GROUP:
            if not self.custom_blood_group_frame.winfo_manager():
                self.custom_blood_group_frame.pack(
                    fill="x", padx=20, before=self.phone_label
                )
        else:
            self.custom_blood_group_frame.pack_forget()
            if clear_when_hidden:
                self.custom_blood_group_entry.delete(0, "end")

    def _recalculate_bmi(self) -> None:
        try:
            height = float(self.height_entry.get())
            weight = float(self.weight_entry.get())
            self.bmi_label_var.set(f"{calculate_bmi(height, weight):g}")
        except ValueError:
            self.bmi_label_var.set("-")

    def _save(self) -> None:
        values = {
            "patient_name": self.name_entry.get(),
            "gender": self.gender_var.get(),
            "year": self.year_var.get(), "month": self.month_var.get(),
            "day": self.day_var.get(),
            "blood_group": self.blood_group_var.get(),
            "custom_blood_group": self.custom_blood_group_entry.get(),
            "phone": self.phone_entry.get(),
            "email": self.email_entry.get(),
            "height": self.height_entry.get(),
            "weight": self.weight_entry.get(),
            "address": self.address_entry.get("1.0", "end").strip(),
            "emergency_contact_name": self.ec_name_entry.get(),
            "emergency_contact_number": self.ec_phone_entry.get(),
        }
        result = validate_profile_form(values)
        if not result:
            self.error_label.configure(text="\n".join(result.errors))
            return
        self.error_label.configure(text="")

        dob = date(int(values["year"]), int(values["month"]), int(values["day"]))
        height = float(values["height"])
        weight = float(values["weight"])

        try:
            self.db.upsert_profile(
                username=self.username,
                patient_name=values["patient_name"].strip(),
                gender=values["gender"],
                date_of_birth=dob.isoformat(),
                age=calculate_age(dob),
                blood_group=resolve_blood_group(
                    values["blood_group"], values["custom_blood_group"]
                ),
                phone=values["phone"].strip(),
                email=values["email"].strip(),
                height=height,
                weight=weight,
                bmi=calculate_bmi(height, weight),
                address=values["address"].strip(),
                emergency_contact_name=values["emergency_contact_name"].strip(),
                emergency_contact_number=values["emergency_contact_number"].strip(),
            )
            messagebox.showinfo("Profile Saved", "Your patient profile has been saved.")
            self.destroy()
            if self.on_saved:
                self.on_saved()
        except DatabaseError as exc:
            self.error_label.configure(text=str(exc))


# --------------------------------------------------------------------------- #
# App (the ONE persistent root window)
# --------------------------------------------------------------------------- #

class App(ctk.CTk):
    """The single Tk root for the whole application. Owns the database
    connection and swaps CTkFrame "screens" in and out of itself."""

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)
        self.db = Database()
        self.current_frame: ctk.CTkFrame | None = None
        self.username: str | None = None
        self.theme: ThemeManager | None = None

        try:
            self.predictor = DiabetesPredictor()
        except ModelNotFoundError as exc:
            self.predictor = None
            self._model_error = str(exc)
        else:
            self._model_error = None

        self.withdraw()  # hide the root until the splash screen finishes
        self.after(50, self._start_splash)

    def _start_splash(self) -> None:
        SplashScreen(self, on_done=self.show_login)

    def _center(self, w: int, h: int) -> None:
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.resizable(w >= 1000, w >= 1000)  # only the dashboard is resizable
        if w >= 1000:
            self.minsize(960, 640)

    def switch_to(self, frame_cls, screen_key: str, **kwargs) -> None:
        """Destroy the current screen and mount a new one in its place."""
        if self.current_frame is not None:
            self.current_frame.destroy()
        self._center(*SCREEN_SIZES[screen_key])
        self.current_frame = frame_cls(self, self, **kwargs)
        self.current_frame.pack(fill="both", expand=True)
        self.deiconify()

    # -- navigation helpers used by every screen --------------------------- #

    def show_login(self) -> None:
        self.username = None
        self.theme = None
        self.switch_to(LoginFrame, "login")

    def show_register(self) -> None:
        self.switch_to(RegisterFrame, "register")

    def show_forgot_password(self) -> None:
        self.switch_to(ForgotPasswordFrame, "forgot_password")

    def show_dashboard(self, username: str) -> None:
        self.username = username
        self.theme = ThemeManager(self.db, username)
        self.switch_to(DashboardFrame, "dashboard", username=username)


# --------------------------------------------------------------------------- #
# Login Frame
# --------------------------------------------------------------------------- #

class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, app: App):
        super().__init__(master, fg_color="transparent")
        self.app = app
        c = COLORS["dark"]

        card = ctk.CTkFrame(self, corner_radius=RADIUS)
        card.pack(expand=True, fill="both", padx=24, pady=24)

        ctk.CTkLabel(card, text="🩺", font=("Segoe UI", 40)).pack(pady=(30, 0))
        ctk.CTkLabel(card, text="Welcome Back", font=FONTS["h1"]).pack(pady=(6, 2))
        ctk.CTkLabel(
            card, text="Sign in to your account", font=FONTS["body"],
            text_color=c["muted_text"],
        ).pack(pady=(0, 24))

        self.username_entry = ctk.CTkEntry(
            card, placeholder_text="Username", width=280, height=40
        )
        self.username_entry.pack(pady=8)

        self.password_entry = ctk.CTkEntry(
            card, placeholder_text="Password", show="•", width=280, height=40
        )
        self.password_entry.pack(pady=8)
        self.password_entry.bind("<Return>", lambda e: self._login())

        self.error_label = ctk.CTkLabel(card, text="", text_color=c["danger"],
                                         wraplength=280)
        self.error_label.pack(pady=(4, 0))

        ctk.CTkButton(
            card, text="Login", width=280, height=42, corner_radius=RADIUS,
            font=FONTS["button"], fg_color=c["primary"], hover_color=c["primary_hover"],
            command=self._login,
        ).pack(pady=(16, 8))

        links = ctk.CTkFrame(card, fg_color="transparent")
        links.pack(pady=4)
        ctk.CTkButton(
            links, text="Forgot password?", fg_color="transparent",
            hover=False, text_color=c["primary"],
            command=self.app.show_forgot_password,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            links, text="Create account", fg_color="transparent",
            hover=False, text_color=c["primary"],
            command=self.app.show_register,
        ).pack(side="left", padx=4)

    def _login(self) -> None:
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        result = validate_username(username)
        if not result:
            self.error_label.configure(text=result.errors[0])
            return

        try:
            if self.app.db.authenticate(username, password):
                self.app.show_dashboard(username)
            else:
                self.error_label.configure(text="Invalid username or password.")
        except DatabaseError as exc:
            logger.exception("Login failed")
            self.error_label.configure(text=f"Database error: {exc}")


# --------------------------------------------------------------------------- #
# Register Frame
# --------------------------------------------------------------------------- #

class RegisterFrame(ctk.CTkFrame):
    def __init__(self, master, app: App):
        super().__init__(master, fg_color="transparent")
        self.app = app
        c = COLORS["dark"]

        card = ctk.CTkFrame(self, corner_radius=RADIUS)
        card.pack(expand=True, fill="both", padx=24, pady=24)

        ctk.CTkLabel(card, text="Create Account", font=FONTS["h1"]).pack(pady=(24, 2))
        ctk.CTkLabel(
            card, text="Set up your patient portal login", font=FONTS["body"],
            text_color=c["muted_text"],
        ).pack(pady=(0, 18))

        self.username_entry = ctk.CTkEntry(card, placeholder_text="Username", width=300, height=40)
        self.username_entry.pack(pady=6)
        self.email_entry = ctk.CTkEntry(card, placeholder_text="Email", width=300, height=40)
        self.email_entry.pack(pady=6)
        self.password_entry = ctk.CTkEntry(card, placeholder_text="Password", show="•", width=300, height=40)
        self.password_entry.pack(pady=6)
        self.confirm_entry = ctk.CTkEntry(card, placeholder_text="Confirm Password", show="•", width=300, height=40)
        self.confirm_entry.pack(pady=6)
        self.security_answer_entry = ctk.CTkEntry(
            card, placeholder_text="Security answer: your city of birth",
            width=300, height=40,
        )
        self.security_answer_entry.pack(pady=6)

        self.error_label = ctk.CTkLabel(card, text="", text_color=c["danger"],
                                         wraplength=300, justify="left")
        self.error_label.pack(pady=(6, 0))

        ctk.CTkButton(
            card, text="Register", width=300, height=42, corner_radius=RADIUS,
            font=FONTS["button"], fg_color=c["primary"], hover_color=c["primary_hover"],
            command=self._handle_register,
        ).pack(pady=(16, 8))

        ctk.CTkButton(
            card, text="Already have an account? Login", fg_color="transparent",
            hover=False, text_color=c["primary"],
            command=self.app.show_login,
        ).pack(pady=4)

    def _handle_register(self) -> None:
        username = self.username_entry.get().strip()
        email = self.email_entry.get().strip()
        password = self.password_entry.get()
        confirm = self.confirm_entry.get()
        security_answer = self.security_answer_entry.get().strip()

        for result in (
            validate_username(username),
            validate_email(email),
            validate_password(password),
            validate_passwords_match(password, confirm),
        ):
            if not result:
                self.error_label.configure(text=result.errors[0])
                return
        if not security_answer:
            self.error_label.configure(text="Security answer cannot be empty.")
            return

        try:
            self.app.db.create_user(username, email, password, security_answer)
            messagebox.showinfo("Success", "Account created! Please log in.")
            self.app.show_login()
        except DatabaseError as exc:
            self.error_label.configure(text=str(exc))


# --------------------------------------------------------------------------- #
# Forgot Password Frame
# --------------------------------------------------------------------------- #

class ForgotPasswordFrame(ctk.CTkFrame):
    def __init__(self, master, app: App):
        super().__init__(master, fg_color="transparent")
        self.app = app
        c = COLORS["dark"]

        card = ctk.CTkFrame(self, corner_radius=RADIUS)
        card.pack(expand=True, fill="both", padx=24, pady=24)

        ctk.CTkLabel(card, text="Reset Password", font=FONTS["h1"]).pack(pady=(30, 2))
        ctk.CTkLabel(
            card, text="Answer your security question to continue",
            font=FONTS["body"], text_color=c["muted_text"],
        ).pack(pady=(0, 18))

        self.username_entry = ctk.CTkEntry(card, placeholder_text="Username", width=280, height=40)
        self.username_entry.pack(pady=6)
        self.answer_entry = ctk.CTkEntry(
            card, placeholder_text="Security answer: your city of birth",
            width=280, height=40,
        )
        self.answer_entry.pack(pady=6)
        self.new_password_entry = ctk.CTkEntry(
            card, placeholder_text="New password", show="•", width=280, height=40
        )
        self.new_password_entry.pack(pady=6)

        self.error_label = ctk.CTkLabel(card, text="", text_color=c["danger"],
                                         wraplength=280)
        self.error_label.pack(pady=(6, 0))

        ctk.CTkButton(
            card, text="Reset Password", width=280, height=42, corner_radius=RADIUS,
            font=FONTS["button"], fg_color=c["primary"], hover_color=c["primary_hover"],
            command=self._reset,
        ).pack(pady=(16, 8))

        ctk.CTkButton(
            card, text="Back to login", fg_color="transparent", hover=False,
            text_color=c["primary"], command=self.app.show_login,
        ).pack(pady=4)

    def _reset(self) -> None:
        username = self.username_entry.get().strip()
        answer = self.answer_entry.get().strip()
        new_password = self.new_password_entry.get()

        pw_result = validate_password(new_password)
        if not pw_result:
            self.error_label.configure(text=pw_result.errors[0])
            return

        if not self.app.db.verify_security_answer(username, answer):
            self.error_label.configure(text="Username or security answer is incorrect.")
            return

        try:
            self.app.db.reset_password(username, new_password)
            messagebox.showinfo("Success", "Password reset! Please log in.")
            self.app.show_login()
        except DatabaseError as exc:
            self.error_label.configure(text=str(exc))


# --------------------------------------------------------------------------- #
# Dashboard Frame (sidebar shell + tabs)
# --------------------------------------------------------------------------- #

class DashboardFrame(ctk.CTkFrame):
    def __init__(self, master, app: App, username: str):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.username = username
        self.db = app.db
        self.theme = app.theme
        self.predictor = app.predictor
        self._last_prediction_inputs: dict[str, float] | None = None

        if self.predictor is None:
            messagebox.showerror(
                "Model Not Found",
                app._model_error or "Trained model artifacts not found. "
                "Run `python model/train_model.py` first.",
            )

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.pack_propagate(False)

        self._build_sidebar()
        self._build_content_area()
        self._show_overview()

        # Deferred (not called synchronously): the root App window is still
        # withdrawn at this point in switch_to() -- see the module docstring
        # on the single-root-window pattern -- and CTkToplevel.grab_set()
        # requires a viewable master. Scheduling via `after` runs this once
        # the event loop resumes, by which point App.deiconify() has already
        # made the window visible.
        self.after(250, self._maybe_prompt_profile_completion)

    def _maybe_prompt_profile_completion(self) -> None:
        if self.db.get_profile(self.username) is None:
            self._open_profile_form()

    def _open_profile_form(self) -> None:
        existing = self.db.get_profile(self.username)
        ProfileFormWindow(
            self, db=self.db, theme=self.theme, username=self.username,
            existing_row=existing, on_saved=self._show_overview,
        )

    # -- sidebar ------------------------------------------------------------- #

    def _build_sidebar(self) -> None:
        c = self.theme.colors()
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0,
                                     fg_color=c["sidebar"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self.sidebar, text=f"{BRAND_ICON} {BRAND_SHORT_NAME}", font=FONTS["h3"],
            text_color=c["sidebar_text"],
        ).pack(pady=(24, 0), padx=20, anchor="w")
        ctk.CTkLabel(
            self.sidebar, text=BRAND_TAGLINE, font=FONTS["small"],
            text_color=c["muted_text"],
        ).pack(pady=(0, 6), padx=20, anchor="w")
        pulse = _make_pulse_line(
            self.sidebar, width=180, height=26, color=c["primary"], bg=c["sidebar"],
        )
        pulse.pack(pady=(0, 14), padx=20, anchor="w")
        ctk.CTkLabel(
            self.sidebar, text=f"Signed in as {self.username}", font=FONTS["small"],
            text_color=c["muted_text"],
        ).pack(pady=(0, 20), padx=20, anchor="w")

        nav_items = [
            ("Overview", self._show_overview),
            ("New Prediction", self._show_prediction),
            ("History", self._show_history),
            ("About Project", self._show_about),
            ("Help", self._show_help),
        ]
        for label, command in nav_items:
            ctk.CTkButton(
                self.sidebar, text=label, anchor="w", corner_radius=8,
                fg_color="transparent", hover_color=c["primary"],
                font=FONTS["body"], command=command,
            ).pack(fill="x", padx=12, pady=4)

        ctk.CTkFrame(self.sidebar, fg_color=c["border"], height=1).pack(
            fill="x", padx=12, pady=16
        )

        ctk.CTkButton(
            self.sidebar, text="🌗 Toggle Theme", anchor="w", corner_radius=8,
            fg_color="transparent", hover_color=c["primary"], font=FONTS["body"],
            command=self._toggle_theme,
        ).pack(fill="x", padx=12, pady=4)

        ctk.CTkButton(
            self.sidebar, text="Logout", anchor="w", corner_radius=8,
            fg_color="transparent", hover_color=c["danger"], font=FONTS["body"],
            command=self.app.show_login,
        ).pack(fill="x", padx=12, pady=(4, 20), side="bottom")

    def _toggle_theme(self) -> None:
        self.theme.toggle()
        messagebox.showinfo(
            "Theme changed",
            "Theme preference saved. Reopen the dashboard (logout/login) "
            "to see it fully applied.",
        )

    # -- content switching ----------------------------------------------------- #

    def _build_content_area(self) -> None:
        c = self.theme.colors()
        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=c["bg"])
        self.content.grid(row=0, column=1, sticky="nsew")

    def _clear_content(self) -> None:
        for widget in self.content.winfo_children():
            widget.destroy()

    def _show_overview(self) -> None:
        self._clear_content()
        c = self.theme.colors()

        ctk.CTkLabel(self.content, text="Overview", font=FONTS["h1"],
                     text_color=c["text"]).pack(anchor="w", padx=30, pady=(30, 4))
        ctk.CTkLabel(
            self.content, text="Your patient profile and prediction summary",
            font=FONTS["body"], text_color=c["muted_text"],
        ).pack(anchor="w", padx=30, pady=(0, 20))

        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        profile_row = self.db.get_profile(self.username)
        if profile_row is None:
            self._render_profile_missing_card(scroll, c)
        else:
            self._render_patient_info_card(scroll, c, PatientProfile.from_row(profile_row))

        self._render_prediction_stats_card(scroll, c)
        self._render_quick_actions(scroll, c)

    def _render_profile_missing_card(self, parent, c) -> None:
        card = ctk.CTkFrame(parent, corner_radius=RADIUS, fg_color=c["surface"])
        card.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(card, text="Complete Your Profile", font=FONTS["h3"],
                     text_color=c["text"]).pack(anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(
            card, text="Add your patient details to personalize your dashboard "
            "and PDF reports.",
            font=FONTS["body"], text_color=c["muted_text"], wraplength=600, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 12))
        ctk.CTkButton(
            card, text="Complete Profile", height=38, corner_radius=RADIUS,
            font=FONTS["button"], fg_color=c["primary"], hover_color=c["primary_hover"],
            command=self._open_profile_form,
        ).pack(anchor="w", padx=20, pady=(0, 20))

    def _render_patient_info_card(self, parent, c, profile: PatientProfile) -> None:
        card = ctk.CTkFrame(parent, corner_radius=RADIUS, fg_color=c["surface"])
        card.pack(fill="x", pady=(0, 16))

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))

        avatar = _make_initials_avatar(
            header, size=56, initials=profile.initials(),
            bg=c["surface"], fill=c["primary"], text_color="#FFFFFF",
        )
        avatar.pack(side="left", padx=(0, 14))

        name_block = ctk.CTkFrame(header, fg_color="transparent")
        name_block.pack(side="left")
        ctk.CTkLabel(name_block, text=profile.patient_name, font=FONTS["h2"],
                     text_color=c["text"]).pack(anchor="w")
        ctk.CTkLabel(name_block, text="Patient Information", font=FONTS["small"],
                     text_color=c["muted_text"]).pack(anchor="w")

        emergency = (
            f"{profile.emergency_contact_name} ({profile.emergency_contact_number})"
            if profile.emergency_contact_name else "-"
        )
        fields = [
            ("👤", "Name", profile.patient_name),
            ("🆔", "Username", profile.username),
            ("🚻", "Gender", profile.gender),
            ("🎂", "Date of Birth", profile.date_of_birth),
            ("📅", "Age", f"{profile.age} years"),
            ("🩸", "Blood Group", profile.blood_group or "-"),
            ("📱", "Phone Number", profile.phone),
            ("📧", "Email", profile.email),
            ("📏", "Height", f"{profile.height:g} cm"),
            ("⚖", "Weight", f"{profile.weight:g} kg"),
            ("📊", "BMI", f"{profile.bmi:g}"),
            ("🏠", "Address", profile.address or "-"),
            ("📞", "Emergency Contact", emergency),
        ]

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=(0, 16))
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        for i, (icon, label, value) in enumerate(fields):
            row_f = ctk.CTkFrame(grid, fg_color="transparent")
            row_f.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=5)
            ctk.CTkLabel(row_f, text=f"{icon} {label}", font=FONTS["small"],
                         text_color=c["muted_text"], width=160, anchor="w").pack(anchor="w")
            ctk.CTkLabel(row_f, text=str(value), font=FONTS["body"], text_color=c["text"],
                         anchor="w", wraplength=260, justify="left").pack(anchor="w")

        ctk.CTkButton(
            card, text="Edit Profile", height=34, corner_radius=RADIUS,
            font=FONTS["body"], fg_color="transparent", border_width=1,
            border_color=c["border"], text_color=c["text"], hover_color=c["border"],
            command=self._open_profile_form,
        ).pack(anchor="w", padx=20, pady=(0, 20))

    def _render_prediction_stats_card(self, parent, c) -> None:
        history = self.db.get_history(self.username)
        total = len(history)
        last_date = history[0]["created_at"].split(" ")[0] if history else "N/A"
        last_risk = history[0]["risk_level"] if history else "N/A"
        avg_probability = (
            f"{(sum(r['probability'] for r in history) / total) * 100:.1f}%"
            if total else "N/A"
        )
        risk_colors = {"Green": c["success"], "Yellow": c["warning"], "Red": c["danger"]}

        ctk.CTkLabel(parent, text="Prediction Statistics", font=FONTS["h3"],
                     text_color=c["text"]).pack(anchor="w", pady=(4, 8))

        cards_frame = ctk.CTkFrame(parent, fg_color="transparent")
        cards_frame.pack(fill="x", pady=(0, 16))
        stats = [
            ("Total Predictions", str(total), c["primary"], True),
            ("Last Prediction Date", last_date, c["text"], False),
            ("Latest Risk Level", last_risk, risk_colors.get(last_risk, c["muted_text"]), False),
            ("Average Probability", avg_probability, c["accent"], total > 0),
        ]
        for i, (label, value, color, is_numeric) in enumerate(stats):
            card = ctk.CTkFrame(cards_frame, corner_radius=RADIUS, fg_color=c["surface"])
            card.grid(row=0, column=i, padx=(0 if i == 0 else 10, 0), sticky="nsew")
            cards_frame.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(
                card, text=value, font=FONTS["data"] if is_numeric else FONTS["h3"],
                text_color=color,
            ).pack(pady=(16, 4), padx=10)
            ctk.CTkLabel(card, text=label, font=FONTS["small"], text_color=c["muted_text"],
                         wraplength=140, justify="center").pack(pady=(0, 16), padx=10)

    def _render_quick_actions(self, parent, c) -> None:
        ctk.CTkLabel(parent, text="Quick Actions", font=FONTS["h3"],
                     text_color=c["text"]).pack(anchor="w", pady=(4, 8))
        actions_frame = ctk.CTkFrame(parent, fg_color="transparent")
        actions_frame.pack(fill="x", pady=(0, 20))

        buttons = [
            ("New Prediction", self._show_prediction),
            ("Prediction History", self._show_history),
            ("Generate Full Report", self._export_history_pdf),
            ("Edit Profile", self._open_profile_form),
        ]
        for i, (label, command) in enumerate(buttons):
            ctk.CTkButton(
                actions_frame, text=label, height=42, corner_radius=RADIUS,
                font=FONTS["button"], fg_color=c["primary"], hover_color=c["primary_hover"],
                command=command,
            ).grid(row=0, column=i, padx=(0 if i == 0 else 10, 0), sticky="ew")
            actions_frame.grid_columnconfigure(i, weight=1)

    # -- prediction tab -------------------------------------------------------- #

    def _show_prediction(self) -> None:
        self._clear_content()
        c = self.theme.colors()

        ctk.CTkLabel(self.content, text="New Prediction", font=FONTS["h1"],
                     text_color=c["text"]).pack(anchor="w", padx=30, pady=(30, 4))
        ctk.CTkLabel(
            self.content, text="Enter the patient's clinical measurements",
            font=FONTS["body"], text_color=c["muted_text"],
        ).pack(anchor="w", padx=30, pady=(0, 16))

        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=30, pady=(0, 10))

        form_frame = ctk.CTkFrame(scroll, corner_radius=RADIUS, fg_color=c["surface"])
        form_frame.pack(fill="x", pady=(0, 12))

        self.entries: dict[str, ctk.CTkEntry] = {}
        for field, (lo, hi, label) in FEATURE_RANGES.items():
            row = ctk.CTkFrame(form_frame, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=8)
            ctk.CTkLabel(row, text=label, font=FONTS["body"], width=220,
                         anchor="w", text_color=c["text"]).pack(side="left")
            entry = ctk.CTkEntry(row, placeholder_text=f"{lo} - {hi}", width=200, height=36)
            entry.pack(side="left")
            self.entries[field] = entry

        self.error_label = ctk.CTkLabel(
            scroll, text="", text_color=c["danger"], wraplength=600, justify="left"
        )
        self.error_label.pack(anchor="w", pady=(4, 0))

        self.result_frame = ctk.CTkFrame(scroll, corner_radius=RADIUS, fg_color=c["surface"])
        # populated by _run_prediction()

        ctk.CTkButton(
            self.content, text="Predict", height=44, width=200, corner_radius=RADIUS,
            font=FONTS["button"], fg_color=c["primary"], hover_color=c["primary_hover"],
            command=self._run_prediction,
        ).pack(anchor="w", padx=30, pady=16)

    def _run_prediction(self) -> None:
        if self.predictor is None:
            messagebox.showerror(
                "Model Not Found",
                "Train the model first: python model/train_model.py",
            )
            return

        values = {field: entry.get() for field, entry in self.entries.items()}
        result = validate_prediction_form(values)
        if not result:
            self.error_label.configure(text="\n".join(result.errors))
            return
        self.error_label.configure(text="")

        numeric_values = {k: float(v) for k, v in values.items()}
        outcome = self.predictor.predict(numeric_values)

        self.db.add_prediction(
            self.username, numeric_values, outcome.label,
            outcome.probability, outcome.risk,
        )

        self._last_prediction_inputs = numeric_values
        self._render_result(outcome)

    def _render_result(self, outcome) -> None:
        c = self.theme.colors()
        for widget in self.result_frame.winfo_children():
            widget.destroy()
        self.result_frame.pack(fill="x", pady=(4, 20))

        risk_color = {"Green": c["success"], "Yellow": c["warning"], "Red": c["danger"]}[
            outcome.risk
        ]

        ctk.CTkLabel(
            self.result_frame, text=f"Prediction: {outcome.label}",
            font=FONTS["h2"], text_color=c["text"],
        ).pack(anchor="w", padx=20, pady=(20, 4))
        ctk.CTkLabel(
            self.result_frame, text=f"Probability: {outcome.probability * 100:.1f}%",
            font=FONTS["data"], text_color=c["text"],
        ).pack(anchor="w", padx=20)

        badge = ctk.CTkLabel(
            self.result_frame, text=f"  Risk Level: {outcome.risk}  ", font=FONTS["button"],
            fg_color=risk_color, text_color="#FFFFFF", corner_radius=8,
        )
        badge.pack(anchor="w", padx=20, pady=8)

        ctk.CTkLabel(
            self.result_frame, text="Suggestions:", font=FONTS["h3"], text_color=c["text"],
        ).pack(anchor="w", padx=20, pady=(8, 2))
        for tip in outcome.suggestions:
            ctk.CTkLabel(
                self.result_frame, text=f"• {tip}", font=FONTS["body"],
                text_color=c["muted_text"], wraplength=600, justify="left",
            ).pack(anchor="w", padx=32, pady=1)

        ctk.CTkButton(
            self.result_frame, text="📄 Download PDF Report", height=36, corner_radius=RADIUS,
            font=FONTS["button"], fg_color=c["primary"], hover_color=c["primary_hover"], command=lambda: self._download_prediction_pdf(outcome),
        ).pack(anchor="w", padx=20, pady=(12, 0))

        ctk.CTkLabel(self.result_frame, text="", height=1).pack(pady=6)

    def _download_prediction_pdf(self, outcome) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
            initialfile=f"{self.username}_prediction_report.pdf",
        )
        if not path:
            return
        profile_row = self.db.get_profile(self.username)
        patient_profile = (
            PatientProfile.from_row(profile_row).report_dict() if profile_row else None
        )
        try:
            generate_prediction_report(
                self.username, self._last_prediction_inputs, outcome.label,
                outcome.probability, outcome.risk, outcome.suggestions, Path(path),
                patient_profile=patient_profile,
            )
            messagebox.showinfo("Report Saved", f"PDF report saved to:\n{path}")
        except Exception as exc:
            logger.exception("Failed to generate prediction PDF report")
            messagebox.showerror("Report Failed", f"Could not generate PDF report:\n{exc}")

    # -- history tab ------------------------------------------------------------ #

    def _show_history(self) -> None:
        self._clear_content()
        c = self.theme.colors()

        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(30, 10))
        ctk.CTkLabel(header, text="Prediction History", font=FONTS["h1"],
                     text_color=c["text"]).pack(side="left")

        toolbar = ctk.CTkFrame(self.content, fg_color="transparent")
        toolbar.pack(fill="x", padx=30, pady=(0, 10))

        self.search_entry = ctk.CTkEntry(
            toolbar, placeholder_text="Search by prediction, risk, or date...",
            width=320, height=36,
        )
        self.search_entry.pack(side="left")
        ctk.CTkButton(
            toolbar, text="Search", width=90, fg_color=c["primary"],
            hover_color=c["primary_hover"], command=self._refresh_history_list,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            toolbar, text="Export PDF", width=110, fg_color=c["primary"],
            hover_color=c["primary_hover"], command=self._export_history_pdf,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            toolbar, text="Clear All", width=100, fg_color=c["danger"],
            hover_color=c["danger_hover"], command=self._clear_all_history,
        ).pack(side="left", padx=8)

        self.history_scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        self.history_scroll.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        self._refresh_history_list()

    def _refresh_history_list(self) -> None:
        for widget in self.history_scroll.winfo_children():
            widget.destroy()

        c = self.theme.colors()
        search = self.search_entry.get().strip() if hasattr(self, "search_entry") else ""
        rows = self.db.get_history(self.username, search=search)

        if not rows:
            ctk.CTkLabel(
                self.history_scroll, text="No prediction history yet.",
                font=FONTS["body"], text_color=c["muted_text"],
            ).pack(pady=20)
            return

        risk_color = {"Green": c["success"], "Yellow": c["warning"], "Red": c["danger"]}
        for row in rows:
            item = ctk.CTkFrame(self.history_scroll, corner_radius=RADIUS, fg_color=c["surface"])
            item.pack(fill="x", pady=6)

            left = ctk.CTkFrame(item, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True, padx=16, pady=12)
            ctk.CTkLabel(
                left, text=f"{row['prediction']}  ·  {row['probability'] * 100:.1f}%",
                font=FONTS["h3"], text_color=c["text"],
            ).pack(anchor="w")
            ctk.CTkLabel(
                left, text=row["created_at"], font=FONTS["small"],
                text_color=c["muted_text"],
            ).pack(anchor="w")

            ctk.CTkLabel(
                item, text=f"  {row['risk_level']}  ", font=FONTS["small"],
                fg_color=risk_color.get(row["risk_level"], c["muted_text"]),
                text_color="#FFFFFF", corner_radius=8,
            ).pack(side="left", padx=8)

            actions = ctk.CTkFrame(item, fg_color="transparent")
            actions.pack(side="right", padx=12, pady=8)

            ctk.CTkButton(
                actions, text="View Details", width=100, fg_color=c["primary"],
                hover_color=c["primary_hover"],
                command=lambda r=row: self._open_history_detail(r),
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                actions, text="Generate PDF", width=100, fg_color=c["primary"],
                hover_color=c["primary_hover"],
                command=lambda r=row: _prompt_and_generate_prediction_pdf(self.db, self.username, r),
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                actions, text="Delete", width=70, fg_color=c["danger"], hover_color=c["danger_hover"],
                command=lambda rid=row["id"]: self._delete_history_row(rid),
            ).pack(side="left", padx=4)

    def _open_history_detail(self, row) -> None:
        HistoryDetailWindow(self, db=self.db, username=self.username, theme=self.theme, row=row)

    def _delete_history_row(self, record_id: int) -> None:
        self.db.delete_prediction(record_id, self.username)
        self._refresh_history_list()

    def _clear_all_history(self) -> None:
        if messagebox.askyesno("Confirm", "Delete all prediction history? This cannot be undone."):
            self.db.clear_history(self.username)
            self._refresh_history_list()

    def _export_history_pdf(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")],
            initialfile=f"{self.username}_prediction_history.pdf",
        )
        if not path:
            return
        profile_row = self.db.get_profile(self.username)
        patient_profile = (
            PatientProfile.from_row(profile_row).report_dict() if profile_row else None
        )
        try:
            rows = self.db.get_history(self.username)
            generate_history_report(self.username, rows, Path(path), patient_profile=patient_profile)
            messagebox.showinfo("Exported", f"History PDF report saved to:\n{path}")
        except Exception as exc:
            logger.exception("Failed to generate history PDF report")
            messagebox.showerror("Report Failed", f"Could not generate PDF report:\n{exc}")

    # -- about / help ---------------------------------------------------------- #

    def _show_about(self) -> None:
        self._clear_content()
        c = self.theme.colors()
        ctk.CTkLabel(self.content, text="About This Project", font=FONTS["h1"],
                     text_color=c["text"]).pack(anchor="w", padx=30, pady=(30, 10))

        text = (
            "This application predicts a patient's likelihood of diabetes using a "
            "machine-learning model trained on the Pima Indians Diabetes Dataset. "
            "Six classifiers (Logistic Regression, Decision Tree, Random Forest, "
            "SVM, KNN, and Gradient Boosting) were trained and compared; the "
            "best-performing model by F1 score is used for live predictions.\n\n"
            "Tech stack: Python, Scikit-learn, Pandas, NumPy, CustomTkinter, SQLite.\n\n"
            "This tool is for educational and portfolio purposes only and is not a "
            "substitute for professional medical diagnosis."
        )
        ctk.CTkLabel(
            self.content, text=text, font=FONTS["body"], text_color=c["muted_text"],
            wraplength=700, justify="left",
        ).pack(anchor="w", padx=30)

    def _show_help(self) -> None:
        self._clear_content()
        c = self.theme.colors()
        ctk.CTkLabel(self.content, text="Help", font=FONTS["h1"],
                     text_color=c["text"]).pack(anchor="w", padx=30, pady=(30, 10))

        faqs = [
            ("How do I make a prediction?",
             "Go to 'New Prediction', fill in all 8 clinical fields, and click Predict."),
            ("What do the risk colors mean?",
             "Green = low probability, Yellow = moderate, Red = high probability of diabetes."),
            ("Can I export my history?",
             "Yes — go to History and click 'Export PDF'."),
            ("Can I get a PDF of a single prediction?",
             "Yes — after running a prediction, click 'Download PDF Report' "
             "under the result."),
            ("I forgot my password.",
             "Use 'Forgot password?' on the login screen and answer your security question."),
        ]
        for q, a in faqs:
            ctk.CTkLabel(self.content, text=q, font=FONTS["h3"], text_color=c["text"]).pack(
                anchor="w", padx=30, pady=(12, 0)
            )
            ctk.CTkLabel(
                self.content, text=a, font=FONTS["body"], text_color=c["muted_text"],
                wraplength=700, justify="left",
            ).pack(anchor="w", padx=30)


# --------------------------------------------------------------------------- #
# App bootstrap
# --------------------------------------------------------------------------- #

def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
