import logging
import os
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import requests
from dotenv import load_dotenv

from app.utils.file_utils import ensure_directory

load_dotenv()

StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[float], None]

PEXELS_API_URL = "https://api.pexels.com/v1/search"
DEFAULT_IMAGES_PER_KEYWORD = 5
MAX_IMAGES_PER_REQUEST = 80

logger = logging.getLogger(__name__)


def download_images(
    keywords: Iterable[str],
    save_folder: str,
    images_per_keyword: int,
    status_callback: Optional[StatusCallback] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> List[Path]:
    """Download images for keywords and save them by keyword folder."""
    if not keywords:
        _report_status("No keywords provided.", status_callback)
        return []

    if not save_folder:
        _report_status("Select a save folder first.", status_callback)
        return []

    if images_per_keyword <= 0:
        images_per_keyword = DEFAULT_IMAGES_PER_KEYWORD

    try:
        api_key = _get_api_key()
    except EnvironmentError as error:
        _report_status(str(error), status_callback)
        logger.exception(error)
        return []

    downloader = ImageDownloader(
        api_key=api_key,
        save_folder=Path(save_folder),
        images_per_keyword=images_per_keyword,
        status_callback=status_callback,
        progress_callback=progress_callback,
    )
    return downloader.download(keywords)


class ImageDownloader:
    def __init__(
        self,
        api_key: str,
        save_folder: Path,
        images_per_keyword: int,
        status_callback: Optional[StatusCallback] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self.api_key = api_key
        self.save_folder = ensure_directory(save_folder)
        self.images_per_keyword = min(max(images_per_keyword, 1), MAX_IMAGES_PER_REQUEST)
        self.status_callback = status_callback
        self.progress_callback = progress_callback
        self.images_downloaded = 0
        self.total_images = 0

    def download(self, keywords: Iterable[str]) -> List[Path]:
        downloaded_files: List[Path] = []
        keyword_list = [keyword.strip() for keyword in keywords if keyword.strip()]

        if not keyword_list:
            _report_status("No valid keywords provided.", self.status_callback)
            return []

        self.total_images = len(keyword_list) * self.images_per_keyword
        progress_increment = 1.0 / max(self.total_images, 1)

        for keyword in keyword_list:
            self._report_status(f"Searching images for '{keyword}'...")
            keyword_folder = ensure_directory(self.save_folder / self._safe_name(keyword))

            urls = self._fetch_image_urls(keyword)
            if not urls:
                self._report_status(f"No images found for '{keyword}'.")
                continue

            for url in urls[: self.images_per_keyword]:
                destination = keyword_folder / self._get_filename(url)
                try:
                    downloaded = self._download_image(url, destination)
                    downloaded_files.append(downloaded)
                except Exception as error:
                    logger.exception("Failed to download image %s", url)
                    self._report_status(f"Failed to download one image for '{keyword}'.")
                finally:
                    self.images_downloaded += 1
                    self._update_progress(progress_increment)

        if self.progress_callback:
            self.progress_callback(1.0)

        if downloaded_files:
            self._report_status("Images downloaded successfully.")
        else:
            self._report_status("No images were downloaded.")

        return downloaded_files

    def _fetch_image_urls(self, keyword: str) -> List[str]:
        headers = {"Authorization": self.api_key}
        params = {"query": keyword, "per_page": self.images_per_keyword}
        try:
            response = requests.get(PEXELS_API_URL, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            payload = response.json()
            photos = payload.get("photos", [])
            return [photo["src"]["large2x"] for photo in photos if "src" in photo]
        except requests.RequestException as error:
            logger.exception("Image search failed for '%s'", keyword)
            self._report_status(
                f"Search failed for '{keyword}'. Check your API key and network."
            )
            return []

    def _download_image(self, url: str, destination: Path) -> Path:
        try:
            response = requests.get(url, stream=True, timeout=20)
            response.raise_for_status()
            with destination.open("wb") as image_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        image_file.write(chunk)
            return destination
        except requests.RequestException as error:
            raise RuntimeError(f"Failed to download image from {url}") from error

    @staticmethod
    def _safe_name(name: str) -> str:
        safe = "".join(
            char if char.isalnum() or char in (" ", "-", "_") else "_" for char in name
        ).strip()
        return safe or "keyword"

    @staticmethod
    def _get_filename(url: str) -> str:
        filename = Path(url).name
        return filename or "image.jpg"

    def _report_status(self, message: str) -> None:
        if self.status_callback:
            try:
                self.status_callback(text=message)
            except TypeError:
                self.status_callback(message)

    def _update_progress(self, increment: float) -> None:
        if self.progress_callback:
            current_value = min(self.images_downloaded * increment, 1.0)
            self.progress_callback(current_value)


def _get_api_key() -> str:
    api_key = os.getenv("PEXELS_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            "Missing PEXELS_API_KEY in .env. Add your Pexels API key to use image downloads."
        )
    return api_key


def _report_status(message: str, status_callback: Optional[StatusCallback] = None) -> None:
    if status_callback:
        try:
            status_callback(text=message)
        except TypeError:
            status_callback(message)
