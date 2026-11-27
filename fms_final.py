import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

# =====================================================================
# Automated Flight Management System (FMS) - FINAL SEED SHOWCASE (v5 - Airbus A350-900)
# Python 3 + Tkinter + Pillow     ->     pip install pillow
#
#  * Sharp, high-DPI text (Segoe UI / Arial) - no pixelation on 4K monitors
#  * Multi-angle image system: the picture changes with the component being scanned
#        plane_front.png  -> Nose
#        plane_top.png    -> Fuselage Top, Flaps, Elevators, Stabilizers
#        plane_left.png   -> Fuselage Left
#        plane_right.png  -> Fuselage Right
#    (put the PNG files in the same folder as this script; a dark-blue
#     placeholder is shown automatically if a file is missing)
#  * START DIAGNOSTIC SCAN: sweeps all 7 components exactly once, then stops
#  * Separate live telemetry pop-up window (G-Force, Engine Temp, Wing Vibration)
# =====================================================================

import os
import random
from collections import deque
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, font as tkfont

try:
    from PIL import ImageTk, Image
    PIL_OK = True
    RESAMPLE = getattr(Image, "Resampling", Image).LANCZOS
except ImportError:          # the app still runs (with placeholders) if Pillow is missing
    PIL_OK = False
    RESAMPLE = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ======================================================================
# THEME - dark sci-fi aerospace
# ======================================================================
BG = "#060b16"
PANEL = "#0c1424"
CARD = "#101b30"
BORDER = "#1c2b47"
TEXT = "#e6edf7"
MUTED = "#7f93b2"
CYAN = "#00e5ff"
BLUE = "#1d6fff"
PLACEHOLDER = "#0a1f44"
GREY = "#5b6b84"
LEVEL_NAMES = ["NORMAL", "CAUTION", "WARNING"]
LEVEL_COLORS = ["#2ecc71", "#f5b301", "#ff4d4d"]

# ======================================================================
# SENSORS  (lo = "normal" level; caution / warn = alert thresholds)
# ======================================================================
SENSORS = {
    "temp": {"label": "Engine Temperature", "unit": "°C", "min": 300, "max": 1000,
             "lo": 500, "caution": 700, "warn": 850, "decimals": 0},
    "vib": {"label": "Wing Vibration", "unit": "mm/s", "min": 0, "max": 10,
            "lo": 2.0, "caution": 4.0, "warn": 7.0, "decimals": 1},
    "g": {"label": "G-Force", "unit": "G", "min": 0, "max": 9,
          "lo": 1.2, "caution": 3.0, "warn": 5.0, "decimals": 1},
}
NOISE = {"temp": 1.5, "vib": 0.06, "g": 0.06}

# ======================================================================
# FLIGHT PROFILE: normal flight -> high stress -> recovery -> landing
# ======================================================================
PHASES = [
    dict(name="Pre-Flight & Taxi",          dur=10, temp=430, vib=0.8, g=1.0, noise=0.5, alert=0),
    dict(name="Takeoff Roll",               dur=10, temp=790, vib=3.4, g=1.5, noise=1.0, alert=0),
    dict(name="Climb-Out",                  dur=15, temp=710, vib=2.3, g=1.2, noise=1.0, alert=0),
    dict(name="Cruise - Normal Flight",     dur=20, temp=620, vib=1.5, g=1.0, noise=0.6, alert=0),
    dict(name="Light Turbulence",           dur=15, temp=660, vib=3.1, g=2.3, noise=2.0, alert=0),
    dict(name="Severe Turbulence",          dur=18, temp=810, vib=5.6, g=4.0, noise=3.5, alert=1),
    dict(name="HIGH STRESS: Storm Evasion", dur=18, temp=910, vib=7.9, g=5.8, noise=5.0, alert=2),
    dict(name="Recovery & Stabilization",   dur=15, temp=700, vib=3.0, g=1.8, noise=2.0, alert=1),
    dict(name="Descent & Landing",          dur=15, temp=540, vib=2.2, g=1.4, noise=1.2, alert=0),
]
TOTAL_FLIGHT_TIME = sum(p["dur"] for p in PHASES)

# ======================================================================
# COMPONENTS + IMAGE MAPPING
# ======================================================================
SCAN_ORDER = ["Nose", "Fuselage Top", "Fuselage Left", "Fuselage Right",
              "Flaps", "Elevators", "Stabilizers"]

# weights = sensitivity to (engine temp, wing vibration, g-force)
WEIGHTS = {
    "Nose":           (0.30, 0.20, 0.50),
    "Fuselage Top":   (0.20, 0.20, 0.60),
    "Fuselage Left":  (0.20, 0.30, 0.50),
    "Fuselage Right": (0.20, 0.30, 0.50),
    "Flaps":          (0.10, 0.30, 0.60),
    "Elevators":      (0.10, 0.50, 0.40),
    "Stabilizers":    (0.10, 0.60, 0.30),
}

# component -> (image file, camera angle label)
VIEW_FOR = {
    "Nose":           ("plane_front.png", "FRONT VIEW"),
    "Fuselage Top":   ("plane_top.png",   "TOP VIEW"),
    "Flaps":          ("plane_top.png",   "TOP VIEW"),
    "Elevators":      ("plane_top.png",   "TOP VIEW"),
    "Stabilizers":    ("plane_top.png",   "TOP VIEW"),
    "Fuselage Left":  ("plane_left.png",  "LEFT VIEW"),
    "Fuselage Right": ("plane_right.png", "RIGHT VIEW"),
}
DEFAULT_VIEW = ("plane_top.png", "TOP VIEW")

