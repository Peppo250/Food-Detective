"""
ui.py — Tkinter UI for Food Detective.
Includes: Scanner tab, Debug tab, and Daily Limit panel.
"""
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, scrolledtext
import threading
import io
import os
import json
import requests
import time
from PIL import Image, ImageTk
import queue

API_BASE = "http://127.0.0.1:8765"

# ── Colours ──────────────────────────────────────────────────────────────────
BG           = "#F7F9F3"
GREEN_DARK   = "#27500A"
GREEN_MID    = "#639922"
GREEN_LIGHT  = "#EAF3DE"
GREEN_BORDER = "#C0DD97"
AMBER_DARK   = "#633806"
AMBER_MID    = "#BA7517"
AMBER_LIGHT  = "#FAEEDA"
AMBER_BORDER = "#FAC775"
RED_DARK     = "#791F1F"
RED_MID      = "#E24B4A"
RED_LIGHT    = "#FCEBEB"
RED_BORDER   = "#F7C1C1"
GRAY_DARK    = "#444441"
GRAY_LIGHT   = "#F1EFE8"
GRAY_MID     = "#888780"
PURPLE_DARK  = "#3C3489"
PURPLE_LIGHT = "#EEEDFE"
BLUE_DARK    = "#1A3A6B"
BLUE_LIGHT   = "#E8F0FE"
BLUE_MID     = "#4A7FD4"
TOXIC_BG     = "#3D0000"
TOXIC_FG     = "#FF8A80"
WHITE        = "#FFFFFF"

STATUS_COLORS = {
    "safe":    (GREEN_LIGHT,  GREEN_DARK,  "✅ Safe"),
    "caution": (AMBER_LIGHT,  AMBER_DARK,  "⚠️ Caution"),
    "avoid":   (RED_LIGHT,    RED_DARK,    "🚫 Avoid"),
    "toxic":   (TOXIC_BG,     TOXIC_FG,    "☠️ Not Food!"),
    "unknown": (GRAY_LIGHT,   GRAY_DARK,   "❓ Unknown"),
}

SCORE_CONFIGS = {
    "great":    (GREEN_LIGHT,  GREEN_DARK,  "🥦 Super Healthy!",     GREEN_BORDER),
    "ok":       (AMBER_LIGHT,  AMBER_DARK,  "🤔 Eat with Care",      AMBER_BORDER),
    "bad":      (RED_LIGHT,    RED_DARK,    "⚠️ Not So Healthy",     RED_BORDER),
    "not_food": (RED_LIGHT,    RED_DARK,    "🚨 This is NOT Food!",  RED_BORDER),
}


class FoodDetectiveApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🔬 Food Detective")
        self.root.geometry("1020x740")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        self._image_bytes: bytes | None = None
        self._scan_thread: threading.Thread | None = None
        self._result_queue: queue.Queue = queue.Queue()
        self._scanning = False
        self._scan_start: float = 0.0

        self._build_ui()
        self._poll_results()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=GREEN_LIGHT, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🔬 Food Detective!",
                 bg=GREEN_LIGHT, fg=GREEN_DARK,
                 font=("Helvetica Neue", 24, "bold")).pack()
        tk.Label(hdr, text="Take a photo of any food label — I'll check every ingredient and tell you how much is safe to eat!",
                 bg=GREEN_LIGHT, fg=GREEN_MID,
                 font=("Helvetica Neue", 10)).pack()

        self._nb = ttk.Notebook(self.root)
        self._nb.pack(fill="both", expand=True, padx=10, pady=8)

        scan_tab  = tk.Frame(self._nb, bg=BG)
        debug_tab = tk.Frame(self._nb, bg=BG)
        self._nb.add(scan_tab,  text="  Scanner  ")
        self._nb.add(debug_tab, text="  Debug / Raw Output  ")

        self._build_scan_tab(scan_tab)
        self._build_debug_tab(debug_tab)

    # ── Scanner tab ───────────────────────────────────────────────────────────

    def _build_scan_tab(self, parent):
        # Three-column layout: upload | results | daily limit
        left = tk.Frame(parent, bg=BG, width=240)
        left.pack(side="left", fill="y", padx=(8, 8), pady=8)
        left.pack_propagate(False)

        middle = tk.Frame(parent, bg=BG)
        middle.pack(side="left", fill="both", expand=True, pady=8)

        right = tk.Frame(parent, bg=BG, width=270)
        right.pack(side="left", fill="y", padx=(8, 8), pady=8)
        right.pack_propagate(False)

        self._build_upload_panel(left)
        self._build_results_panel(middle)
        self._build_daily_panel(right)

    def _build_upload_panel(self, parent):
        tk.Label(parent, text="Step 1: Choose a photo",
                 bg=BG, fg=GRAY_DARK,
                 font=("Helvetica Neue", 11, "bold")).pack(anchor="w")

        self._drop_frame = tk.Frame(parent, bg=PURPLE_LIGHT,
                                    highlightthickness=2,
                                    highlightbackground="#AFA9EC",
                                    width=224, height=170)
        self._drop_frame.pack(fill="x", pady=(6, 0))
        self._drop_frame.pack_propagate(False)

        self._drop_label = tk.Label(self._drop_frame,
                                    text="📷\n\nTap to pick\na photo",
                                    bg=PURPLE_LIGHT, fg=PURPLE_DARK,
                                    font=("Helvetica Neue", 12, "bold"),
                                    justify="center", cursor="hand2")
        self._drop_label.pack(expand=True, fill="both")
        self._drop_label.bind("<Button-1>", lambda e: self._pick_file())

        self._img_label = tk.Label(self._drop_frame, bg=PURPLE_LIGHT, cursor="hand2")
        self._img_label.bind("<Button-1>", lambda e: self._pick_file())

        bf = tk.Frame(parent, bg=BG)
        bf.pack(fill="x", pady=(8, 0))

        tk.Button(bf, text="📁  Pick from Files",
                  command=self._pick_file,
                  bg=PURPLE_LIGHT, fg=PURPLE_DARK,
                  font=("Helvetica Neue", 10, "bold"),
                  relief="flat", padx=8, pady=5,
                  cursor="hand2").pack(fill="x", pady=(0, 5))

        try:
            import cv2
            tk.Button(bf, text="📷  Take a Photo",
                      command=self._capture_camera,
                      bg=PURPLE_LIGHT, fg=PURPLE_DARK,
                      font=("Helvetica Neue", 10, "bold"),
                      relief="flat", padx=8, pady=5,
                      cursor="hand2").pack(fill="x", pady=(0, 5))
        except ImportError:
            pass

        self._scan_btn = tk.Button(
            parent, text="🔍  Scan Ingredients!",
            command=self._start_scan,
            bg=GREEN_MID, fg=WHITE,
            font=("Helvetica Neue", 13, "bold"),
            relief="flat", padx=10, pady=10,
            cursor="hand2", state="disabled")
        self._scan_btn.pack(fill="x", pady=(10, 0))

        self._status_label = tk.Label(
            parent, text="", bg=BG, fg=GRAY_DARK,
            font=("Helvetica Neue", 9),
            wraplength=224, justify="center")
        self._status_label.pack(pady=(6, 0))

    def _build_results_panel(self, parent):
        tk.Label(parent, text="Step 2: Results",
                 bg=BG, fg=GRAY_DARK,
                 font=("Helvetica Neue", 11, "bold")).pack(anchor="w")

        # Score banner
        self._score_frame = tk.Frame(parent, bg=GRAY_LIGHT, pady=8, padx=10)
        self._score_frame.pack(fill="x", pady=(4, 6))
        self._score_label = tk.Label(
            self._score_frame, text="Scan a food label to see results!",
            bg=GRAY_LIGHT, fg=GRAY_DARK,
            font=("Helvetica Neue", 13, "bold"))
        self._score_label.pack()

        # Counters
        cf = tk.Frame(parent, bg=BG)
        cf.pack(fill="x", pady=(0, 6))
        self._safe_count    = self._make_counter(cf, "0", "Safe",     GREEN_LIGHT, GREEN_DARK)
        self._caution_count = self._make_counter(cf, "0", "Caution",  AMBER_LIGHT, AMBER_DARK)
        self._avoid_count   = self._make_counter(cf, "0", "Avoid",    RED_LIGHT,   RED_DARK)
        self._toxic_count   = self._make_counter(cf, "0", "Not Food", TOXIC_BG,    TOXIC_FG)

        # Scrollable ingredient list
        canvas_frame = tk.Frame(parent, bg=BG)
        canvas_frame.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(canvas_frame, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(canvas_frame, orient="vertical", command=self._canvas.yview)
        self._results_frame = tk.Frame(self._canvas, bg=BG)
        self._results_frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.create_window((0, 0), window=self._results_frame, anchor="nw")
        self._canvas.configure(yscrollcommand=sb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind_all("<Button-4>",   self._on_mousewheel)
        self._canvas.bind_all("<Button-5>",   self._on_mousewheel)

    def _make_counter(self, parent, num, label, bg, fg):
        f = tk.Frame(parent, bg=bg, padx=10, pady=6)
        f.pack(side="left", expand=True, fill="x", padx=2)
        n = tk.Label(f, text=num, bg=bg, fg=fg,
                     font=("Helvetica Neue", 18, "bold"))
        n.pack()
        tk.Label(f, text=label, bg=bg, fg=fg,
                 font=("Helvetica Neue", 8, "bold")).pack()
        return n

    def _build_daily_panel(self, parent):
        """Right panel — daily serving limit display."""
        tk.Label(parent, text="📊 Daily Limit Guide",
                 bg=BG, fg=BLUE_DARK,
                 font=("Helvetica Neue", 11, "bold")).pack(anchor="w")
        tk.Label(parent,
                 text="For a child aged 4–8 (20 kg reference weight)",
                 bg=BG, fg=GRAY_MID,
                 font=("Helvetica Neue", 8),
                 wraplength=256).pack(anchor="w", pady=(0, 6))

        # Big serving number display
        self._serving_frame = tk.Frame(parent, bg=BLUE_LIGHT,
                                       highlightthickness=1,
                                       highlightbackground="#B0C4E8",
                                       pady=14, padx=10)
        self._serving_frame.pack(fill="x", pady=(0, 8))

        self._serving_icon = tk.Label(self._serving_frame, text="🍽️",
                                      bg=BLUE_LIGHT,
                                      font=("Helvetica Neue", 28))
        self._serving_icon.pack()

        self._serving_number = tk.Label(self._serving_frame,
                                        text="—",
                                        bg=BLUE_LIGHT, fg=BLUE_DARK,
                                        font=("Helvetica Neue", 36, "bold"))
        self._serving_number.pack()

        self._serving_label = tk.Label(self._serving_frame,
                                       text="servings per day",
                                       bg=BLUE_LIGHT, fg=BLUE_MID,
                                       font=("Helvetica Neue", 10, "bold"))
        self._serving_label.pack()

        self._serving_summary = tk.Label(self._serving_frame,
                                         text="Scan a label to see\nhow many servings\nare safe today.",
                                         bg=BLUE_LIGHT, fg=BLUE_DARK,
                                         font=("Helvetica Neue", 9),
                                         wraplength=240, justify="center")
        self._serving_summary.pack(pady=(6, 0))

        # Detail breakdown
        tk.Label(parent, text="Breakdown by ingredient:",
                 bg=BG, fg=GRAY_DARK,
                 font=("Helvetica Neue", 9, "bold")).pack(anchor="w", pady=(4, 2))

        detail_canvas_frame = tk.Frame(parent, bg=BG)
        detail_canvas_frame.pack(fill="both", expand=True)

        self._detail_canvas = tk.Canvas(detail_canvas_frame, bg=BG,
                                        highlightthickness=0)
        detail_sb = ttk.Scrollbar(detail_canvas_frame, orient="vertical",
                                  command=self._detail_canvas.yview)
        self._detail_frame = tk.Frame(self._detail_canvas, bg=BG)
        self._detail_frame.bind(
            "<Configure>",
            lambda e: self._detail_canvas.configure(
                scrollregion=self._detail_canvas.bbox("all")))
        self._detail_canvas.create_window((0, 0), window=self._detail_frame, anchor="nw")
        self._detail_canvas.configure(yscrollcommand=detail_sb.set)
        self._detail_canvas.pack(side="left", fill="both", expand=True)
        detail_sb.pack(side="right", fill="y")

        # Source note
        tk.Label(parent,
                 text="Sources: WHO, AHA, EFSA ADI guidelines",
                 bg=BG, fg=GRAY_MID,
                 font=("Helvetica Neue", 7),
                 wraplength=256).pack(anchor="w", pady=(4, 0))

    # ── Debug tab ─────────────────────────────────────────────────────────────

    def _build_debug_tab(self, parent):
        tk.Label(parent,
                 text="Raw OCR text and parsed ingredient list — copy and paste this when reporting issues.",
                 bg=BG, fg=GRAY_DARK,
                 font=("Helvetica Neue", 10),
                 wraplength=860, justify="left").pack(anchor="w", padx=10, pady=(8, 4))

        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill="x", padx=10, pady=(0, 4))
        tk.Button(btn_row, text="📋  Copy All",
                  command=self._copy_debug,
                  bg=PURPLE_LIGHT, fg=PURPLE_DARK,
                  font=("Helvetica Neue", 10, "bold"),
                  relief="flat", padx=8, pady=4,
                  cursor="hand2").pack(side="left")
        tk.Button(btn_row, text="🗑  Clear",
                  command=self._clear_debug,
                  bg=GRAY_LIGHT, fg=GRAY_DARK,
                  font=("Helvetica Neue", 10, "bold"),
                  relief="flat", padx=8, pady=4,
                  cursor="hand2").pack(side="left", padx=(6, 0))

        self._debug_box = scrolledtext.ScrolledText(
            parent,
            font=("Courier New", 10),
            bg="#1E1E1E", fg="#D4D4D4",
            insertbackground="white",
            relief="flat", wrap="word",
            padx=10, pady=10)
        self._debug_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _debug_log(self, text: str):
        self._result_queue.put(("_debug", {"text": text}))

    def _copy_debug(self):
        content = self._debug_box.get("1.0", "end")
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        messagebox.showinfo("Copied", "Debug output copied to clipboard!")

    def _clear_debug(self):
        self._debug_box.config(state="normal")
        self._debug_box.delete("1.0", "end")

    # ── Image handling ────────────────────────────────────────────────────────

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Choose an ingredient label photo",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp"),
                       ("All", "*.*")])
        if path:
            with open(path, "rb") as f:
                self._image_bytes = f.read()
            self._show_preview(self._image_bytes)

    def _capture_camera(self):
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                messagebox.showwarning("Camera", "Could not open camera.")
                return
            win = tk.Toplevel(self.root)
            win.title("Take a photo — press SPACE")
            win.geometry("640x520")
            lbl = tk.Label(win)
            lbl.pack()
            tk.Label(win, text="SPACE = capture  |  ESC = cancel",
                     font=("Helvetica Neue", 11)).pack()
            captured = [None]

            def update_frame():
                ret, frame = cap.read()
                if ret:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(rgb)
                    img.thumbnail((620, 460))
                    photo = ImageTk.PhotoImage(img)
                    lbl.config(image=photo)
                    lbl.image = photo
                    captured[0] = frame
                if win.winfo_exists():
                    win.after(30, update_frame)

            def on_key(event):
                if event.keysym == "space" and captured[0] is not None:
                    rgb = cv2.cvtColor(captured[0], cv2.COLOR_BGR2RGB)
                    buf = io.BytesIO()
                    Image.fromarray(rgb).save(buf, format="JPEG", quality=95)
                    self._image_bytes = buf.getvalue()
                    self._show_preview(self._image_bytes)
                    cap.release()
                    win.destroy()
                elif event.keysym == "Escape":
                    cap.release()
                    win.destroy()

            win.bind("<Key>", on_key)
            update_frame()
            win.focus_set()
        except Exception as e:
            messagebox.showerror("Camera Error", str(e))

    def _show_preview(self, image_bytes: bytes):
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((220, 165))
        photo = ImageTk.PhotoImage(img)
        self._drop_label.pack_forget()
        self._img_label.config(image=photo)
        self._img_label.image = photo
        self._img_label.pack(expand=True, fill="both")
        self._scan_btn.config(state="normal")
        self._status_label.config(text="Image loaded. Press Scan!")

    # ── Scanning ──────────────────────────────────────────────────────────────

    def _start_scan(self):
        if not self._image_bytes or self._scanning:
            return
        self._scanning = True
        self._scan_start = time.time()
        self._scan_btn.config(state="disabled", text="Scanning...")
        self._clear_results()
        self._reset_daily_panel()
        self._debug_log(f"\n{'='*60}\nNEW SCAN — {time.strftime('%H:%M:%S')}\n{'='*60}")
        self._tick_timer()

        self._scan_thread = threading.Thread(target=self._do_scan, daemon=True)
        self._scan_thread.start()

    def _tick_timer(self):
        if not self._scanning:
            return
        elapsed = time.time() - self._scan_start
        self._status_label.config(text=f"Scanning… {elapsed:.0f}s")
        self.root.after(500, self._tick_timer)

    def _do_scan(self):
        try:
            buf = io.BytesIO(self._image_bytes)
            response = requests.post(
                f"{API_BASE}/scan",
                files={"file": ("label.jpg", buf, "image/jpeg")},
                stream=True,
                timeout=120)
            event_type = None
            for line in response.iter_lines(decode_unicode=True):
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:") and event_type:
                    data = json.loads(line[5:].strip())
                    self._result_queue.put((event_type, data))
                    event_type = None
        except Exception as e:
            self._result_queue.put(("error", {"message": str(e)}))

    # ── Result polling ────────────────────────────────────────────────────────

    def _poll_results(self):
        safe_n = caution_n = avoid_n = toxic_n = 0
        try:
            while True:
                event, data = self._result_queue.get_nowait()

                if event == "_debug":
                    self._debug_box.config(state="normal")
                    self._debug_box.insert("end", data["text"] + "\n")
                    self._debug_box.see("end")

                elif event == "status":
                    msg = data.get("message", "")
                    self._status_label.config(text=msg)
                    self._debug_log(f"[status] {msg}")

                elif event == "parsed":
                    ingredients = data.get("ingredients", [])
                    self._debug_log(f"\n--- PARSED INGREDIENTS ({len(ingredients)}) ---")
                    for i, ing in enumerate(ingredients, 1):
                        self._debug_log(f"  {i:2d}. {ing}")
                    self._debug_log("--- END PARSED ---")

                elif event == "ingredient":
                    self._add_ingredient_card(data)
                    status = data.get("status", "unknown")
                    src = "cache" if data.get("from_cache") else "api"
                    self._debug_log(f"  {status:8s}  {data.get('name','')}  [{src}]")
                    if status == "safe":      safe_n += 1
                    elif status == "caution": caution_n += 1
                    elif status == "avoid":   avoid_n += 1
                    elif status == "toxic":   toxic_n += 1

                elif event == "done":
                    self._finish_scan(data)
                    self._debug_log(f"\n[done] overall_score={data.get('overall_score','?')}")
                    elapsed = time.time() - self._scan_start
                    self._debug_log(f"[done] total time: {elapsed:.1f}s")

                elif event == "daily_advice":
                    self._show_daily_advice(data)
                    self._debug_log(f"\n--- DAILY ADVICE ---")
                    self._debug_log(f"  {data.get('summary','')}")
                    for line in data.get("detail_lines", []):
                        self._debug_log(f"  {line}")

                elif event == "error":
                    msg = data.get("message", "Unknown error")
                    self._show_error(msg)
                    self._debug_log(f"\n[ERROR] {msg}")

        except queue.Empty:
            pass

        # Update counters
        if safe_n or caution_n or avoid_n or toxic_n:
            def _int(w): return int(w.cget("text") or 0)
            self._safe_count.config(text=str(_int(self._safe_count) + safe_n))
            self._caution_count.config(text=str(_int(self._caution_count) + caution_n))
            self._avoid_count.config(text=str(_int(self._avoid_count) + avoid_n))
            self._toxic_count.config(text=str(_int(self._toxic_count) + toxic_n))

        self.root.after(80, self._poll_results)

    def _finish_scan(self, data: dict):
        self._scanning = False
        elapsed = time.time() - self._scan_start
        self._scan_btn.config(state="normal", text="🔍  Scan Again!")
        self._status_label.config(text=f"Done in {elapsed:.1f}s")

        score = data.get("overall_score", "ok")
        cfg = SCORE_CONFIGS.get(score, SCORE_CONFIGS["ok"])
        bg, fg, text, border = cfg
        for w in self._score_frame.winfo_children():
            w.destroy()
        self._score_frame.config(bg=bg, highlightthickness=2,
                                 highlightbackground=border)
        tk.Label(self._score_frame, text=text, bg=bg, fg=fg,
                 font=("Helvetica Neue", 15, "bold")).pack()

    def _show_error(self, message: str):
        self._scanning = False
        self._scan_btn.config(state="normal", text="🔍  Try Again!")
        self._status_label.config(text=f"Error: {message}", fg=RED_DARK)

    def _clear_results(self):
        for w in self._results_frame.winfo_children():
            w.destroy()
        self._safe_count.config(text="0")
        self._caution_count.config(text="0")
        self._avoid_count.config(text="0")
        self._toxic_count.config(text="0")
        for w in self._score_frame.winfo_children():
            w.destroy()
        self._score_frame.config(bg=GRAY_LIGHT, highlightthickness=0)
        tk.Label(self._score_frame, text="Reading ingredients…",
                 bg=GRAY_LIGHT, fg=GRAY_DARK,
                 font=("Helvetica Neue", 12, "bold")).pack()

    def _reset_daily_panel(self):
        self._serving_number.config(text="—", fg=BLUE_DARK)
        self._serving_icon.config(text="🍽️")
        self._serving_summary.config(text="Calculating…")
        for w in self._detail_frame.winfo_children():
            w.destroy()

    # ── Daily advice display ──────────────────────────────────────────────────

    def _show_daily_advice(self, data: dict):
        """Render the daily serving limit panel from SSE daily_advice event."""
        summary   = data.get("summary", "")
        details   = data.get("detail_lines", [])
        max_s     = data.get("max_servings", "—")
        limiting  = data.get("limiting", "")
        serving_g = data.get("serving_size_g")

        # Determine colour and icon based on max servings
        try:
            n = float(max_s.replace("about ", "").replace("less than ½", "0.4")
                      .replace("½", "0.5").replace("less than", "0").strip())
        except Exception:
            n = 99

        if n == 0 or max_s in ("none", "no limit found"):
            icon, fg, bg = "🚫", RED_DARK, RED_LIGHT
        elif n < 1:
            icon, fg, bg = "⚠️", RED_DARK, RED_LIGHT
        elif n < 2:
            icon, fg, bg = "1️⃣", AMBER_DARK, AMBER_LIGHT
        elif n <= 3:
            icon, fg, bg = "✅", GREEN_DARK, GREEN_LIGHT
        else:
            icon, fg, bg = "🎉", GREEN_DARK, GREEN_LIGHT

        # Update big display
        self._serving_frame.config(bg=bg)
        self._serving_icon.config(text=icon, bg=bg)
        self._serving_label.config(bg=bg, fg=fg)

        display_num = max_s if max_s else "?"
        self._serving_number.config(text=display_num, fg=fg, bg=bg)

        # Summary text — wrap to fit
        short_summary = summary
        if len(short_summary) > 140:
            # Truncate to first sentence
            idx = short_summary.find(".")
            if idx > 0:
                short_summary = short_summary[:idx + 1]
        self._serving_summary.config(text=short_summary, bg=bg, fg=fg)

        # Show serving size if found
        if serving_g:
            tk.Label(self._serving_frame,
                     text=f"(per {serving_g:.0f}g serving)",
                     bg=bg, fg=fg,
                     font=("Helvetica Neue", 8)).pack()

        # Detail breakdown
        for w in self._detail_frame.winfo_children():
            w.destroy()

        if not details:
            tk.Label(self._detail_frame,
                     text="No nutrition panel found.\nServing size not detected on label.",
                     bg=BG, fg=GRAY_MID,
                     font=("Helvetica Neue", 9),
                     wraplength=248, justify="left").pack(anchor="w", pady=4)
            return

        for line in details:
            # Pick colour from first emoji
            if line.startswith("🚫") or line.startswith("☠️"):
                card_bg, card_fg = RED_LIGHT, RED_DARK
            elif line.startswith("⚠️"):
                card_bg, card_fg = AMBER_LIGHT, AMBER_DARK
            elif line.startswith("✅"):
                card_bg, card_fg = GREEN_LIGHT, GREEN_DARK
            else:
                card_bg, card_fg = GRAY_LIGHT, GRAY_DARK

            card = tk.Frame(self._detail_frame, bg=card_bg, pady=5, padx=8)
            card.pack(fill="x", pady=2)
            tk.Label(card, text=line, bg=card_bg, fg=card_fg,
                     font=("Helvetica Neue", 8),
                     wraplength=248, justify="left",
                     anchor="w").pack(fill="x")

        self._detail_canvas.update_idletasks()
        self._detail_canvas.configure(
            scrollregion=self._detail_canvas.bbox("all"))

    # ── Ingredient cards ──────────────────────────────────────────────────────

    def _add_ingredient_card(self, data: dict):
        status  = data.get("status", "unknown")
        name    = data.get("name", "Unknown").title()
        explain = data.get("explanation", "")
        e_num   = data.get("e_number", "")
        cached  = data.get("from_cache", False)

        bg, fg, badge = STATUS_COLORS.get(status, STATUS_COLORS["unknown"])

        card = tk.Frame(self._results_frame, bg=bg, padx=8, pady=6)
        card.pack(fill="x", padx=3, pady=2)

        top = tk.Frame(card, bg=bg)
        top.pack(fill="x")

        tk.Label(top, text=badge, bg=bg, fg=fg,
                 font=("Helvetica Neue", 8, "bold")).pack(side="left")

        display = f"  {name}"
        if e_num:
            display += f"  ({e_num.upper()})"
        tk.Label(top, text=display, bg=bg, fg=fg,
                 font=("Helvetica Neue", 10, "bold")).pack(side="left")

        if cached:
            tk.Label(top, text=" ⚡", bg=bg, fg=fg,
                     font=("Helvetica Neue", 8)).pack(side="right")

        if explain:
            tk.Label(card, text=explain, bg=bg, fg=fg,
                     font=("Helvetica Neue", 8),
                     wraplength=420, justify="left",
                     anchor="w").pack(fill="x", pady=(2, 0))

        self._canvas.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._canvas.yview_moveto(1.0)

    def _on_mousewheel(self, event):
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
