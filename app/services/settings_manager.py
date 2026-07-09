"""Thread-safe settings management for Creator Studio AI.

This module centralizes application settings persistence in a JSON file so
other modules can reuse a consistent configuration interface without mixing
business logic into the GUI.
"""

from __future__ import annotations

import json
import logging
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SettingsManager:
    """Manage application settings with validation, persistence, and recovery.

    The manager stores settings in a JSON file at the project root by default.
    It is thread-safe and gracefully handles corrupted or missing files.
    """

    DEFAULT_SETTINGS: Dict[str, Any] = {
        "theme": "system",
        "default_download_folder": "",
        "default_image_source": "pexels",
        "images_per_keyword": 5,
        "pexels_api_key": "",
        "pixabay_api_key": "",
        "remember_last_folder": True,
        "logging_enabled": True,
    }

    VALID_THEMES = {"system", "dark", "light"}
    VALID_SOURCES = {"pexels", "pixabay", "google", "bing"}

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        """Create a settings manager bound to a JSON settings file.

        Args:
            config_path: Optional custom path for the settings file. When omitted,
                the manager uses the project root and the default file name.
        """
        self._lock = threading.Lock()
        self._config_path = self._resolve_config_path(config_path)
        self._settings: Dict[str, Any] = {}
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self) -> Dict[str, Any]:
        """Load settings from disk and return a validated settings dictionary."""
        with self._lock:
            if not self._config_path.exists():
                logger.info("Settings file missing, creating a new one at %s", self._config_path)
                self._reset_to_defaults_locked()
                return self.get_all_locked()

            try:
                with self._config_path.open("r", encoding="utf-8") as handle:
                    raw_settings = json.load(handle)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Settings file is invalid or unreadable: %s", exc)
                self._recover_corrupt_file()
                self._reset_to_defaults_locked()
                return self.get_all_locked()

            if not isinstance(raw_settings, dict):
                logger.warning("Settings content is not a JSON object; resetting to defaults")
                self._recover_corrupt_file()
                self._reset_to_defaults_locked()
                return self.get_all_locked()

            self._settings = self.validate(raw_settings)
            self._write_settings_locked(self._settings)
            return self.get_all_locked()

    def save(self) -> None:
        """Persist the current validated settings to disk."""
        with self._lock:
            self._settings = self.validate(self._settings)
            self._write_settings_locked(self._settings)

    def reset(self) -> None:
        """Reset settings to the default values and save them."""
        with self._lock:
            self._reset_to_defaults_locked()

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for a setting key, or a provided default."""
        with self._lock:
            return self.get_locked(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a setting value and persist it immediately."""
        with self._lock:
            self._settings[key] = self._coerce_value(key, value)
            self._write_settings_locked(self._settings)

    def get_all(self) -> Dict[str, Any]:
        """Return a copy of all current settings."""
        with self._lock:
            return self.get_all_locked()

    def validate(self, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Validate and normalize a settings dictionary.

        Invalid values are restored to their defaults. Missing values are filled
        in with defaults so the configuration remains stable.
        """
        source = settings if settings is not None else self._settings
        if not isinstance(source, dict):
            source = {}

        validated: Dict[str, Any] = {}
        for key, default_value in self.DEFAULT_SETTINGS.items():
            raw_value = source.get(key, default_value)
            validated[key] = self._coerce_value(key, raw_value)

        for key, value in source.items():
            if key not in self.DEFAULT_SETTINGS:
                validated[key] = value

        return validated

    def _resolve_config_path(self, config_path: Optional[Path | str]) -> Path:
        """Resolve the settings file path to a project-root-based default."""
        if config_path is None:
            return Path(__file__).resolve().parents[2] / "creator_studio_settings.json"
        return Path(config_path)

    def _write_settings_locked(self, settings: Dict[str, Any]) -> None:
        """Write settings to disk using a consistent JSON format."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._config_path.with_suffix(self._config_path.suffix + ".tmp")

        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(settings, handle, indent=2)
                handle.write("\n")
            temp_path.replace(self._config_path)
        except OSError as exc:
            logger.error("Failed to write settings file %s: %s", self._config_path, exc)
            raise
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def _recover_corrupt_file(self) -> None:
        """Rename a corrupt settings file to a backup and log the action."""
        backup_path = self._config_path.with_name(f"{self._config_path.stem}.backup.json")
        try:
            if backup_path.exists():
                backup_path.unlink()
            self._config_path.rename(backup_path)
        except OSError as exc:
            logger.warning("Unable to rename corrupted settings file to backup: %s", exc)
            return

        logger.warning("Corrupted settings file moved to %s", backup_path)

    def _reset_to_defaults_locked(self) -> None:
        """Replace the current settings with defaults and persist them."""
        self._settings = deepcopy(self.DEFAULT_SETTINGS)
        self._write_settings_locked(self._settings)

    def _coerce_value(self, key: str, value: Any) -> Any:
        """Coerce an input value to the expected type or restore the default."""
        if key not in self.DEFAULT_SETTINGS:
            return deepcopy(value) if value is not None else None

        default_value = self.DEFAULT_SETTINGS[key]

        if key == "theme":
            if isinstance(value, str) and value.lower() in self.VALID_THEMES:
                return value.lower()
            return default_value

        if key == "default_download_folder":
            return value if isinstance(value, str) else default_value

        if key == "default_image_source":
            if isinstance(value, str) and value.lower() in self.VALID_SOURCES:
                return value.lower()
            return default_value

        if key == "images_per_keyword":
            if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 80:
                return value
            return default_value

        if key in {"pexels_api_key", "pixabay_api_key"}:
            return value if isinstance(value, str) else default_value

        if key in {"remember_last_folder", "logging_enabled"}:
            return value if isinstance(value, bool) else default_value

        return deepcopy(default_value) if value is None else value

    def get_locked(self, key: str, default: Any = None) -> Any:
        """Return a setting while already holding the lock."""
        if key in self._settings:
            return self._settings[key]
        if default is not None:
            return default
        return self.DEFAULT_SETTINGS.get(key)

    def get_all_locked(self) -> Dict[str, Any]:
        """Return a copy of the settings while already holding the lock."""
        return deepcopy(self._settings)
