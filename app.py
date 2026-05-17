import asyncio
import logging
import os
import re
import threading
import time
import tkinter as tk
from queue import Empty, Queue
from difflib import SequenceMatcher
from typing import Optional

from dotenv import load_dotenv, set_key
import cv2
import numpy as np
import pyperclip
from PIL import Image, ImageGrab

from config import (
    API_URL,
    CAPTURE_INTERVAL_SECONDS,
    CYRILLIC_TO_LATIN,
    MIN_TEXT_LENGTH,
    MODEL_NAME,
    OVERLAY_GEOMETRY,
    QUEUE_POLL_INTERVAL_MS,
    SIMILARITY_THRESHOLD,
    STATUS_RESET_DELAY_MS,
    TRANSLATION_COOLDOWN_SECONDS,
    WINDOW_GEOMETRY,
)
from models import ManualTranslationTask
from ocr import WinRTOCR
from translator import ReasoningOnlyModelError, TranslatorClient


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(threadName)s: %(message)s")
# Suppress noisy logs from third-party libraries like httpx (used by genai) and urllib3
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)

LOGGER = logging.getLogger("wow_translator")


class WoWTranslatorApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.geometry(WINDOW_GEOMETRY)
        self.root.overrideredirect(True)  # type: ignore[attr-defined]
        self.root.attributes("-topmost", True, "-alpha", 0.95)
        self.root.config(bg="#000")

        self.stop_event = threading.Event()
        self.region_lock = threading.Lock()
        self.translation_lock = threading.Lock()

        self.overlay = None
        self.is_region_locked = False
        self.translation_enabled = True
        self.subtitle_region = None
        self.last_raw_text = ""
        self.last_similarity_key = ""
        self.last_displayed_text = ""
        self.last_translation_at = 0.0
        self.last_thresh = None

        self.input_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.api_key_var.trace_add("write", self.on_api_key_change)
        self.manual_request_seq = 0
        self.latest_manual_request_id = 0
        self._is_manual_translating: bool = False

        self.ui_queue: Queue[tuple[str, str]] = Queue()
        self.translation_queue: Queue[str | None] = Queue(maxsize=1)
        # None is used as a stop sentinel instead of a magic string
        self.manual_translation_queue: Queue[ManualTranslationTask | None] = Queue()

        self.win_ocr = WinRTOCR(LOGGER)
        self.translator = TranslatorClient(API_URL, MODEL_NAME)
        # Created once and reused across frames to avoid per-frame allocation overhead
        self._clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))

        self.status_reset_job = None
        self.capture_thread = None
        self.translation_thread = None
        self.manual_translation_thread = None
        self.model_failure_logged = False

        self.x = self.y = 0
        self.sw = self.sh = 0
        self.mx = self.my = 0
        self.ox = self.oy = 0
        self.ow = self.oh = 0
        self.omx = self.omy = 0

        self.setup_ui()
        self.load_settings()
        self.start_workers()
        self.check_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self) -> None:
        self.main_frame = tk.Frame(self.root, bg="#121212", highlightbackground="#00FF41", highlightthickness=1)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.top_panel = tk.Frame(self.main_frame, bg="#1e1e1e", height=30)
        self.top_panel.pack(fill=tk.X, side=tk.TOP)
        self.top_panel.pack_propagate(False)

        self.btn_reg = tk.Button(
            self.top_panel,
            text="SET REGION",
            command=self.toggle_overlay,
            bg="#443300",
            fg="white",
            bd=0,
            padx=10,
            font=("Arial", 8, "bold"),
        )
        self.btn_reg.pack(side=tk.LEFT, padx=5)

        self.btn_lock = tk.Button(
            self.top_panel,
            text="LOCK",
            command=self.toggle_lock_region,
            bg="#333",
            fg="white",
            bd=0,
            padx=10,
            font=("Arial", 8, "bold"),
            state=tk.DISABLED,
        )
        self.btn_lock.pack(side=tk.LEFT)

        self.btn_clr = tk.Button(
            self.top_panel,
            text="CLR",
            command=self.clear_all,
            bg="#333",
            fg="white",
            bd=0,
            padx=10,
            font=("Arial", 8),
        )
        self.btn_clr.pack(side=tk.LEFT)

        self.btn_toggle_tl = tk.Button(
            self.top_panel,
            text="TL: ON",
            command=self.toggle_translation,
            bg="#006400",
            fg="white",
            bd=0,
            padx=10,
            font=("Arial", 8, "bold"),
        )
        self.btn_toggle_tl.pack(side=tk.LEFT, padx=5)

        # Gemini API Key input (Wider, no stars for clarity if user can't see what they type)
        self.api_key_entry = tk.Entry(
            self.top_panel,
            textvariable=self.api_key_var,
            width=20,
            bg="#000",
            fg="#00FF41",
            insertbackground="white",
            bd=0,
            font=("Arial", 8),
        )
        self.api_key_entry.pack(side=tk.LEFT, padx=5)
        # Tooltip-like label
        tk.Label(self.top_panel, text="KEY", bg="#1e1e1e", fg="#444", font=("Arial", 7)).pack(side=tk.LEFT)

        # Force focus when clicked (fixes common overrideredirect issues)
        self.api_key_entry.bind("<Button-1>", lambda e: self.force_focus(self.api_key_entry))
        self.api_key_entry.bind("<Button-3>", lambda e: self.show_context_menu(e, self.api_key_entry))
        # Bind standard shortcuts manually because overrideredirect breaks them
        self.api_key_entry.bind("<Control-v>", lambda e: self.manual_paste(self.api_key_entry))
        self.api_key_entry.bind("<Control-c>", lambda e: self.manual_copy(self.api_key_entry))
        self.api_key_entry.bind("<Control-a>", lambda e: self.manual_select_all(self.api_key_entry))

        self.btn_close = tk.Button(
            self.top_panel,
            text="X",
            command=self.on_closing,
            bg="#c00",
            fg="white",
            bd=0,
            padx=12,
            font=("Arial", 10, "bold"),
        )
        self.btn_close.pack(side=tk.RIGHT)

        self.status_var = tk.StringVar(value="Status: idle")
        self.status_label = tk.Label(
            self.top_panel,
            textvariable=self.status_var,
            bg="#1e1e1e",
            fg="#a0a0a0",
            font=("Consolas", 8),
        )
        self.status_label.pack(side=tk.RIGHT, padx=10)

        self.text_area = tk.Text(
            self.main_frame,
            bg="#000",
            fg="#00FF41",
            font=("Consolas", 12),
            wrap=tk.WORD,
            bd=0,
            padx=15,
            pady=15,
        )
        self.text_area.config(state=tk.DISABLED)

        # Pack input_frame FIRST with side=BOTTOM so it always reserves space.
        # text_area is packed after and fills whatever remains.
        self.input_frame = tk.Frame(self.main_frame, bg="#121212")
        self.input_frame.pack(fill=tk.X, pady=4, padx=8, side=tk.BOTTOM)

        self.text_area.pack(expand=True, fill=tk.BOTH)

        tk.Label(
            self.input_frame,
            text="Я написал (русский):",
            bg="#121212",
            fg="#00FF41",
            font=("Arial", 9),
        ).pack(anchor="w")
        self.input_entry = tk.Entry(
            self.input_frame,
            textvariable=self.input_var,
            font=("Arial", 11),
            bg="#000814",
            fg="#ffd200",
            insertbackground="white",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#00FF41",
        )
        self.input_entry.pack(fill=tk.X, pady=(0, 4))
        self.input_entry.bind("<Return>", lambda e: self.translate_input())
        self.input_entry.bind("<Button-1>", lambda e: self.force_focus(self.input_entry))
        self.input_entry.bind("<Button-3>", lambda e: self.show_context_menu(e, self.input_entry))
        self.input_entry.bind("<Control-v>", lambda e: self.manual_paste(self.input_entry))
        self.input_entry.bind("<Control-c>", lambda e: self.manual_copy(self.input_entry))
        self.input_entry.bind("<Control-a>", lambda e: self.manual_select_all(self.input_entry))

        tk.Label(
            self.input_frame,
            text="Перевод на английский:",
            bg="#121212",
            fg="#00FF41",
            font=("Arial", 9),
        ).pack(anchor="w")
        self.translated_text = tk.Text(
            self.input_frame,
            height=2,
            bg="#1e1e1e",
            fg="#00FF41",
            font=("Consolas", 10),
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.translated_text.pack(fill=tk.X)

        self.main_res = tk.Label(self.main_frame, text="◢", bg="#121212", fg="#444", cursor="size_nw_se")
        self.main_res.place(relx=1.0, rely=1.0, x=-12, y=-12)
        self.main_res.bind("<ButtonPress-1>", self.start_resize)
        self.main_res.bind("<B1-Motion>", self.do_resize)
        self.top_panel.bind("<ButtonPress-1>", self.start_move)
        self.top_panel.bind("<B1-Motion>", self.do_move)

    def translate_input(self):
        russian_text = self.input_var.get().strip()
        if not russian_text:
            return

        self.manual_request_seq += 1
        request_id = self.manual_request_seq
        self.latest_manual_request_id = request_id
        self.input_entry.config(state=tk.DISABLED)
        self.manual_translation_queue.put(ManualTranslationTask(request_id=request_id, text=russian_text))
        self.set_status("Status: manual translation...")

    def start_workers(self) -> None:
        self.capture_thread = threading.Thread(target=self.capture_loop, daemon=True, name="capture-worker")
        self.capture_thread.start()

        self.translation_thread = threading.Thread(target=self.translation_loop, daemon=True, name="translation-worker")
        self.translation_thread.start()

        self.manual_translation_thread = threading.Thread(
            target=self.manual_translation_loop,
            daemon=True,
            name="manual-translation-worker",
        )
        self.manual_translation_thread.start()

    def start_move(self, event) -> None:
        self.x = event.x
        self.y = event.y

    def do_move(self, event) -> None:
        delta_x = event.x - self.x
        delta_y = event.y - self.y
        self.root.geometry(f"+{self.root.winfo_x() + delta_x}+{self.root.winfo_y() + delta_y}")

    def start_resize(self, event) -> None:
        self.sw = self.root.winfo_width()
        self.sh = self.root.winfo_height()
        self.mx = event.x_root
        self.my = event.y_root

    def do_resize(self, event) -> None:
        new_width = max(400, self.sw + (event.x_root - self.mx))
        new_height = max(220, self.sh + (event.y_root - self.my))  # 220 keeps bottom panel visible
        self.root.geometry(f"{new_width}x{new_height}")

    def toggle_translation(self) -> None:
        self.translation_enabled = not self.translation_enabled
        if self.translation_enabled:
            self.btn_toggle_tl.config(text="TL: ON", bg="#006400")
            self.set_status("Status: Auto-translation resumed")
            self.last_thresh = None
        else:
            self.btn_toggle_tl.config(text="TL: OFF", bg="#8B0000")
            self.set_status("Status: Auto-translation paused")

    def toggle_overlay(self) -> None:
        if self.overlay and self.overlay.winfo_exists():
            self.overlay.destroy()
            self.overlay = None
            self.is_region_locked = False
            self.btn_lock.config(state=tk.DISABLED, text="LOCK", bg="#333")
            self.set_region(None)
            self.set_status("Status: region cleared")
            return

        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True, "-alpha", 0.3)
        self.overlay.config(bg="black")
        self.overlay.geometry(OVERLAY_GEOMETRY)

        self.ov_frame = tk.Frame(
            self.overlay,
            highlightbackground="#FF0000",
            highlightthickness=3,
            bg="black",
        )
        self.ov_frame.pack(fill=tk.BOTH, expand=True)

        self.ov_res = tk.Label(
            self.ov_frame,
            text="<>",
            bg="#FF0000",
            fg="white",
            font=("Arial", 10, "bold"),
            cursor="size_nw_se",
            width=3,
        )
        self.ov_res.place(relx=1.0, rely=1.0, x=-25, y=-25)

        self.ov_res.bind("<ButtonPress-1>", self.ov_start_resize)
        self.ov_res.bind("<B1-Motion>", self.ov_do_resize)
        self.ov_frame.bind("<ButtonPress-1>", self.ov_start_move)
        self.ov_frame.bind("<B1-Motion>", self.ov_do_move)

        self.update_region()
        self.btn_lock.config(state=tk.NORMAL)
        self.set_status("Status: region active")

    def toggle_lock_region(self) -> None:
        if not self.overlay or not self.overlay.winfo_exists():
            return
            
        try:
            import ctypes
            hwnd = int(self.overlay.frame(), 16)
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            
            if not self.is_region_locked:
                # Add click-through style
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED)
                self.is_region_locked = True
                self.overlay.attributes("-alpha", 0.05)
                self.btn_lock.config(text="UNLOCK", bg="#8B0000")
                self.ov_res.place_forget()
                self.ov_frame.config(highlightbackground="#FF3131")
                self.last_thresh = None
                self.set_status("Status: region locked (click-through)")
            else:
                # Remove click-through style
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT)
                self.is_region_locked = False
                self.overlay.attributes("-alpha", 0.3)
                self.btn_lock.config(text="LOCK", bg="#333")
                self.ov_res.place(relx=1.0, rely=1.0, x=-25, y=-25)
                self.ov_frame.config(highlightbackground="#FF0000")
                self.set_status("Status: region unlocked")
        except Exception as e:
            LOGGER.error(f"Failed to toggle region lock: {e}")

    def ov_start_move(self, event) -> None:
        self.ox = event.x
        self.oy = event.y

    def ov_do_move(self, event) -> None:
        if not self.overlay:
            return
        delta_x = event.x - self.ox
        delta_y = event.y - self.oy
        self.overlay.geometry(f"+{self.overlay.winfo_x() + delta_x}+{self.overlay.winfo_y() + delta_y}")
        self.update_region()

    def ov_start_resize(self, event) -> None:
        if not self.overlay:
            return
        self.ow = self.overlay.winfo_width()
        self.oh = self.overlay.winfo_height()
        self.omx = event.x_root
        self.omy = event.y_root

    def ov_do_resize(self, event) -> None:
        if not self.overlay:
            return
        new_width = max(100, self.ow + (event.x_root - self.omx))
        new_height = max(40, self.oh + (event.y_root - self.omy))
        self.overlay.geometry(f"{new_width}x{new_height}")
        self.update_region()

    def set_region(self, region: Optional[tuple[int, int, int, int]]) -> None:
        with self.region_lock:
            self.subtitle_region = region

    def get_region(self) -> Optional[tuple[int, int, int, int]]:
        with self.region_lock:
            return self.subtitle_region

    def update_region(self) -> None:
        if not self.overlay:
            return
        self.overlay.update_idletasks()
        x = self.overlay.winfo_rootx()
        y = self.overlay.winfo_rooty()
        w = self.overlay.winfo_width()
        h = self.overlay.winfo_height()
        # Exclude the 3px highlight border from the capture region so it doesn't corrupt OCR
        self.set_region((x + 3, y + 3, x + w - 3, y + h - 3))

    def capture_loop(self) -> None:
        # Each worker thread owns its own event loop — avoids cross-thread loop sharing
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        LOGGER.info("WinRT OCR capture worker started.")

        try:
            while not self.stop_event.is_set():
                if not self.translation_enabled or not self.is_region_locked:
                    self.stop_event.wait(CAPTURE_INTERVAL_SECONDS)
                    continue

                region = self.get_region()
                if not region:
                    self.stop_event.wait(CAPTURE_INTERVAL_SECONDS)
                    continue

                try:
                    shot = ImageGrab.grab(bbox=region, all_screens=True)

                    img = cv2.resize(np.array(shot), None, fx=4.0, fy=4.0, interpolation=cv2.INTER_LANCZOS4)
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    # Mild filter to remove noise without blurring characters
                    gray = cv2.bilateralFilter(gray, 3, 40, 40)
                    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

                    pil_image = Image.fromarray(thresh)
                    
                    # Optimization: 10x3 grid image comparison to avoid unnecessary OCR and API calls
                    should_process = True
                    if self.last_thresh is not None and self.last_thresh.shape == thresh.shape:
                        h, w = thresh.shape
                        cell_h, cell_w = h // 10, w // 3
                        diff = cv2.absdiff(thresh, self.last_thresh)
                        
                        changed_enough = False
                        for row in range(10):
                            for col in range(3):
                                y1, y2 = row * cell_h, h if row == 9 else (row + 1) * cell_h
                                x1, x2 = col * cell_w, w if col == 2 else (col + 1) * cell_w
                                
                                cell_diff = diff[y1:y2, x1:x2]
                                changed_pixels = cv2.countNonZero(cell_diff)
                                cell_area = (y2 - y1) * (x2 - x1)
                                
                                if changed_pixels / cell_area > 0.04:  # 4% change in any cell is enough
                                    changed_enough = True
                                    break
                            if changed_enough:
                                break
                                
                        if not changed_enough:
                            should_process = False

                    if should_process:
                        self.last_thresh = thresh.copy()
                        raw_text = loop.run_until_complete(self.win_ocr.recognize_text(pil_image))
                        normalized_text = self.normalize_ocr_text(raw_text)

                        if normalized_text and self.should_enqueue_text(normalized_text):
                            self.enqueue_latest_translation(normalized_text)
                            self.ui_queue.put(("status", "Status: translating..."))

                except Exception:
                    LOGGER.exception("Capture/OCR pipeline failed.")
                    self.ui_queue.put(("status", "Status: OCR error"))

                self.stop_event.wait(CAPTURE_INTERVAL_SECONDS)
        finally:
            loop.close()

        LOGGER.info("Capture worker stopped.")

    def translation_loop(self) -> None:
        LOGGER.info("Translation worker started.")

        while not self.stop_event.is_set():
            try:
                raw_text = self.translation_queue.get(timeout=0.5)
            except Empty:
                continue

            if raw_text is None:  # stop sentinel
                self.translation_queue.task_done()
                break

            try:
                chat_lines = self.extract_chat_lines(raw_text)
                
                # Обновить translator с последним API Key из UI перед переводом
                self.translator.set_api_key(self.api_key_var.get().strip())
                
                # Переводим все сообщения за один быстрый и дешевый запрос к API
                translated_text, engine_name = self.translator.translate_lines(chat_lines)
                
                # Проверяем на sentinel и валидность
                if translated_text and translated_text.strip().upper() != "SKIP":
                    self.ui_queue.put(("translation", translated_text))
                    self.ui_queue.put(("status", f"Status: updated via {engine_name}"))
                    self.model_failure_logged = False
                else:
                    self.ui_queue.put(("status", "Status: skipped (garbage input)"))
            except ReasoningOnlyModelError:
                LOGGER.warning("Model still thinking. Translation skipped.")
                self.ui_queue.put(("status", "Status: model is thinking (no output)"))
            except Exception:
                LOGGER.exception("Translation failed")
                self.ui_queue.put(("status", "Status: translation error"))
            finally:
                self.translation_queue.task_done()

        LOGGER.info("Translation worker stopped.")

    def manual_translation_loop(self) -> None:
        LOGGER.info("Manual translation worker started.")

        while not self.stop_event.is_set():
            try:
                task = self.manual_translation_queue.get(timeout=0.5)
            except Empty:
                continue

            if task is None:  # stop sentinel
                self.manual_translation_queue.task_done()
                break

            try:
                if not isinstance(task, ManualTranslationTask):
                    LOGGER.warning("Unexpected item in manual_translation_queue: %s", type(task))
                    continue

                # Update translator with latest API Key
                self.translator.set_api_key(self.api_key_var.get().strip())
                english_text, engine_name = self.translator.translate_manual_input(task.text)
                self.ui_queue.put(("manual_translation", f"{task.request_id}\n{english_text}"))
                self.ui_queue.put(("status", f"[{engine_name}] Скопировано в буфер: {english_text[:40]}..."))
            except Exception as exc:
                LOGGER.exception("Manual translation failed")
                self.ui_queue.put(("status", f"Ошибка перевода: {exc}"))
                self.ui_queue.put(("manual_translation_done", str(task.request_id if isinstance(task, ManualTranslationTask) else 0)))
            finally:
                self.manual_translation_queue.task_done()

        LOGGER.info("Manual translation worker stopped.")

    def normalize_ocr_text(self, text: str) -> str:
        if not text:
            return ""

        # 1. Сверхнадежно удаляем все полноценные таймстампы (включая зашумленные OCR вроде '1 9:06' или '13:18:57') по всему тексту
        # Паттерн ищет цифры с двоеточиями, допуская возможные опечатки OCR (l, I, З, O вместо цифр) и лишние пробелы перед временем
        timestamp_pattern = re.compile(
            r"\b(?:[0-9lI|!ЗO]{1,2}\s+)?[0-9lI|!ЗO]{1,2}\s*[:;]\s*[0-9lI|!ЗO]{2}(?:\s*[:;]\s*[0-9lI|!ЗO]{2})?\b"
        )
        text = timestamp_pattern.sub("", text)

        # 2. Удаляем оборванные куски времени в начале или конце строк (например, оставшиеся '13:' или '11:')
        text = re.sub(r"(?m)^\s*[0-9lI|!ЗO]{1,2}\s*[:;]\s*", "", text)
        text = re.sub(r"(?m)\s*[0-9lI|!ЗO]{1,2}\s*[:;]\s*$", "", text)

        # Разделяем исходный текст по строкам и убираем пустые
        raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not raw_lines:
            return ""

        messages = []
        current_msg = []

        # Сверхнадежные регулярные выражения для поиска границ новых сообщений чата (когда таймстампы уже вырезаны)
        # 1. Префиксы каналов или отправителей в скобках (игнорирует до 12 мусорных знаков перед открывающей скобкой)
        prefix_regex = re.compile(
            r"^\s*(?:[^\[\]]{1,12})?[\[1lI|!]\s*[^\]:;]{2,15}[\]1lI|!]"
        )
        # 2. Имена персонажей с двоеточием или ключевыми словами
        name_colon_regex = re.compile(
            r"^\s*[A-Za-zА-Яа-я0-9]{2,12}\s*(?:says|whispers|said|yells|говорит|шепчет)?\s*[:;]",
            re.I
        )

        for line in raw_lines:
            is_new = False
            if prefix_regex.match(line):
                is_new = True
            elif name_colon_regex.match(line):
                is_new = True
            elif re.match(r"^\s*(?:To\s+)?\[", line, re.I):
                is_new = True

            if is_new:
                if current_msg:
                    messages.append(" ".join(current_msg))
                current_msg = [line]
            else:
                if current_msg:
                    current_msg.append(line)  # Склеиваем многострочное сообщение в одну строку через пробел
                else:
                    current_msg = [line]

        if current_msg:
            messages.append(" ".join(current_msg))

        cleaned_messages = []
        for msg in messages:
            # 1. Удаление мусора перед открывающей скобкой сообщения (если она есть)
            if "[" in msg:
                msg_clean = msg[msg.find("["):]
            else:
                msg_clean = msg

            # 2. Исправление фрагментированных скобок
            msg_clean = re.sub(r"\[\s+", "[", msg_clean)
            msg_clean = re.sub(r"\s+\]", "]", msg_clean)
            msg_clean = re.sub(r"^[1lI|!]\s*\[", "[", msg_clean)

            # 3. Применяем замены символов (кириллица -> латиница для структурных частей)
            msg_clean = self._fix_structural_cyrillic(msg_clean)
            msg_clean = msg_clean.replace("|", " ").replace("_", " ")
            msg_clean = msg_clean.replace("То ", "To ").replace("то ", "to ")
            msg_clean = msg_clean.replace("Тo ", "To ").replace("тo ", "to ")
            
            msg_clean = re.sub(r"(?i)\b([a-z])\1{2,}\b", r"\1", msg_clean)
            msg_clean = re.sub(r"(?i)whispers\s*:\s*To\s+\[", "whispers: [", msg_clean)
            msg_clean = re.sub(r"(?i)To\s+\[([^\]]+?)1\s*:", r"To [\1]:", msg_clean)
            msg_clean = re.sub(r"(?i)\[([^\]]+?)1\s*:", r"[\1]:", msg_clean)
            
            # Убираем лишние двойные пробелы
            msg_clean = re.sub(r"\s+", " ", msg_clean).strip()
            
            if msg_clean:
                cleaned_messages.append(msg_clean)

        cleaned = "\n".join(cleaned_messages)

        duplicate_match = re.match(
            r"^(?P<left>.+?)\s+(?P<right>(?:To\s+\[[^\]]+\]:|\[[^\]]+\]\s+whispers:).+)$",
            cleaned,
        )
        if duplicate_match:
            left = duplicate_match.group("left").strip()
            right = duplicate_match.group("right").strip()
            if left and right and self.similarity_key(left) == self.similarity_key(right):
                cleaned = left

        if len(cleaned) < 10 or not any(char.isalpha() for char in cleaned):
            return ""
        return cleaned

    def _fix_structural_cyrillic(self, text: str) -> str:
        """Apply CYRILLIC_TO_LATIN only to player name tags and English chat keywords.

        This prevents corrupting Russian message bodies (e.g. "сова" → "coba"),
        while still fixing OCR confusion in names and structural tokens.
        """
        # Fix player names inside [Name] brackets
        text = re.sub(
            r"\[([^\]]+)\]",
            lambda m: "[" + m.group(1).translate(CYRILLIC_TO_LATIN) + "]",
            text,
        )
        # Fix English chat keywords that OCR may read as Cyrillic lookalikes
        for keyword in ("whispers", "says", "said", "yells"):
            text = re.sub(
                rf"(?i)\b{keyword}\b",
                lambda m: m.group(0).translate(CYRILLIC_TO_LATIN),
                text,
            )
        return text

    def _format_translation_lines(self, text: str) -> str:
        """Safety net: if the LLM joined messages with '. ' instead of '\n',
        split on period followed by a capital letter (Latin or Cyrillic) or '['.
        Only runs when the output has no newlines at all.
        """
        if "\n" in text:
            return text
        return re.sub(r"\.\s+(?=[A-ZА-ЯЁ\[])", ".\n", text)

    def insert_chat_line_breaks(self, text: str) -> str:
        # Robust prefix: Time? + Channel? + To? + Name (must have letter) + Colon/Keyword
        # Name part [^\]:;\s]*[A-Za-zА-Яа-я][^\]:;]* ensures we don't match pure numbers (timestamps) as names.
        prefix = r"(?:(?:\d{1,2}:\d{1,2}(?::\d{1,2})?\s+)?(?:[\[1lI|!]?[^\]:;]{2,15}[\]1lI|!]?\s+)?(?:To\s+)?(?:[\[1lI|!]?[^\]:;]*[A-Za-zА-Яа-я][^\]:;]*[\]1lI|!]?)(?:[:;\s]+(?:whispers|says|said|yells|говорит|шепчет)[:;]|[:;]))"
        sys_prefix = r"(?:(?:\d{1,2}:\d{2}(?::\d{2})?\s+)?(?:[\[1lI|!]?[A-Z][A-Za-zА-Яа-я0-9]+[\]1lI|!]?)\s+has\s+(?:come\s+online|gone\s+offline))"
        combined_pattern = r"(?i)(" + prefix + r"|" + sys_prefix + r")"
        
        matches = list(re.finditer(combined_pattern, text))
        if not matches:
            return text
            
        lines = []
        if matches[0].start() > 0:
            first_part = text[:matches[0].start()].strip()
            if first_part:
                lines.append(first_part)
                
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i+1].start() if i + 1 < len(matches) else len(text)
            line = text[start:end].strip()
            if line:
                lines.append(line)
                
        return "\n".join(lines)

    def extract_chat_lines(self, text: str) -> list[str]:
        parts = [line.strip() for line in text.splitlines() if line.strip()]
        return parts or [text]

    def similarity_key(self, text: str) -> str:
        lowered = text.lower()
        lowered = re.sub(r"[^a-zа-я0-9]+", "", lowered)
        return lowered

    def should_enqueue_text(self, text: str) -> bool:
        with self.translation_lock:
            current_time = time.monotonic()
            similarity_key = self.similarity_key(text)

            if text == self.last_raw_text or similarity_key == self.last_similarity_key:
                return False

            if self.last_similarity_key:
                similarity = SequenceMatcher(None, similarity_key, self.last_similarity_key).ratio()
                if similarity >= SIMILARITY_THRESHOLD:
                    return False

            if current_time - self.last_translation_at < TRANSLATION_COOLDOWN_SECONDS:
                return False

            self.last_raw_text = text
            self.last_similarity_key = similarity_key
            self.last_translation_at = current_time
            return True

    def enqueue_latest_translation(self, text: str) -> None:
        try:
            while True:
                self.translation_queue.get_nowait()
                self.translation_queue.task_done()
        except Empty:
            pass

        self.translation_queue.put(text)

    def check_queue(self) -> None:
        if self.stop_event.is_set():
            return

        try:
            while True:
                event_type, payload = self.ui_queue.get_nowait()
                if event_type == "translation":
                    self.display_translation(payload)
                elif event_type == "manual_translation":
                    self.display_manual_translation(payload)
                elif event_type == "manual_translation_done":
                    self.finish_manual_translation(int(payload))
                elif event_type == "status":
                    self.set_status(payload)
        except Empty:
            pass
        except tk.TclError:
            LOGGER.info("UI loop stopped because widgets were destroyed.")
            return

        self.root.after(QUEUE_POLL_INTERVAL_MS, self.check_queue)

    def display_translation(self, text: str) -> None:
        if text == self.last_displayed_text:
            return
        self.last_displayed_text = text

        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.END, text)
        self.text_area.see(tk.END)
        self.text_area.config(state=tk.DISABLED)

    def display_manual_translation(self, text: str) -> None:
        # Debounce for bottom translation field — only show final result
        # Ignore intermediate updates during loading
        if not self._is_manual_translating:
            try:
                request_id_text, english_text = text.split("\n", 1)
                request_id = int(request_id_text)

                self.translated_text.config(state=tk.NORMAL)
                self.translated_text.delete("1.0", tk.END)
                self.translated_text.insert(tk.END, english_text)
                self.translated_text.config(state=tk.DISABLED)
                pyperclip.copy(english_text)
                if request_id == self.latest_manual_request_id:
                    self.input_var.set("")
                self.finish_manual_translation(request_id)

            except (ValueError, IndexError):
                # Skip invalid updates
                pass

        # Mark translation as active

    def finish_manual_translation(self, request_id: Optional[int] = None) -> None:
        if request_id is None or request_id == self.latest_manual_request_id:
            self.input_entry.config(state=tk.NORMAL)
            self.input_entry.focus()
        
        # Finish translation (remove flag for next update)

    def force_focus(self, widget) -> None:
        self.root.focus_force()
        widget.focus_set()

    def show_context_menu(self, event, widget) -> None:
        menu = tk.Menu(self.root, tearoff=0, bg="#1e1e1e", fg="#00FF41", activebackground="#443300")
        menu.add_command(label="Копировать", command=lambda: self.manual_copy(widget))
        menu.add_command(label="Вставить", command=lambda: self.manual_paste(widget))
        menu.add_separator()
        menu.add_command(label="Выделить всё", command=lambda: self.manual_select_all(widget))
        menu.post(event.x_root, event.y_root)

    def manual_paste(self, widget) -> str:
        try:
            text = self.root.clipboard_get()
            if isinstance(widget, tk.Entry):
                # If text is selected, delete it first
                try:
                    widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except tk.TclError:
                    pass
                widget.insert(tk.INSERT, text)
            elif isinstance(widget, tk.Text):
                widget.insert(tk.INSERT, text)
        except Exception:
            pass
        return "break"

    def manual_copy(self, widget) -> str:
        try:
            sel = ""
            if isinstance(widget, tk.Entry):
                sel = widget.selection_get()
            elif isinstance(widget, tk.Text):
                sel = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
            
            if sel:
                self.root.clipboard_clear()
                self.root.clipboard_append(sel)
        except Exception:
            pass
        return "break"

    def manual_select_all(self, widget) -> str:
        if isinstance(widget, tk.Entry):
            widget.selection_range(0, tk.END)
            widget.icursor(tk.END)
        elif isinstance(widget, tk.Text):
            widget.tag_add(tk.SEL, "1.0", tk.END)
        return "break"

    def on_api_key_change(self, *args) -> None:
        # Cancel previous timer if exists (debounce)
        if hasattr(self, '_api_key_timer') and self._api_key_timer:
            self.root.after_cancel(self._api_key_timer)
        
        # Schedule update in 500ms
        self._api_key_timer = self.root.after(500, self._apply_api_key)

    def _apply_api_key(self):
        self._api_key_timer = None
        key = self.api_key_var.get().strip()
        self.translator.set_api_key(key)
        self.save_settings()

    def load_settings(self) -> None:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)
            key = os.getenv("GEMINI_API_KEY", "")
            if key:
                self.api_key_var.set(key)
                self.translator.set_api_key(key)

    def save_settings(self) -> None:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        try:
            key = self.api_key_var.get().strip()
            set_key(env_path, "GEMINI_API_KEY", key)
        except Exception as e:
            LOGGER.error(f"Failed to save settings to .env: {e}")

    def set_status(self, message: str) -> None:
        self.status_var.set(message)
        if self.status_reset_job:
            self.root.after_cancel(self.status_reset_job)
            self.status_reset_job = None

        if message != "Status: idle":
            self.status_reset_job = self.root.after(STATUS_RESET_DELAY_MS, lambda: self.status_var.set("Status: idle"))

    def clear_all(self) -> None:
        self.last_displayed_text = ""
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete("1.0", tk.END)
        self.text_area.config(state=tk.DISABLED)
        self.set_status("Status: cleared")

    def on_closing(self) -> None:
        if self.stop_event.is_set():
            return

        LOGGER.info("Shutting down application.")
        self.stop_event.set()
        self.set_region(None)

        if self.overlay and self.overlay.winfo_exists():
            self.overlay.destroy()
            self.overlay = None

        # Cancel any pending status-reset timer to avoid TclError on destroyed widgets
        if self.status_reset_job:
            self.root.after_cancel(self.status_reset_job)
            self.status_reset_job = None

        try:
            self.translation_queue.put_nowait(None)  # stop sentinel
        except Exception:
            pass
        try:
            self.manual_translation_queue.put_nowait(None)  # stop sentinel
        except Exception:
            pass

        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1.5)
        if self.translation_thread and self.translation_thread.is_alive():
            self.translation_thread.join(timeout=1.5)
        if self.manual_translation_thread and self.manual_translation_thread.is_alive():
            self.manual_translation_thread.join(timeout=1.5)

        self.translator.close()

        self.root.after(50, self.root.destroy)