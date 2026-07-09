"""Settings dialog for Creator Studio AI.

A CTkToplevel dialog that exposes user-configurable settings.  All
persistence and validation logic is delegated to
:class:`~app.services.SettingsManager` so that this module stays a
pure View component.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import customtkinter as ctk
from tkinter import filedialog

from app.services import SettingsManager

logger = logging.getLogger(__name__)


class SettingsDialog(ctk.CTkToplevel):
    """Modal-style settings dialog.

    The dialog loads the current settings on creation, lets the user
    modify them through widgets, and persists changes only when
    **Save** is clicked.  **Reset** restores factory defaults and
    **Cancel** closes the dialog without saving.
    """

    _APPEARANCE_OPTIONS = ["System", "Light", "Dark"]

    def __init__(
        self,
        parent: ctk.CTk,
        settings_manager: SettingsManager,
        *,
        on_save: Optional[Callable[[], None]] = None,
    ) -> None:
        """Initialise the settings dialog.

        Args:
            parent: The parent window that owns this dialog.
            settings_manager: Shared settings manager instance.
            on_save: Optional callback invoked after a successful save
                so the parent can react to setting changes.
        """
        super().__init__(parent)
        self.title("Settings")
        self.geometry("480x340")
        self.resizable(False, False)

        self._settings_manager = settings_manager
        self._on_save = on_save

        # Tkinter variables bound to widgets
        self._appearance_var = ctk.StringVar()
        self._folder_var = ctk.StringVar()
        self._images_per_keyword_var = ctk.StringVar()

        self._build_ui()
        self._load_settings()

        # Keep the dialog on top and grab focus
        self.transient(parent)
        self.grab_set()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Assemble all dialog widgets."""
        self._build_appearance_row()
        self._build_folder_row()
        self._build_images_row()
        self._build_button_row()

    def _build_appearance_row(self) -> None:
        """Create the appearance-mode dropdown."""
        row = ctk.CTkFrame(self)
        row.pack(fill="x", padx=20, pady=(20, 6))

        label = ctk.CTkLabel(row, text="Appearance:")
        label.pack(side="left", padx=(0, 10))

        self._appearance_menu = ctk.CTkOptionMenu(
            row,
            values=self._APPEARANCE_OPTIONS,
            variable=self._appearance_var,
        )
        self._appearance_menu.pack(side="left")

    def _build_folder_row(self) -> None:
        """Create the download-folder entry and browse button."""
        row = ctk.CTkFrame(self)
        row.pack(fill="x", padx=20, pady=6)

        label = ctk.CTkLabel(row, text="Default Download Folder:")
        label.pack(side="left", padx=(0, 10))

        self._folder_entry = ctk.CTkEntry(
            row, textvariable=self._folder_var, width=220,
        )
        self._folder_entry.pack(side="left", padx=(0, 6))

        browse_btn = ctk.CTkButton(
            row, text="Browse...", width=80, command=self._browse_folder,
        )
        browse_btn.pack(side="left")

    def _build_images_row(self) -> None:
        """Create the images-per-keyword integer entry."""
        row = ctk.CTkFrame(self)
        row.pack(fill="x", padx=20, pady=6)

        label = ctk.CTkLabel(row, text="Images Per Keyword:")
        label.pack(side="left", padx=(0, 10))

        self._images_entry = ctk.CTkEntry(
            row, textvariable=self._images_per_keyword_var, width=80,
        )
        self._images_entry.pack(side="left")

    def _build_button_row(self) -> None:
        """Create Save, Reset, and Cancel action buttons."""
        row = ctk.CTkFrame(self)
        row.pack(fill="x", padx=20, pady=(20, 20))

        cancel_btn = ctk.CTkButton(
            row, text="Cancel", fg_color="gray", command=self._on_cancel,
        )
        cancel_btn.pack(side="right", padx=(6, 0))

        reset_btn = ctk.CTkButton(
            row, text="Reset", fg_color="gray", command=self._on_reset,
        )
        reset_btn.pack(side="right", padx=(6, 0))

        save_btn = ctk.CTkButton(
            row, text="Save", command=self._on_save_click,
        )
        save_btn.pack(side="right")

    # ------------------------------------------------------------------
    # Settings <-> widgets
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        """Populate widgets from the current persisted settings."""
        settings = self._settings_manager.get_all()

        theme = settings.get("theme", "system").capitalize()
        if theme not in self._APPEARANCE_OPTIONS:
            theme = "System"
        self._appearance_var.set(theme)

        self._folder_var.set(settings.get("default_download_folder", ""))
        self._images_per_keyword_var.set(
            str(settings.get("images_per_keyword", 5))
        )

    def _apply_to_manager(self) -> None:
        """Write widget values back to the settings manager and save."""
        self._settings_manager.set(
            "theme", self._appearance_var.get().lower(),
        )
        self._settings_manager.set(
            "default_download_folder", self._folder_var.get(),
        )

        try:
            count = int(self._images_per_keyword_var.get())
        except ValueError:
            count = 5
        self._settings_manager.set("images_per_keyword", count)

        logger.info("Settings saved.")

    # ------------------------------------------------------------------
    # Widget callbacks
    # ------------------------------------------------------------------

    def _browse_folder(self) -> None:
        """Open a folder-selection dialog and update the entry."""
        folder = filedialog.askdirectory(parent=self)
        if folder:
            self._folder_var.set(folder)

    def _on_save_click(self) -> None:
        """Persist current widget values and close the dialog."""
        self._apply_to_manager()
        if self._on_save is not None:
            self._on_save()
        self.destroy()

    def _on_reset(self) -> None:
        """Restore factory defaults and refresh widgets."""
        self._settings_manager.reset()
        self._load_settings()
        logger.info("Settings reset to defaults.")

    def _on_cancel(self) -> None:
        """Close the dialog without saving."""
        self.destroy()
