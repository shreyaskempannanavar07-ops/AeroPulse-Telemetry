import sys, os, random, time
import tkinter as tk
from tkinter import ttk
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass
try:
    from PIL import ImageTk, Image
    PIL_OK = True
except Exception:
    PIL_OK = False

BG, PANEL, ALT, TEXT = "#060b16", "#0c1424", "#101a30", "#e6edf7"
CYAN, BLUE, GREEN, RED, AMBER, MUTED = "#00e5ff", "#3d8bff", "#39ff88", "#ff4d6d", "#ffc247", "#7f8ca8"
PH = "#0a1a3a"
F = "Segoe UI"
BASE = os.path.dirname(os.path.abspath(sys.argv[0])) if sys.argv and sys.argv[0] else os.getcwd()
IMG = {"front": "plane_front.png", "top": "plane_top.png", "left": "plane_left.png", "right": "plane_right.png"}
ZONES = [("Nose", "front", 1.0), ("Fuselage Top", "top", 0.8), ("Fuselage Left", "left", 0.9),
         ("Fuselage Right", "right", 0.9), ("Flaps", "top", 1.3), ("Elevators", "top", 1.1),
         ("Stabilizers", "top", 1.0)]
PHASES = [("TAKEOFF ROLL", "HIGH VIBRATION", 3.2), ("CLIMB", "THERMAL LOAD", 2.4),
          ("CRUISE", "STABLE FIELD", 0.9), ("TURBULENCE", "SHEAR STRESS", 3.8),
          ("DESCENT", "PRESSURE CHANGE", 2.0), ("APPROACH", "FLAP DRAG LOAD", 2.6),
          ("LANDING", "IMPACT SHOCK", 4.0)]
N = len(PHASES)


def lbl(p, t, f, fg, bg=PANEL, **k):
    return tk.Label(p, text=t, font=(F, f, "bold") if k.pop("b", True) else (F, f), fg=fg, bg=bg, **k)