CRACK_PLACES = {
    "Flaps": ["right wing flap", "left wing flap"],
    "Elevators": ["right elevator", "left elevator"],
    "Stabilizers": ["right horizontal stabilizer", "left horizontal stabilizer",
                    "vertical fin"],
}

# (name, level, length range in mm, health damage range in %)
SEVERITIES = [
    ("Minor", 0, (1, 5), (3, 6)),
    ("Moderate", 1, (6, 25), (10, 18)),
    ("Severe", 2, (26, 90), (25, 40)),
]

FATIGUE_RATE = 0.5      # % health lost per second of (stress squared) exposure


def status_of(health):
    """Return (name, color, level) for a health percentage."""
    if health >= 90:
        return "OPTIMAL", "#2ecc71", 0
    if health >= 75:
        return "SERVICEABLE", "#a3e635", 0
    if health >= 50:
        return "DEGRADED", "#f5b301", 1
    return "CRITICAL", "#ff4d4d", 2


def sensor_level(cfg, value):
    if value >= cfg["warn"]:
        return 2
    if value >= cfg["caution"]:
        return 1
    return 0


def pick_font(root):
    families = set(tkfont.families(root))
    for name in ("Segoe UI", "Arial", "Helvetica"):
        if name in families:
            return name
    return "Arial"


def draw_gauge(canvas, cfg, value, level, width, height):
    canvas.delete("all")
    span = cfg["max"] - cfg["min"]
    canvas.create_rectangle(0, 0, width, height, fill=BG, outline="")
    canvas.create_rectangle(0, 0, (value - cfg["min"]) / span * width, height,
                            fill=LEVEL_COLORS[level], outline="")
    for t in (cfg["caution"], cfg["warn"]):
        x = (t - cfg["min"]) / span * width
        canvas.create_line(x, 0, x, height, fill="white", dash=(2, 2))


# ======================================================================
# SEPARATE LIVE TELEMETRY WINDOW (tk.Toplevel)
# ======================================================================
class TelemetryWindow:
    ORDER = ("g", "temp", "vib")
    TITLES = {"g": "G-FORCE", "temp": "ENGINE TEMPERATURE", "vib": "WING VIBRATION"}

    def __init__(self, app):
        self.app = app
        S, f = app.S, app.f
        self.win = tk.Toplevel(app.root)
        self.win.title("Live Flight Telemetry")
        self.win.configure(bg=BG)
        self.win.geometry(f"{S(640)}x{S(640)}")
        self.win.minsize(S(600), S(600))
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.gw, self.gh = S(260), S(16)
        self.sw, self.sh = S(260), S(44)

        head = tk.Frame(self.win, bg=BG)
        head.pack(fill="x", padx=S(18), pady=(S(14), S(4)))
        tk.Label(head, text="LIVE FLIGHT TELEMETRY", bg=BG, fg=CYAN,
                 font=f(18, "bold")).pack(side="left")
        self.top_var = tk.BooleanVar(value=False)
        tk.Checkbutton(head, text="Always on top", variable=self.top_var,
                       command=lambda: self.win.attributes("-topmost", self.top_var.get()),
                       bg=BG, fg=MUTED, selectcolor=CARD, activebackground=BG,
                       activeforeground=TEXT, font=f(9)).pack(side="right")

        self.phase_label = tk.Label(self.win, bg=BG, fg=TEXT, font=f(12, "bold"), anchor="w")
        self.phase_label.pack(fill="x", padx=S(18))
        self.time_label = tk.Label(self.win, bg=BG, fg=MUTED, font=f(10), anchor="w")
        self.time_label.pack(fill="x", padx=S(18), pady=(0, S(6)))

        self.rows = {}
        for key in self.ORDER:
            cfg = SENSORS[key]
            card = tk.Frame(self.win, bg=CARD, highlightthickness=1,
                            highlightbackground=BORDER)
            card.pack(fill="x", padx=S(18), pady=S(6))
            left = tk.Frame(card, bg=CARD)
            left.pack(side="left", padx=S(14), pady=S(10))
            tk.Label(left, text=self.TITLES[key], bg=CARD, fg=MUTED,
                     font=f(10, "bold")).pack(anchor="w")
            line = tk.Frame(left, bg=CARD)
            line.pack(anchor="w")
            value = tk.Label(line, bg=CARD, fg=TEXT, font=f(40, "bold"))
            value.pack(side="left")
            tk.Label(line, text=" " + cfg["unit"], bg=CARD, fg=MUTED,
                     font=f(14)).pack(side="left", anchor="s", pady=S(8))
            chip = tk.Label(left, width=10, fg=BG, font=f(9, "bold"))
            chip.pack(anchor="w", pady=(S(2), 0))

            right = tk.Frame(card, bg=CARD)
            right.pack(side="right", padx=S(14), pady=S(10))
            gauge = tk.Canvas(right, width=self.gw, height=self.gh, bg=BG,
                              highlightthickness=0)
            gauge.pack(pady=(0, S(6)))
            spark = tk.Canvas(right, width=self.sw, height=self.sh, bg=BG,
                              highlightthickness=1, highlightbackground=BORDER)
            spark.pack()
            self.rows[key] = {"value": value, "chip": chip, "gauge": gauge, "spark": spark}

        tk.Label(self.win, text="White dashed marks = caution / warning limits.  "
                                "Lower graph = last 18 seconds.",
                 bg=BG, fg=MUTED, font=f(9)).pack(pady=(S(6), S(10)))
        self.update()

    def exists(self):
        return self.win.winfo_exists()

    def close(self):
        self.app.telem = None
        self.win.destroy()

    def update(self):
        app = self.app
        ph = PHASES[app.phase_idx]
        self.phase_label.config(text=f"Phase: {ph['name']}", fg=LEVEL_COLORS[ph["alert"]])
        e, t = int(app.elapsed), TOTAL_FLIGHT_TIME
        self.time_label.config(
            text=f"Flight #{app.flight_no}   T+ {e // 60:02d}:{e % 60:02d} / "
                 f"{t // 60:02d}:{t % 60:02d}")
        for key in self.ORDER:
            cfg, row = SENSORS[key], self.rows[key]
            value = app.values[key]
            level = sensor_level(cfg, value)
            row["value"].config(text=f"{value:.{cfg['decimals']}f}", fg=LEVEL_COLORS[level])
            row["chip"].config(text=LEVEL_NAMES[level], bg=LEVEL_COLORS[level])
            draw_gauge(row["gauge"], cfg, value, level, self.gw, self.gh)
            self.draw_spark(row["spark"], cfg, list(app.history[key]), level)

    def draw_spark(self, canvas, cfg, data, level):
        canvas.delete("all")
        w, h = self.sw, self.sh
        span = cfg["max"] - cfg["min"]
        for t, col in ((cfg["caution"], "#7a5d00"), (cfg["warn"], "#7a1f1f")):
            y = h - (t - cfg["min"]) / span * h
            canvas.create_line(0, y, w, y, fill=col, dash=(3, 3))
        if len(data) >= 2:
            step = w / (app_hist - 1)
            pts = []
            offset = app_hist - len(data)
            for i, v in enumerate(data):
                pts += [(offset + i) * step, h - (v - cfg["min"]) / span * h]
            canvas.create_line(*pts, fill=LEVEL_COLORS[level], width=2)


