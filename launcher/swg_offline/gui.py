"""The launcher window: pick a play style, press Play, watch the galaxy boot and save."""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import presets
from .session import Session, Stage
from .settings import ALL_GROUND_ZONES, Settings

BUSY = {Stage.CHECKING, Stage.BOOTING, Stage.SAVING}


class LauncherWindow:
    def __init__(self, root: tk.Tk, settings: Settings):
        self.root = root
        self.settings = settings
        self.session = None
        self.events = queue.Queue()
        self.stage = None
        self.closing = False

        root.title("SWG Offline")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(frame, text="Star Wars Galaxies — offline", font=("Segoe UI", 14, "bold")).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 12))
        row += 1

        ttk.Label(frame, text="SWG folder").grid(row=row, column=0, sticky="w")
        self.swg_dir = tk.StringVar(value=settings.swg_dir)
        ttk.Entry(frame, textvariable=self.swg_dir, width=44).grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="Browse…", command=self.browse).grid(row=row, column=2)
        row += 1

        ttk.Label(frame, text="Account").grid(row=row, column=0, sticky="w", pady=(6, 0))
        self.account = tk.StringVar(value=settings.account)
        ttk.Entry(frame, textvariable=self.account, width=20).grid(row=row, column=1, sticky="w", padx=6, pady=(6, 0))
        row += 1

        styles = ttk.LabelFrame(frame, text="Play style", padding=8)
        styles.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.preset = tk.StringVar(value=settings.preset)
        for preset in presets.PRESETS.values():
            ttk.Radiobutton(styles, text=preset.title, value=preset.key, variable=self.preset).pack(anchor="w")
            ttk.Label(styles, text=preset.description, foreground="#666", wraplength=420).pack(
                anchor="w", padx=(22, 0), pady=(0, 4))
        row += 1

        planets = ttk.LabelFrame(frame, text="Planets (fewer boot faster and use less memory)", padding=8)
        planets.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.zones = {}
        for i, zone in enumerate(ALL_GROUND_ZONES):
            var = tk.BooleanVar(value=zone in settings.zones)
            ttk.Checkbutton(planets, text=zone, variable=var).grid(row=i // 4, column=i % 4, sticky="w", padx=4)
            self.zones[zone] = var
        row += 1

        self.play = ttk.Button(frame, text="Play", command=self.start)
        self.play.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(16, 8), ipady=4)
        row += 1

        self.stage_label = ttk.Label(frame, text="Ready.", font=("Segoe UI", 10, "bold"))
        self.stage_label.grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1
        self.detail = ttk.Label(frame, text="", foreground="#666", width=60)
        self.detail.grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        row += 1
        log_button = ttk.Button(frame, text="Open server log", command=self.open_log)
        log_button.grid(row=row, column=2, sticky="e", pady=(8, 0))

        self.controls = [w for w in frame.winfo_children()
                         if isinstance(w, (ttk.Entry, ttk.Button)) and w is not log_button]
        self.controls += list(styles.winfo_children()) + list(planets.winfo_children())

        root.after(100, self.poll)

    def browse(self):
        path = filedialog.askdirectory(title="Your SWGEmu client folder (holds SWGEmu.exe)",
                                       initialdir=self.swg_dir.get() or None)
        if path:
            self.swg_dir.set(str(Path(path)))

    def collect(self) -> Settings:
        s = self.settings
        s.swg_dir = self.swg_dir.get().strip()
        s.account = self.account.get().strip()
        s.preset = self.preset.get()
        s.zones = [z for z, var in self.zones.items() if var.get()]
        return s

    def start(self):
        settings = self.collect()
        problems = settings.validate()
        if problems:
            messagebox.showerror("SWG Offline", "\n".join(problems))
            return
        settings.save()
        self.set_busy(True)
        self.session = Session(settings, lambda stage, text: self.events.put((stage, text)))
        threading.Thread(target=self.session.run, name="session", daemon=True).start()

    def set_busy(self, busy: bool):
        for w in self.controls:
            try:
                w.state(["disabled"] if busy else ["!disabled"])
            except (AttributeError, tk.TclError):
                pass

    def poll(self):
        try:
            while True:
                self.show(*self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def show(self, stage: Stage, text: str):
        if stage != self.stage:
            if stage in BUSY:
                self.progress.start(12)
            else:
                self.progress.stop()
            if stage == Stage.PLAYING:
                self.root.iconify()
            elif self.stage == Stage.PLAYING:
                self.root.deiconify()
        self.stage = stage
        self.stage_label.config(text=stage.value + ("…" if stage in BUSY else ""))
        self.detail.config(text=text.splitlines()[-1][:90] if text else "")

        if stage in (Stage.DONE, Stage.FAILED):
            self.session = None
            self.set_busy(False)
            if stage == Stage.FAILED:
                messagebox.showerror("SWG Offline", text)
            if self.closing:
                self.root.destroy()

    def on_close(self):
        if self.session is None:
            self.root.destroy()
            return
        if self.stage == Stage.SAVING:
            return  # never interrupt a save
        if messagebox.askyesno("SWG Offline", "Stop the galaxy? It saves before shutting down."):
            self.closing = True
            self.session.cancel()

    def open_log(self):
        log = Session(self.settings, lambda *_: None).server_log
        if not log.exists():
            messagebox.showinfo("SWG Offline", "No server log yet.")
        elif os.name == "nt":
            os.startfile(str(log))  # noqa: S606 - opening the player's own log file
        else:
            subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", str(log)])


def main(settings: Settings) -> None:
    root = tk.Tk()
    LauncherWindow(root, settings)
    root.mainloop()