class App:
    def __init__(self, root):
        self.root = root
        root.title("Quantum Entanglement Telemetry Terminal")
        root.configure(bg=BG)
        root.geometry("1280x860")
        root.minsize(1100, 760)
        self.health = {z[0]: 100.0 for z in ZONES}
        self.scanning = self.done = self.paused = False
        self.i = 0
        self.elapsed = 0.0
        self.last = 0.0
        self.clk = self.job = self.twin = self.tjob = self.view = self.photo = None
        self.cache = {}
        self.coh, self.var, self.lag, self.stress = 99.0, 0.0021, 1.2, 1.0
        st = ttk.Style(root)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        for n, c, d in (("Neon", CYAN, BLUE), ("Done", GREEN, GREEN), ("Health", GREEN, GREEN)):
            st.configure(n + ".Horizontal.TProgressbar", troughcolor=ALT, background=c,
                         bordercolor=PANEL, lightcolor=c, darkcolor=d)
        self.build()
        self.show("top")
        root.after(800, self.start)

    def build(self):
        r = self.root
        h = tk.Frame(r, bg=BG)
        h.pack(fill="x", padx=18, pady=(12, 4))
        lbl(h, "QUANTUM ENTANGLEMENT TELEMETRY TERMINAL", 20, CYAN, BG).pack(anchor="w")
        s = tk.Frame(h, bg=BG)
        s.pack(anchor="w", pady=(2, 0))
        tk.Frame(s, bg=BLUE, width=4).pack(side="left", fill="y", padx=(0, 10))
        t = tk.Frame(s, bg=BG)
        t.pack(side="left")
        lbl(t, "AIRBUS A350-900  |  SUBSURFACE QUANTUM STATE MATRIX", 14, BLUE, BG).pack(anchor="w")
        lbl(t, "Subatomic Fleet Tracking  •  360° Airframe Diagnostic Suite", 10, MUTED, BG, b=False).pack(anchor="w")

        bt = tk.Frame(r, bg=BG)
        bt.pack(side="bottom", fill="x", padx=18, pady=(6, 14))
        bt.columnconfigure(0, weight=1)
        bt.columnconfigure(1, weight=1)
        self.sb = tk.Button(bt, text="⚡ LIVE AUTONOMOUS STREAMING", font=(F, 13, "bold"), bg=BLUE, fg="white",
                            activebackground=CYAN, activeforeground=BG, relief="flat", pady=12,
                            cursor="hand2", command=self.toggle)
        self.sb.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.tb = tk.Button(bt, text="📊 VIEW LIVE TELEMETRY", font=(F, 13, "bold"), bg=ALT, fg=CYAN,
                            activebackground=CYAN, activeforeground=BG, relief="flat", pady=12,
                            cursor="hand2", command=self.open_tele)
        self.tb.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        c = tk.Frame(r, bg=PANEL, highlightbackground=BLUE, highlightthickness=1)
        c.pack(fill="x", padx=18, pady=8)
        tr = tk.Frame(c, bg=PANEL)
        tr.pack(fill="x", padx=14, pady=(10, 2))
        lbl(tr, "QUANTUM CHRONO-TIMELINE", 12, CYAN).pack(side="left")
        self.clock = lbl(tr, "T+ 00:00.0", 14, GREEN)
        self.clock.pack(side="right")
        self.rb = tk.Button(tr, text="🔄 REPLAY SIMULATION", font=(F, 10, "bold"), bg=ALT, fg=CYAN,
                            activebackground=CYAN, activeforeground=BG, relief="flat", padx=12, pady=2,
                            cursor="hand2", command=self.start)
        self.rb.pack(side="right", padx=(0, 18))
        self.bar = ttk.Progressbar(c, style="Neon.Horizontal.TProgressbar", maximum=N, value=0)
        self.bar.pack(fill="x", padx=14, pady=6)
        self.phase = lbl(c, "⚪ PHASE: STANDBY", 13, AMBER)
        self.phase.pack(anchor="w", padx=14)
        self.stl = lbl(c, "Stress environment: --", 10, MUTED, b=False)
        self.stl.pack(anchor="w", padx=14)
        self.lock = lbl(c, "", 12, GREEN)
        self.lock.pack(anchor="w", padx=14, pady=(2, 10))

        b = tk.Frame(r, bg=BG)
        b.pack(fill="both", expand=True, padx=18, pady=6)
        b.columnconfigure(0, weight=3)
        b.columnconfigure(1, weight=2)
        b.rowconfigure(0, weight=1)
        L = tk.Frame(b, bg=PANEL, highlightbackground=BLUE, highlightthickness=1)
        L.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.vt = lbl(L, "360° AIRFRAME VIEW", 12, CYAN)
        self.vt.pack(anchor="w", padx=12, pady=(10, 4))
        self.il = tk.Label(L, bg=PH, bd=0)
        self.il.pack(fill="both", expand=True, padx=12, pady=6)
        self.zl = lbl(L, "Active zone: --", 13, GREEN)
        self.zl.pack(anchor="w", padx=12, pady=(0, 10))

        R = tk.Frame(b, bg=PANEL, highlightbackground=BLUE, highlightthickness=1)
        R.grid(row=0, column=1, sticky="nsew")
        lbl(R, "COMPONENT HEALTH", 12, CYAN).pack(anchor="w", padx=14, pady=(12, 6))
        rc = tk.Frame(R, bg=PANEL)
        rc.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        rc.columnconfigure(0, weight=1)
        self.hb, self.hl = {}, {}
        for i, (n, _, _) in enumerate(ZONES):
            rc.rowconfigure(i, weight=1)
            row = tk.Frame(rc, bg=ALT)
            row.grid(row=i, column=0, sticky="nsew", pady=4)
            inn = tk.Frame(row, bg=ALT)
            inn.pack(fill="both", expand=True, padx=12, pady=8)
            tp = tk.Frame(inn, bg=ALT)
            tp.pack(fill="x")
            lbl(tp, n.upper(), 11, TEXT, ALT).pack(side="left")
            v = lbl(tp, "100.0%", 12, GREEN, ALT)
            v.pack(side="right")
            pb = ttk.Progressbar(inn, style="Health.Horizontal.TProgressbar", maximum=100, value=100)
            pb.pack(fill="x", pady=(6, 0))
            self.hb[n], self.hl[n] = pb, v

    def show(self, v):
        if v == self.view:
            return
        self.view = v
        fn = IMG[v]
        p = os.path.join(BASE, fn)
        W, H = 640, 400
        ph, ok = None, os.path.isfile(p)
        try:
            if PIL_OK and ok:
                if p not in self.cache:
                    im = Image.open(p).convert("RGBA")
                    im.thumbnail((W, H), Image.LANCZOS)
                    self.cache[p] = ImageTk.PhotoImage(im)
                ph = self.cache[p]
        except Exception:
            ph = None
        if ph is None:
            try:
                k = "ph" + v
                if k not in self.cache:
                    if PIL_OK:
                        self.cache[k] = ImageTk.PhotoImage(Image.new("RGB", (W, H), PH))
                    else:
                        g = tk.PhotoImage(width=W, height=H)
                        g.put(PH, to=(0, 0, W, H))
                        self.cache[k] = g
                ph = self.cache[k]
            except Exception:
                ph = None
        self.photo = ph
        self.il.config(image=ph if ph else "", compound="center", fg=MUTED, font=(F, 12),
                       text="" if ok and ph else f"[{fn} not found]")
        self.vt.config(text="360° AIRFRAME VIEW  •  " + v.upper())

    def cancel(self):
        for j in (self.clk, self.job):
            if j:
                try:
                    self.root.after_cancel(j)
                except Exception:
                    pass
        self.clk = self.job = None

    def start(self):
        self.cancel()
        self.scanning, self.done, self.paused = True, False, False
        self.i = 0
        self.elapsed = 0.0
        self.last = time.time()
        self.health = {z[0]: 100.0 for z in ZONES}
        for n in self.hb:
            self.hb[n].config(value=100)
            self.hl[n].config(text="100.0%", fg=GREEN)
        self.bar.config(style="Neon.Horizontal.TProgressbar", value=0)
        self.clock.config(text="T+ 00:00.0")
        self.lock.config(text="")
        self.phase.config(text="⚪ PHASE: STANDBY", fg=CYAN)
        self.stl.config(text="Stress environment: --")
        self.zl.config(text="Active zone: --")
        self.sb.config(text="⚡ LIVE AUTONOMOUS STREAMING", bg=BLUE, state="normal")
        self.tick()
        self.step()

    def fmt(self):
        m = int(self.elapsed // 60)
        return f"T+ {m:02d}:{self.elapsed - m * 60:04.1f}"

    def tick(self):
        if self.scanning and not self.paused:
            now = time.time()
            self.elapsed += now - self.last
            self.last = now
            self.clock.config(text=self.fmt())
            self.clk = self.root.after(100, self.tick)

    def toggle(self):
        if not self.scanning:
            return
        if not self.paused:
            self.paused = True
            self.cancel()
            self.sb.config(text="⏸️ SIMULATION PAUSED", bg=AMBER, fg=BG)
        else:
            self.paused = False
            self.last = time.time()
            self.sb.config(text="⚡ LIVE AUTONOMOUS STREAMING", bg=BLUE, fg="white")
            self.tick()
            self.job = self.root.after(1400, self.step)

    def step(self):
        if not self.scanning or self.paused:
            return
        if self.i >= len(ZONES):
            return self.finish()
        z, v, sens = ZONES[self.i]
        pn, sn, base = PHASES[self.i % N]
        self.bar.config(value=self.i + 1)
        self.phase.config(text=f"🔵 PHASE {self.i + 1}/{N}: {pn}", fg=CYAN)
        self.stl.config(text=f"Stress environment: {sn}  (load x{base:.1f})")
        self.zl.config(text=f"Active zone: {z}")
        self.show(v)
        self.stress = base
        self.health[z] = max(0.0, self.health[z] - base * sens * random.uniform(0.8, 3.2))
        hv = self.health[z]
        self.hb[z].config(value=hv)
        self.hl[z].config(text=f"{hv:.1f}%", fg=GREEN if hv >= 95 else AMBER if hv >= 90 else RED)
        self.i += 1
        self.job = self.root.after(1400, self.step)

    def finish(self):
        self.scanning, self.done, self.paused = False, True, False
        self.cancel()
        self.clock.config(text=self.fmt())
        self.bar.config(style="Done.Horizontal.TProgressbar", value=N)
        self.phase.config(text="🟢 PHASE: DIAGNOSTICS COMPLETED", fg=GREEN)
        self.lock.config(text="🔒 DATA INTEGRITY LOCKED - REPORT SECURED")
        self.stl.config(text="Stress environment: scan finished")
        self.zl.config(text="Active zone: ALL ZONES SCANNED")
        self.sb.config(text="🔒 SIMULATION COMPLETE", bg=BLUE, fg="white")
        self.stress = 0.3

    def open_tele(self):
        if self.twin is not None and self.twin.winfo_exists():
            self.twin.lift()
            return
        w = tk.Toplevel(self.root)
        w.title("Live Quantum Telemetry")
        w.configure(bg=BG)
        w.geometry("520x470")
        w.protocol("WM_DELETE_WINDOW", self.close_tele)
        self.twin = w
        lbl(w, "LIVE QUANTUM TELEMETRY", 16, CYAN, BG).pack(pady=(16, 10))

        def card(t, c):
            f = tk.Frame(w, bg=PANEL, highlightbackground=c, highlightthickness=1)
            f.pack(fill="x", padx=20, pady=7)
            lbl(f, t, 11, MUTED).pack(anchor="w", padx=14, pady=(10, 0))
            v = lbl(f, "--", 26, c)
            v.pack(anchor="w", padx=14, pady=(0, 10))
            return v

        self.cv = card("Quantum Coherence Stability (%)", GREEN)
        self.vv = card("Subatomic Phase Variance (Δψ)", CYAN)
        self.sv = card("Instant Entanglement Sync (μs-lag)", BLUE)
        self.ts = lbl(w, "", 10, GREEN, BG)
        self.ts.pack(pady=8)
        self.upd()

    def close_tele(self):
        if self.tjob:
            try:
                self.root.after_cancel(self.tjob)
            except Exception:
                pass
            self.tjob = None
        if self.twin is not None:
            try:
                self.twin.destroy()
            except Exception:
                pass
        self.twin = None

    def upd(self):
        if self.twin is None or not self.twin.winfo_exists():
            self.tjob = None
            return
        s = self.stress
        self.coh += (99.5 - s * 1.6 - self.coh) * 0.25 + random.uniform(-0.25, 0.25)
        self.coh = max(80.0, min(99.99, self.coh))
        self.var = max(0.0001, 0.0015 * s + random.uniform(-0.0004, 0.0006))
        self.lag = max(0.10, 0.9 + s * 0.45 + random.uniform(-0.15, 0.2))
        self.cv.config(text=f"{self.coh:6.2f} %")
        self.vv.config(text=f"{self.var:.4f} Δψ")
        self.sv.config(text=f"{self.lag:5.2f} μs")
        if self.done:
            self.ts.config(text="🔒 SCAN LOCKED - IDLE BASELINE FEED", fg=GREEN)
        elif self.paused:
            self.ts.config(text="⏸️ SIMULATION PAUSED", fg=AMBER)
        else:
            self.ts.config(text="● LIVE - SCAN ACTIVE", fg=CYAN)
        self.tjob = self.root.after(250, self.upd)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()