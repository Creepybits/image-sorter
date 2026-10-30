"""
Image Sorter: a small window around sort_images.py for people who'd rather not use a terminal.

Pick a folder, press Analyze, look at the preview sheets, then press Move. Nothing moves until you say so,
and "Undo last sort" puts everything back.

    Start.bat            (Windows)
    python sort_images_gui.py
"""
import json
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# With pythonw there is no console, and print() would crash on a missing stdout
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w"))

import sort_images as core
import undo_sort

SETTINGS = Path.home() / ".image_sorter.json"
DEFAULT_DEST = str(Path.home() / "Pictures" / "Sorted")
MISSING_LIBS = ("The AI libraries are not installed yet.\n\n"
                "On Windows, close this window and run setup.bat once (or just use Start.bat). "
                "Elsewhere run:  pip install -r requirements.txt")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Image Sorter")
        self.minsize(560, 520)
        s = self.load_settings()
        self.folder = tk.StringVar(value=s.get("folder", str(Path.home() / "Pictures")))
        self.dest = tk.StringVar(value=s.get("dest", DEFAULT_DEST))
        self.sub = tk.BooleanVar(value=s.get("sub", False))
        self.status = tk.StringVar(value="Choose a folder of images, then press Analyze.")
        self.results = None  # [(path, category, score)] from the last analysis
        self.analysed_folder = None
        self.sheets = None
        self.cancel_flag = threading.Event()
        self.events = queue.Queue()
        self.busy = False
        self.build()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.poll)

    # ---- layout ----
    def build(self):
        pad = {"padx": 12, "pady": 6}
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        box = ttk.LabelFrame(root, text="1. Images to sort")
        box.pack(fill="x", **pad)
        ttk.Entry(box, textvariable=self.folder).grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ttk.Button(box, text="Browse…", command=lambda: self.browse(self.folder)).grid(row=0, column=1, padx=8)
        ttk.Checkbutton(box, text="Include subfolders", variable=self.sub).grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        box.columnconfigure(0, weight=1)

        box = ttk.LabelFrame(root, text="2. Where the sorted folders go")
        box.pack(fill="x", **pad)
        ttk.Entry(box, textvariable=self.dest).grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ttk.Button(box, text="Browse…", command=lambda: self.browse(self.dest)).grid(row=0, column=1, padx=8)
        box.columnconfigure(0, weight=1)

        box = ttk.LabelFrame(root, text="3. Analyze (nothing is moved yet)")
        box.pack(fill="both", expand=True, **pad)
        row = ttk.Frame(box)
        row.pack(fill="x", padx=8, pady=8)
        self.analyze_btn = ttk.Button(row, text="Analyze", command=self.analyze)
        self.analyze_btn.pack(side="left")
        self.cancel_btn = ttk.Button(row, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=8)
        self.bar = ttk.Progressbar(box, mode="determinate")
        self.bar.pack(fill="x", padx=8)
        ttk.Label(box, textvariable=self.status, wraplength=500, justify="left").pack(fill="x", padx=8, pady=6)

        self.table = ttk.Treeview(box, columns=("images",), height=8)
        self.table.heading("#0", text="Category")
        self.table.heading("images", text="Images")
        self.table.column("images", width=80, anchor="e", stretch=False)
        self.table.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        row = ttk.Frame(box)
        row.pack(fill="x", padx=8, pady=(0, 8))
        self.preview_btn = ttk.Button(row, text="Show previews", command=self.show_previews, state="disabled")
        self.preview_btn.pack(side="left")
        self.move_btn = ttk.Button(row, text="Move images", command=self.move, state="disabled")
        self.move_btn.pack(side="right")

        row = ttk.Frame(root)
        row.pack(fill="x", **pad)
        self.undo_btn = ttk.Button(row, text="Undo last sort…", command=self.undo)
        self.undo_btn.pack(side="left")
        ttk.Button(row, text="Edit categories…", command=lambda: core.open_folder(str(core.HERE / "categories.json"))).pack(side="left", padx=8)

    # ---- settings ----
    def load_settings(self):
        try:
            return json.loads(SETTINGS.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_settings(self):
        try:
            SETTINGS.write_text(json.dumps({"folder": self.folder.get(), "dest": self.dest.get(), "sub": self.sub.get()}), encoding="utf-8")
        except Exception:
            pass  # remembering the last choices is a convenience only

    def on_close(self):
        self.save_settings()
        self.cancel_flag.set()
        self.destroy()

    # ---- helpers ----
    def browse(self, var):
        chosen = filedialog.askdirectory(initialdir=var.get() if os.path.isdir(var.get()) else str(Path.home()), parent=self)
        if chosen:
            var.set(os.path.normpath(chosen))
            if var is self.folder:
                self.clear_results()

    def clear_results(self):
        self.results = None
        self.table.delete(*self.table.get_children())
        self.move_btn.config(state="disabled", text="Move images")
        self.preview_btn.config(state="disabled")
        self.bar["value"] = 0

    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.analyze_btn.config(state=state)
        self.undo_btn.config(state=state)
        self.cancel_btn.config(state="normal" if busy else "disabled")
        if busy:
            self.move_btn.config(state="disabled")
            self.preview_btn.config(state="disabled")
        elif self.results:
            self.move_btn.config(state="normal")
            self.preview_btn.config(state="normal")

    def run_in_thread(self, work):
        """Runs work() off the UI thread; it reports back through self.events."""
        def target():
            try:
                work()
            except ImportError:
                self.events.put(("error", MISSING_LIBS))
            except Exception as e:
                self.events.put(("error", f"{type(e).__name__}: {e}"))
        threading.Thread(target=target, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, *data = self.events.get_nowait()
                getattr(self, "on_" + kind)(*data)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    # ---- analyze ----
    def analyze(self):
        folder, dest = self.folder.get().strip(), self.dest.get().strip()
        if not os.path.isdir(folder):
            messagebox.showwarning("Image Sorter", "Please choose a folder that exists.", parent=self)
            return
        if not dest:
            messagebox.showwarning("Image Sorter", "Please choose where the sorted folders should go.", parent=self)
            return
        self.save_settings()
        self.clear_results()
        self.cancel_flag.clear()
        self.set_busy(True)
        self.status.set("Looking for images…")
        sub = self.sub.get()

        def work():
            categories, nsfw, nsfw_min, other_below = core.load_categories(str(core.HERE / "categories.json"))
            paths = core.list_images(folder, sub)
            if not paths:
                self.events.put(("empty",))
                return
            self.events.put(("loading", len(paths)))
            results = core.classify(paths, categories, nsfw, nsfw_min, other_below, os.environ.get("SORT_MODEL") or "openai/clip-vit-large-patch14",
                                    progress=lambda d, t: self.events.put(("progress", d, t)), cancelled=self.cancel_flag.is_set)
            if results is None:
                self.events.put(("cancelled",))
                return
            self.events.put(("previewing",))
            sheets = core.preview_sheets(results, dest, os.path.basename(os.path.normpath(folder)))
            self.events.put(("analysed", folder, results, sheets))

        self.run_in_thread(work)

    def cancel(self):
        self.cancel_flag.set()
        self.status.set("Cancelling…")

    def on_loading(self, n):
        self.status.set(f"Found {n} images. Loading the AI model… (the first time this downloads about 1.7 GB, so it can take a while)")
        self.bar.config(mode="indeterminate")
        self.bar.start(12)

    def on_progress(self, done, total):
        if str(self.bar["mode"]) != "determinate":
            self.bar.stop()
            self.bar.config(mode="determinate")
        self.bar["maximum"], self.bar["value"] = total, done
        self.status.set(f"Analyzing… {done} of {total}")

    def on_previewing(self):
        self.status.set("Making preview sheets…")

    def on_empty(self):
        self.set_busy(False)
        self.status.set("No images (png, jpg, webp) found in that folder.")

    def on_cancelled(self):
        self.bar.stop()
        self.set_busy(False)
        self.status.set("Cancelled. Nothing was moved.")

    def on_error(self, text):
        self.bar.stop()
        self.set_busy(False)
        self.status.set("Something went wrong.")
        messagebox.showerror("Image Sorter", text, parent=self)

    def on_analysed(self, folder, results, sheets):
        self.bar.stop()
        self.bar.config(mode="determinate")
        self.results, self.analysed_folder, self.sheets = results, folder, sheets
        counts = {}
        for _, cat, _ in results:
            counts[cat] = counts.get(cat, 0) + 1
        for cat, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            self.table.insert("", "end", text=cat, values=(n,))
        self.set_busy(False)
        self.move_btn.config(text=f"Move {len(results)} images")
        self.status.set("Done analyzing. Press “Show previews” to check the result, then “Move” if it looks right. Nothing has been moved yet.")
        core.open_folder(sheets)

    # ---- preview / move ----
    def show_previews(self):
        core.open_folder(self.sheets)

    def move(self):
        dest = self.dest.get().strip()
        n = len(self.results)
        if not messagebox.askyesno("Move images", f"Move {n} images into category folders inside\n{dest}?\n\nYou can undo this afterwards.", parent=self):
            return
        results, folder = self.results, self.analysed_folder
        self.set_busy(True)
        self.status.set("Moving…")

        def work():
            log = core.move_all(results, folder, dest)
            self.events.put(("moved", n, log))

        self.run_in_thread(work)

    def on_moved(self, n, log):
        self.clear_results()
        self.set_busy(False)
        self.status.set(f"Done. Moved {n} images. Every move is listed in {log}")

    # ---- undo ----
    def undo(self):
        log = os.path.join(self.dest.get().strip(), "sort_log.csv")
        if not os.path.exists(log):
            messagebox.showinfo("Image Sorter", f"There is nothing to undo. No sort log was found in\n{self.dest.get()}", parent=self)
            return
        if not messagebox.askyesno("Undo last sort", "Move the images from your most recent sort back to where they were?", parent=self):
            return
        self.set_busy(True)
        self.status.set("Undoing…")

        def work():
            self.events.put(("undone", undo_sort.undo(log, last_run=True, say=lambda _: None)))

        self.run_in_thread(work)

    def on_undone(self, n):
        self.clear_results()
        self.set_busy(False)
        self.status.set(f"Put {n} images back where they came from.")


if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on high-DPI Windows screens
    except Exception:
        pass
    App().mainloop()