app_hist = 90   # number of samples kept for the telemetry graphs (90 x 0.2 s = 18 s)


# ======================================================================
# MAIN APPLICATION
# ======================================================================
class FMSApp:
    def __init__(self, root):
        self.root = root
        global FONT
        FONT = pick_font(root)
        self.sf = max(1.0, root.winfo_fpixels("1i") / 96.0)      # DPI scale factor
        self.apply_global_fonts()

        root.title("Flight Management System (FMS) - Airbus A350-900 | Automated Structural Diagnostics")
        root.configure(bg=BG)
        root.geometry(f"{self.S(1300)}x{self.S(900)}")
        root.minsize(self.S(1200), self.S(820))

        self.gen = 0
        self.ready = False
        self.scanning = False
        self.scan_line_ids = []
        self.telem = None
        self.cur_photo = None
        self.img_cache = {}
        self.sensor_levels = {k: 0 for k in SENSORS}
        self.values = {k: 0.0 for k in SENSORS}
        self.history = {k: deque(maxlen=app_hist) for k in SENSORS}
        self.fatigue = {n: 0.0 for n in SCAN_ORDER}
        self.comp = {}
        self.cards = {}
        self.run_no = 0

        self.setup_styles()
        self.build_header()
        self.build_phase_strip()
        self.build_main_area()
        self.build_log_panel()

        self.reset_system(first=True)
        self.tick_clock()

    # ---------- helpers ----------
    def S(self, n):
        return int(round(n * self.sf))

    def f(self, size, weight="normal"):
        return (FONT, size, weight)

    def apply_global_fonts(self):
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                     "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
            try:
                tkfont.nametofont(name).configure(family=FONT)
            except tk.TclError:
                pass
        self.root.option_add("*Font", (FONT, 10))

    def setup_styles(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("FMS.Horizontal.TProgressbar", troughcolor=BG, background=CYAN,
                     bordercolor=BORDER, lightcolor=CYAN, darkcolor=CYAN,
                     thickness=self.S(8))
        st.configure("Vertical.TScrollbar", background=CARD, troughcolor=BG,
                     bordercolor=BORDER, arrowcolor=TEXT)

    def make_button(self, parent, text, command, bg, hover, size=11, pady=8):
        btn = tk.Button(parent, text=text, command=command, bg=bg, fg="white",
                        activebackground=hover, activeforeground="white",
                        disabledforeground="#9fb0c9", relief="flat", bd=0, cursor="hand2",
                        font=self.f(size, "bold"), pady=pady)
        btn.bind("<Enter>", lambda e: btn["state"] == "normal" and btn.config(bg=hover))
        btn.bind("<Leave>", lambda e: btn["state"] == "normal" and btn.config(bg=bg))
        btn.base_bg = bg
        return btn

    # ==================================================================
    # UI BUILDING
    # ==================================================================
    def build_header(self):
        S, f = self.S, self.f
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=S(18), pady=(S(12), S(4)))
        tk.Label(header, text="✈", bg=BG, fg=CYAN, font=f(24)).pack(side="left")
        box = tk.Frame(header, bg=BG)
        box.pack(side="left", padx=S(10))
        tk.Label(box, text="FLIGHT MANAGEMENT SYSTEM", bg=BG, fg=TEXT,
                 font=f(20, "bold")).pack(anchor="w")
        tk.Label(box, text="Airbus A350-900  |  Automated Structural Diagnostics", bg=BG,
                 fg=CYAN, font=f(9, "bold")).pack(anchor="w")
        self.clock_label = tk.Label(header, bg=BG, fg=MUTED, font=f(12))
        self.clock_label.pack(side="right")

        self.banner = tk.Label(self.root, font=f(14, "bold"), pady=S(6))
        self.banner.pack(fill="x", padx=S(18), pady=(S(2), S(6)))

    def build_phase_strip(self):
        S, f = self.S, self.f
        strip = tk.Frame(self.root, bg=PANEL, highlightthickness=1,
                         highlightbackground=BORDER)
        strip.pack(fill="x", padx=S(18), pady=S(4))

        left = tk.Frame(strip, bg=PANEL)
        left.pack(side="left", padx=S(14), pady=S(8))
        tk.Label(left, text="FLIGHT PHASE (LIVE SIMULATION)", bg=PANEL, fg=MUTED,
                 font=f(8, "bold")).pack(anchor="w")
        self.phase_label = tk.Label(left, bg=PANEL, fg=TEXT, font=f(14, "bold"))
        self.phase_label.pack(anchor="w")

        mid = tk.Frame(strip, bg=PANEL)
        mid.pack(side="left", fill="x", expand=True, padx=S(20))
        self.phase_bar = ttk.Progressbar(mid, maximum=100, style="FMS.Horizontal.TProgressbar")
        self.phase_bar.pack(fill="x", pady=(S(8), S(4)))
        self.time_label = tk.Label(mid, bg=PANEL, fg=MUTED, font=f(10))
        self.time_label.pack(anchor="w")

        right = tk.Frame(strip, bg=PANEL)
        right.pack(side="right", padx=S(14))
        self.stress_label = tk.Label(right, bg=PANEL, fg=TEXT, font=f(12, "bold"))
        self.stress_label.pack(side="left", padx=S(14))
        self.make_button(right, "📊  VIEW LIVE FLIGHT TELEMETRY", self.open_telemetry,
                         "#0e7490", "#0891b2", size=11, pady=S(6)
                         ).pack(side="left", padx=(0, S(8)))
        self.make_button(right, "⟲  RESET SYSTEM", lambda: self.reset_system(False),
                         "#26334d", "#34456a", size=9, pady=S(6)).pack(side="left")

    def build_main_area(self):
        S, f = self.S, self.f
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="x", padx=S(18), pady=S(4))

        # ---------------- LEFT: multi-angle scanner ----------------
        scan = tk.LabelFrame(main, text="  360° AI STRUCTURAL SCANNER  ", bg=PANEL, fg=CYAN,
                             font=f(11, "bold"), bd=1, relief="solid",
                             highlightbackground=BORDER)
        scan.pack(side="left", padx=(0, S(10)), fill="y")

        self.cw, self.ch = S(600), S(330)
        self.canvas = tk.Canvas(scan, width=self.cw, height=self.ch, bg=BG,
                                highlightthickness=1, highlightbackground=BORDER)
        self.canvas.pack(padx=S(12), pady=(S(10), S(6)))
        self.build_hud()

        self.scan_progress = ttk.Progressbar(scan, maximum=100,
                                             style="FMS.Horizontal.TProgressbar")
        self.scan_progress.pack(fill="x", padx=S(12), pady=(S(2), S(2)))
        self.scan_status = tk.Label(scan, bg=PANEL, fg=MUTED, font=f(10, "bold"),
                                    anchor="w", wraplength=self.cw)
        self.scan_status.pack(fill="x", padx=S(12))
        self.verdict_label = tk.Label(scan, bg=PANEL, fg=MUTED, font=f(11, "bold"),
                                      anchor="w", wraplength=self.cw, justify="left")
        self.verdict_label.pack(fill="x", padx=S(12), pady=(S(2), S(6)))

        self.start_btn = self.make_button(scan, "START DIAGNOSTIC SCAN",
                                          self.start_diagnostic, BLUE, "#3d8bff",
                                          size=15, pady=S(12))
        self.start_btn.pack(fill="x", padx=S(12), pady=(0, S(12)))

        # ---------------- RIGHT: component health grid ----------------
        grid = tk.LabelFrame(main, text="  COMPONENT HEALTH & STRUCTURAL STATUS  ", bg=PANEL,
                             fg=CYAN, font=f(11, "bold"), bd=1, relief="solid")
        grid.pack(side="left", fill="both", expand=True)
        for c in range(2):
            grid.columnconfigure(c, weight=1, uniform="g")
        for r in range(4):
            grid.rowconfigure(r, weight=1)

        for i, name in enumerate(SCAN_ORDER):
            self.cards[name] = self.make_component_card(grid, name, i // 2, i % 2)

        card = tk.Frame(grid, bg=CARD, padx=S(10), pady=S(6), highlightthickness=2,
                        highlightbackground=CARD)
        card.grid(row=3, column=1, padx=S(6), pady=S(5), sticky="nsew")
        tk.Label(card, text="OVERALL INTEGRITY", bg=CARD, fg=MUTED,
                 font=f(9, "bold")).pack(anchor="w")
        self.overall_value = tk.Label(card, bg=CARD, fg=TEXT, font=f(22, "bold"))
        self.overall_value.pack(anchor="w")
        self.overall_detail = tk.Label(card, bg=CARD, fg=MUTED, font=f(9), justify="left",
                                       anchor="w")
        self.overall_detail.pack(anchor="w", fill="x")

    def make_component_card(self, parent, name, row, col):
        S, f = self.S, self.f
        card = tk.Frame(parent, bg=CARD, padx=S(10), pady=S(6), highlightthickness=2,
                        highlightbackground=CARD)
        card.grid(row=row, column=col, padx=S(6), pady=S(5), sticky="nsew")
        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text=name.upper(), bg=CARD, fg=TEXT, font=f(10, "bold")).pack(side="left")
        health = tk.Label(top, bg=CARD, fg=TEXT, font=f(17, "bold"))
        health.pack(side="right")
        bar = tk.Canvas(card, width=S(200), height=S(8), bg=BG, highlightthickness=0)
        bar.pack(fill="x", pady=S(3))
        mid = tk.Frame(card, bg=CARD)
        mid.pack(fill="x")
        chip = tk.Label(mid, width=14, fg=BG, font=f(8, "bold"))
        chip.pack(side="left")
        detail = tk.Label(mid, bg=CARD, fg=MUTED, font=f(8))
        detail.pack(side="right")
        return {"frame": card, "health": health, "bar": bar, "chip": chip, "detail": detail}

    def build_log_panel(self):
        S, f = self.S, self.f
        panel = tk.LabelFrame(self.root, text="  AUTOMATIC DAMAGE & EVENT LOG  ", bg=PANEL,
                              fg=CYAN, font=f(11, "bold"), bd=1, relief="solid")
        panel.pack(fill="both", expand=True, padx=S(18), pady=(S(4), S(12)))

        top = tk.Frame(panel, bg=PANEL)
        top.pack(fill="x", padx=S(8), pady=(S(6), 0))
        self.make_button(top, "Save Log…", self.save_log, "#26334d", "#34456a",
                         size=9, pady=S(2)).pack(side="right", padx=S(4))
        self.make_button(top, "Clear Log", self.clear_log, "#26334d", "#34456a",
                         size=9, pady=S(2)).pack(side="right", padx=S(4))
        tk.Label(top, text="All entries are written automatically by the FMS.", bg=PANEL,
                 fg=MUTED, font=f(9, "italic")).pack(side="left")

        frame = tk.Frame(panel, bg=PANEL)
        frame.pack(fill="both", expand=True, padx=S(8), pady=S(8))
        self.log_box = tk.Text(frame, bg="#04070e", fg=TEXT, font=f(10), state="disabled",
                               wrap="word", height=6, relief="flat", padx=S(8), pady=S(6))
        scroll = ttk.Scrollbar(frame, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_box.pack(side="left", fill="both", expand=True)
        for i, color in enumerate(LEVEL_COLORS):
            self.log_box.tag_configure(f"lvl{i}", foreground=color)
        self.log_box.tag_configure("time", foreground=MUTED)

    # ==================================================================
    # MULTI-ANGLE IMAGE SYSTEM
    # ==================================================================
    def build_hud(self):
        """Permanent decorative overlay on the image: corner brackets only (no text)."""
        c, S = self.canvas, self.S
        m, L = S(8), S(26)
        for (x, y, dx, dy) in ((m, m, 1, 1), (self.cw - m, m, -1, 1),
                               (m, self.ch - m, 1, -1), (self.cw - m, self.ch - m, -1, -1)):
            c.create_line(x, y, x + dx * L, y, fill=CYAN, width=2, tags="hud")
            c.create_line(x, y, x, y + dy * L, fill=CYAN, width=2, tags="hud")

    def get_image(self, filename):
        """Return a PhotoImage fitted to the canvas, or None if unavailable."""
        if not PIL_OK:
            return None
        path = os.path.join(BASE_DIR, filename)
        if filename in self.img_cache:
            return self.img_cache[filename]
        if not os.path.exists(path):
            return None
        try:
            img = Image.open(path).convert("RGB")
            pad = self.S(10)
            scale = min((self.cw - 2 * pad) / img.width, (self.ch - 2 * pad) / img.height)
            img = img.resize((max(1, int(img.width * scale)),
                              max(1, int(img.height * scale))), RESAMPLE)
            photo = ImageTk.PhotoImage(img)
            self.img_cache[filename] = photo
            return photo
        except Exception:
            return None

    def show_view(self, filename, view_label):
        """Display an aircraft image (or a dark blue placeholder if the file is missing)."""
        c, S = self.canvas, self.S
        c.delete("img")
        photo = self.get_image(filename)
        if photo:
            self.cur_photo = photo                    # keep a reference so it isn't garbage collected
            c.create_image(self.cw // 2, self.ch // 2, image=photo, tags="img")
        else:
            c.create_rectangle(S(12), S(12), self.cw - S(12), self.ch - S(12),
                               fill=PLACEHOLDER, outline="#1d4ed8", width=2, tags="img")
            c.create_text(self.cw // 2, self.ch // 2 - S(24), text="✈", fill="#2b5fb8",
                          font=self.f(44), tags="img")
            msg = f"{filename} not found" if PIL_OK else "Pillow not installed (pip install pillow)"
            c.create_text(self.cw // 2, self.ch // 2 + S(28), text=msg, fill="#8fb4ff",
                          font=self.f(12, "bold"), tags="img")
            c.create_text(self.cw // 2, self.ch // 2 + S(52),
                          text="Place the image in the same folder as this script",
                          fill="#5d82c9", font=self.f(9), tags="img")
        c.tag_lower("img")

    # ==================================================================
    # TIMER HELPER (old timers die automatically after a reset)
    # ==================================================================
    def after_gen(self, ms, func, *args):
        self.root.after(ms, self._guard, self.gen, func, args)

    def _guard(self, gen, func, args):
        if gen == self.gen:
            func(*args)

    # ==================================================================
    # RESET
    # ==================================================================
    def reset_system(self, first=False):
        self.gen += 1                       # cancels all running timers / scans
        self.ready = False
        self.scanning = False
        self.run_no = 0
        self.canvas.delete("scanline")
        self.fatigue = {n: 0.0 for n in SCAN_ORDER}
        self.comp = {n: dict(health=100.0, scanned=False, cracks=0, last="--:--:--")
                     for n in SCAN_ORDER}
        for n in SCAN_ORDER:
            self.cards[n]["frame"].config(highlightbackground=CARD)
            self.refresh_card(n)

        self.phase_idx, self.phase_t, self.elapsed, self.flight_no = 0, 0.0, 0.0, 1
        self.sensor_levels = {k: 0 for k in SENSORS}
        for key in SENSORS:
            self.values[key] = PHASES[0][key]
            self.history[key].clear()
            self.update_sensor(key, self.values[key])
        self.update_flight_labels()

        self.start_btn.config(state="normal", text="START DIAGNOSTIC SCAN", bg=BLUE)
        self.scan_progress["value"] = 0
        self.scan_status.config(text="Scanner standing by. Press START DIAGNOSTIC SCAN.",
                                fg=MUTED)
        self.verdict_label.config(text="", fg=MUTED)
        self.show_view(*DEFAULT_VIEW)
        self.update_overall()
        self.update_master_status()
        self.ready = True

        if first:
            self.log("FMS boot complete. Flight simulation online. Scanner ready.", 0)
        else:
            self.log("System reset by operator. Fatigue and component data cleared.", 0)
        self.log(f"FLIGHT #1 STARTED. Phase: {PHASES[0]['name']}.", 0)
        self.after_gen(200, self.flight_tick)

    # ==================================================================
    # BACKGROUND FLIGHT SIMULATION (drives telemetry + structural fatigue)
    # ==================================================================
    def flight_tick(self):
        dt = 0.2
        phase = PHASES[self.phase_idx]
        self.phase_t += dt
        self.elapsed += dt
        for key, cfg in SENSORS.items():
            cur = self.values[key]
            cur += (phase[key] - cur) * 0.12
            cur += random.gauss(0, NOISE[key] * phase["noise"])
            cur = max(cfg["min"], min(cfg["max"], cur))
            self.values[key] = cur
            self.history[key].append(cur)
            self.update_sensor(key, cur)

        # structural fatigue slowly builds up, mostly during high stress
        for name in SCAN_ORDER:
            s = self.stress_for(WEIGHTS[name])
            self.fatigue[name] = min(60.0, self.fatigue[name] + FATIGUE_RATE * s * s * dt)

        if self.phase_t >= phase["dur"]:
            self.next_phase()
        self.update_flight_labels()
        if self.telem and self.telem.exists():
            self.telem.update()
        self.after_gen(200, self.flight_tick)

    def next_phase(self):
        self.phase_idx += 1
        self.phase_t = 0.0
        if self.phase_idx >= len(PHASES):
            self.phase_idx = 0
            self.elapsed = 0.0
            self.flight_no += 1
            self.log(f"FLIGHT #{self.flight_no - 1} COMPLETE. Starting FLIGHT #{self.flight_no}.", 0)
        ph = PHASES[self.phase_idx]
        self.log(f"FLIGHT PHASE: {ph['name']}.", ph["alert"])

    def stress_for(self, weights):
        total = 0.0
        for key, w in zip(("temp", "vib", "g"), weights):
            cfg = SENSORS[key]
            n = (self.values[key] - cfg["lo"]) / (cfg["warn"] - cfg["lo"])
            total += w * max(0.0, min(1.2, n))
        return total

    def update_flight_labels(self):
        ph = PHASES[self.phase_idx]
        self.phase_label.config(text=ph["name"], fg=LEVEL_COLORS[ph["alert"]])
        self.phase_bar["value"] = self.phase_t / ph["dur"] * 100
        e, t = int(self.elapsed), TOTAL_FLIGHT_TIME
        self.time_label.config(
            text=f"Flight #{self.flight_no}   T+ {e // 60:02d}:{e % 60:02d} / "
                 f"{t // 60:02d}:{t % 60:02d}")
        stress = self.stress_for((1 / 3, 1 / 3, 1 / 3))
        lvl = 2 if stress >= 0.8 else 1 if stress >= 0.45 else 0
        self.stress_label.config(text=f"STRESS INDEX  {stress:.2f}", fg=LEVEL_COLORS[lvl])

    def update_sensor(self, key, value):
        cfg = SENSORS[key]
        level = sensor_level(cfg, value)
        old = self.sensor_levels[key]
        if self.ready and level != old:
            text = f"{value:.{cfg['decimals']}f}"
            if level > old:
                limit = cfg["caution"] if level == 1 else cfg["warn"]
                self.log(f"{LEVEL_NAMES[level]}: {cfg['label']} reached {text} {cfg['unit']} "
                         f"(limit {limit} {cfg['unit']}).", level)
            else:
                self.log(f"RECOVERY: {cfg['label']} back to {LEVEL_NAMES[level]} "
                         f"at {text} {cfg['unit']}.", level)
        self.sensor_levels[key] = level
        if self.ready and level != old:
            self.update_master_status()

    def open_telemetry(self):
        if self.telem and self.telem.exists():
            self.telem.win.deiconify()
            self.telem.win.lift()
            self.telem.win.focus_force()
            return
        self.telem = TelemetryWindow(self)
        self.log("Live telemetry window opened.", 0)

    # ==================================================================
    # CONTROLLED DIAGNOSTIC SCAN (runs through all components exactly once)
    # ==================================================================
    def start_diagnostic(self):
        if self.scanning:
            return
        self.scanning = True
        self.run_no += 1
        self.scan_index = 0
        self.run_cracks = 0
        self.run_worst_crack = -1
        for n in SCAN_ORDER:                         # fresh results for this run
            self.comp[n] = dict(health=100.0, scanned=False, cracks=0, last="--:--:--")
            self.cards[n]["frame"].config(highlightbackground=CARD)
            self.refresh_card(n)
        self.update_overall()
        self.update_master_status()
        self.verdict_label.config(text="", fg=MUTED)
        self.start_btn.config(state="disabled", bg="#26334d")

        stress = self.stress_for((1 / 3, 1 / 3, 1 / 3))
        self.log(f"DIAGNOSTIC SCAN #{self.run_no} STARTED. Flight phase: "
                 f"{PHASES[self.phase_idx]['name']} (stress index {stress:.2f}).", 0)
        self.begin_scan()

    def begin_scan(self):
        name = SCAN_ORDER[self.scan_index]
        n = len(SCAN_ORDER)
        filename, view = VIEW_FOR[name]
        self.show_view(filename, view)               # image changes with the component
        self.cards[name]["frame"].config(highlightbackground=CYAN)
        self.cards[name]["chip"].config(text="SCANNING…", bg=CYAN)
        self.start_btn.config(text=f"SCANNING…  {self.scan_index + 1} / {n}")
        self.scan_status.config(text=f"AI camera scanning: {name}  ({view.lower()})", fg=CYAN)
        self.scan_step(name, 0)

    def scan_step(self, name, step):
        total = 28
        pad = self.S(14)
        x = pad + (self.cw - 2 * pad) * step / total
        self.canvas.delete("scanline")
        self.canvas.create_line(x - self.S(6), 0, x - self.S(6), self.ch, fill="#0a5f6e",
                                width=self.S(3), tags=("hud", "scanline"))
        self.canvas.create_line(x, 0, x, self.ch, fill=CYAN, width=2, tags=("hud", "scanline"))
        n = len(SCAN_ORDER)
        self.scan_progress["value"] = (self.scan_index + step / total) / n * 100
        if step < total:
            self.after_gen(55, self.scan_step, name, step + 1)
        else:
            self.canvas.delete("scanline")
            self.finish_scan(name)

    def finish_scan(self, name):
        c = self.comp[name]
        stress = self.stress_for(WEIGHTS[name])
        fatigue = self.fatigue[name]
        health = 100.0 - fatigue
        cracked = None

        # crack chance rises with current stress and accumulated fatigue
        chance = min(0.85, 0.03 + 0.28 * stress ** 2 + fatigue / 150.0)
        if random.random() < chance:
            sev_name, level, (lo, hi), (dlo, dhi) = random.choices(
                SEVERITIES, weights=[max(0.1, 1 - stress), stress, stress ** 3])[0]
            length = random.randint(lo, hi)
            conf = random.randint(85, 99)
            health -= random.uniform(dlo, dhi)
            c["cracks"] += 1
            self.run_cracks += 1
            self.run_worst_crack = max(self.run_worst_crack, level)
            places = CRACK_PLACES.get(name, [name.lower()])
            place = random.choice(places)
            cracked = (sev_name, level, length, conf, place)

        c["health"] = max(0.0, health)
        c["scanned"] = True
        c["last"] = datetime.now().strftime("%H:%M:%S")
        s_name, s_color, s_level = status_of(c["health"])

        if cracked:
            sev_name, level, length, conf, place = cracked
            action = ["Log for next routine inspection.",
                      "Schedule maintenance check within 10 flight hours.",
                      "GROUND AIRCRAFT. Immediate structural inspection required."][level]
            self.log(f"DAMAGE DETECTED: {sev_name} crack (~{length} mm) on {place}. "
                     f"AI confidence {conf}%. {name} health {c['health']:.0f}% ({s_name}). "
                     f"Action: {action}", level)
        else:
            self.log(f"{name}: no structural damage found. Health {c['health']:.0f}% "
                     f"({s_name}).", s_level)

        self.cards[name]["frame"].config(highlightbackground=CARD)
        self.refresh_card(name)
        self.update_overall()
        self.update_master_status()
        note = f"  |  {cracked[0].upper()} CRACK DETECTED" if cracked else "  |  no damage"
        self.scan_status.config(text=f"{name}: health {c['health']:.0f}% - {s_name}{note}",
                                fg=LEVEL_COLORS[cracked[1]] if cracked else s_color)

        self.scan_index += 1
        if self.scan_index < len(SCAN_ORDER):
            self.after_gen(450, self.begin_scan)
        else:
            self.after_gen(450, self.finish_diagnostic)

    def finish_diagnostic(self):
        """Runs once after the last component: prints the final status and STOPS."""
        healths = {n: v["health"] for n, v in self.comp.items()}
        avg = sum(healths.values()) / len(healths)
        worst = min(healths, key=healths.get)
        levels = [status_of(h)[2] for h in healths.values()]

        if max(levels) == 2 or self.run_worst_crack == 2:
            verdict, vlevel = "GROUNDED - CRITICAL STRUCTURAL DAMAGE. Inspection required before flight.", 2
        elif max(levels) == 1 or self.run_worst_crack == 1:
            verdict, vlevel = "MAINTENANCE REQUIRED - aircraft needs inspection soon.", 1
        elif self.run_cracks:
            verdict, vlevel = "CLEARED FOR FLIGHT - minor cracks logged for monitoring.", 0
        else:
            verdict, vlevel = "CLEARED FOR FLIGHT - no structural damage detected.", 0

        self.log(f"DIAGNOSTIC SCAN #{self.run_no} COMPLETE. Overall integrity {avg:.0f}%, "
                 f"{self.run_cracks} crack(s) found, weakest part: {worst} "
                 f"({healths[worst]:.0f}%).", vlevel)
        self.log(f"FINAL STATUS: {verdict}", vlevel)

        self.scanning = False
        self.scan_progress["value"] = 100
        self.scan_status.config(
            text=f"Diagnostic #{self.run_no} complete. Overall integrity {avg:.0f}%.",
            fg=LEVEL_COLORS[vlevel])
        self.verdict_label.config(text=f"FINAL STATUS: {verdict}", fg=LEVEL_COLORS[vlevel])
        self.start_btn.config(state="normal", text="↻  RE-RUN DIAGNOSTIC SCAN", bg=BLUE)
        self.show_view(*DEFAULT_VIEW)
        self.update_master_status()

    # ==================================================================
    # DASHBOARD UPDATES
    # ==================================================================
    def refresh_card(self, name):
        c, w = self.comp[name], self.cards[name]
        bar_w = self.S(200)
        if not c["scanned"]:
            w["health"].config(text="--%", fg=MUTED)
            w["chip"].config(text="AWAITING SCAN", bg=GREY)
            self.draw_bar(w["bar"], 0, GREY)
        else:
            s_name, s_color, _ = status_of(c["health"])
            w["health"].config(text=f"{c['health']:.0f}%", fg=s_color)
            w["chip"].config(text=s_name, bg=s_color)
            self.draw_bar(w["bar"], c["health"], s_color)
        w["detail"].config(text=f"Cracks: {c['cracks']}   {c['last']}")

    def draw_bar(self, canvas, pct, color):
        canvas.delete("all")
        width = max(canvas.winfo_width(), self.S(200))
        canvas.create_rectangle(0, 0, width * pct / 100, self.S(8), fill=color, outline="")

    def update_overall(self):
        scanned = {n: v for n, v in self.comp.items() if v["scanned"]}
        if not scanned:
            self.overall_value.config(text="--%", fg=MUTED)
            self.overall_detail.config(text="Waiting for diagnostic scan…")
            return
        avg = sum(v["health"] for v in scanned.values()) / len(scanned)
        worst = min(scanned, key=lambda n: scanned[n]["health"])
        s_name, s_color, _ = status_of(avg)
        total = sum(v["cracks"] for v in self.comp.values())
        self.overall_value.config(text=f"{avg:.0f}%", fg=s_color)
        self.overall_detail.config(
            text=f"{s_name}\nWeakest: {worst} ({scanned[worst]['health']:.0f}%)\n"
                 f"Total cracks: {total}")

    def update_master_status(self):
        levels = list(self.sensor_levels.values())
        levels += [status_of(v["health"])[2] for v in self.comp.values() if v["scanned"]]
        worst = max(levels)
        messages = ["ALL SYSTEMS NORMAL", "MASTER CAUTION - CHECK SYSTEMS",
                    "MASTER WARNING - IMMEDIATE ACTION REQUIRED"]
        self.banner.config(text=messages[worst], bg=LEVEL_COLORS[worst], fg=BG)

    # ==================================================================
    # LOGGING
    # ==================================================================
    def log(self, message, level=0):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[{stamp}] ", "time")
        self.log_box.insert("end", f"{message}\n", f"lvl{level}")
        self.log_box.see("end")
        self.log_box.config(state="disabled")      # read-only: only the FMS writes

    def clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")
        self.log("Log cleared by operator.", 0)

    def save_log(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt",
                                            filetypes=[("Text files", "*.txt")],
                                            initialfile="fms_log.txt")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.log_box.get("1.0", "end"))
            self.log(f"Log saved to {path}", 0)

    def tick_clock(self):
        self.clock_label.config(text=datetime.now().strftime("%Y-%m-%d   %H:%M:%S"))
        self.root.after(1000, self.tick_clock)


FONT = "Arial"

if __name__ == "__main__":
    root = tk.Tk()
    FMSApp(root)
    root.mainloop()