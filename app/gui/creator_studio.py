"""Creator Studio AI GUI (MVC: View + Controller).

This module provides a CustomTkinter-based GUI that acts as the View/Controller
and delegates all download work to the `DownloadManager` service.
The GUI never implements downloading logic itself; it runs downloads on a
background thread and updates the UI in a thread-safe manner.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, List, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

from app.services.download_manager import DownloadManager
from app.downloaders.pexels_downloader import DownloadSummary


logger = logging.getLogger(__name__)


class GUIHandler(logging.Handler):
    """Logging handler that forwards formatted records to a callback.

    The callback is expected to be thread-safe (or schedule UI updates via
    ``after``). The handler keeps responsibilities small: format and forward.
    """

    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.callback(msg)
        except Exception:
            self.handleError(record)


class CreatorStudioApp(ctk.CTk):
    """Main application window for Creator Studio AI.

    The class contains only UI code and delegates download requests to
    `DownloadManager` which performs the actual work.
    """

    def __init__(self, download_manager: Optional[DownloadManager] = None) -> None:
        super().__init__()
        self.title("Creator Studio AI")
        self.geometry("900x700")

        # Services
        self.download_manager = download_manager or DownloadManager()

        # UI state
        self._stop_event = threading.Event()

        self._build_ui()

        # Attach a GUI log handler
        handler = GUIHandler(self._append_log)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logging.getLogger().addHandler(handler)

    def _build_ui(self) -> None:
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        title = ctk.CTkLabel(self, text="Creator Studio AI", font=("Arial", 26, "bold"))
        title.pack(pady=12)

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=16, pady=8)

        left = ctk.CTkFrame(frame)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        right = ctk.CTkFrame(frame, width=300)
        right.pack(side="right", fill="y")

        # Keywords input
        keywords_label = ctk.CTkLabel(left, text="Keywords (one per line):")
        keywords_label.pack(anchor="w")
        self.textbox = ctk.CTkTextbox(left, width=560, height=220)
        self.textbox.pack(pady=8)

        # Images per keyword and source selection
        options_row = ctk.CTkFrame(left)
        options_row.pack(fill="x", pady=(6, 0))

        count_label = ctk.CTkLabel(options_row, text="Images per keyword:")
        count_label.grid(row=0, column=0, sticky="w", padx=6)
        self.count_entry = ctk.CTkEntry(options_row, width=80)
        self.count_entry.insert(0, "5")
        self.count_entry.grid(row=0, column=1, padx=6)

        source_label = ctk.CTkLabel(options_row, text="Image source:")
        source_label.grid(row=0, column=2, sticky="w", padx=6)
        self.source_var = ctk.StringVar(value="pexels")
        self.source_dropdown = ctk.CTkOptionMenu(options_row, values=["pexels"], variable=self.source_var)
        self.source_dropdown.grid(row=0, column=3, padx=6)

        # Destination folder chooser
        folder_frame = ctk.CTkFrame(left)
        folder_frame.pack(fill="x", pady=(12, 0))

        self.folder_label = ctk.CTkLabel(folder_frame, text="No folder selected")
        self.folder_label.pack(side="left", padx=6)

        browse_button = ctk.CTkButton(folder_frame, text="Choose Save Folder", command=self._browse_folder)
        browse_button.pack(side="right", padx=6)

        # Download button and progress
        action_row = ctk.CTkFrame(left)
        action_row.pack(fill="x", pady=12)

        self.download_button = ctk.CTkButton(action_row, text="Download", command=self._on_download)
        self.download_button.pack(side="left", padx=6)

        self.progress = ctk.CTkProgressBar(action_row, width=400)
        self.progress.set(0)
        self.progress.pack(side="left", padx=12)

        self.status_label = ctk.CTkLabel(left, text="Status: Waiting...")
        self.status_label.pack(anchor="w")

        # Right side: log output
        log_label = ctk.CTkLabel(right, text="Activity Log:")
        log_label.pack(anchor="w", pady=(6, 0), padx=6)

        self.log_box = ctk.CTkTextbox(right, width=280, height=420)
        self.log_box.pack(padx=6, pady=6)
        self.log_box.configure(state="disabled")

    def _browse_folder(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            self.save_folder = Path(folder)
            self.folder_label.configure(text=str(self.save_folder))
            logger.debug("Selected folder: %s", folder)

    def _append_log(self, message: str) -> None:
        # Ensure UI updates occur on the main thread
        def _write():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", message + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        try:
            self.after(0, _write)
        except Exception:
            # In rare cases when after fails, write directly (best-effort)
            _write()

    def _set_status(self, text: str) -> None:
        def _update():
            self.status_label.configure(text=f"Status: {text}")

        self.after(0, _update)

    def _set_progress_fraction(self, fraction: float) -> None:
        def _update():
            self.progress.set(max(0.0, min(1.0, fraction)))

        self.after(0, _update)

    def _on_download(self) -> None:
        """Validate inputs and start background downloading."""
        # Basic validation
        keywords_text = self.textbox.get("1.0", "end").strip()
        if not keywords_text:
            messagebox.showerror("Validation Error", "Please enter at least one keyword.")
            return

        keywords = [k.strip() for k in keywords_text.splitlines() if k.strip()]

        try:
            count = int(self.count_entry.get())
            if count <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Validation Error", "Please enter a valid positive integer for images per keyword.")
            return

        save_folder = getattr(self, "save_folder", None)
        if not save_folder:
            messagebox.showerror("Validation Error", "Please choose a destination folder.")
            return

        source = self.source_var.get()
        # Disable UI controls
        self.download_button.configure(state="disabled")
        self._set_status("Starting downloads...")
        self._append_log(f"Starting downloads: source={source} count={count} keywords={len(keywords)}")

        # Start background thread
        thread = threading.Thread(target=self._download_worker, args=(source, keywords, count, save_folder), daemon=True)
        thread.start()

    def _download_worker(self, source: str, keywords: List[str], count: int, save_folder: Path) -> None:
        """Background worker that coordinates downloads via the DownloadManager.

        The worker calls `DownloadManager.download` for each keyword and updates
        UI state via thread-safe callbacks.
        """
        # Create a manager bound to the chosen download root so that each downloader
        # writes into the selected folder.
        manager = DownloadManager(downloads_root=save_folder)

        total = len(keywords)
        completed = 0

        for idx, keyword in enumerate(keywords, start=1):
            try:
                self._set_status(f"Downloading ({idx}/{total}): {keyword}")
                logger.info("Downloading keyword '%s' (%d/%d)", keyword, idx, total)

                summary: DownloadSummary = manager.download(source=source, keyword=keyword, count=count)

                logger.info("Completed '%s': %d images, %d failures", keyword, summary.images_downloaded, summary.failures)
                self._append_log(f"{keyword} -> downloaded={summary.images_downloaded} failures={summary.failures}")

            except EnvironmentError as e:
                logger.error("Missing API key or configuration: %s", e)
                self._append_log("Error: missing API key. Please configure PEXELS_API_KEY in .env.")
                self.after(0, lambda: messagebox.showerror("Configuration Error", str(e)))
                break
            except Exception as e:
                logger.exception("Failed downloading keyword '%s': %s", keyword, e)
                self._append_log(f"Error downloading '{keyword}': {e}")

            finally:
                completed += 1
                self._set_progress_fraction(completed / total)

        self._set_status("Finished")
        self._append_log("All downloads finished.")
        # Re-enable controls
        def _enable():
            self.download_button.configure(state="normal")

        self.after(0, _enable)

    def run(self) -> None:
        self.mainloop()


def run_app() -> None:
    app = CreatorStudioApp()
    app.run()
