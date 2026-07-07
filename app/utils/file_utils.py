"""Utility helpers for TechTubeAI."""

from pathlib import Path


def ensure_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path
