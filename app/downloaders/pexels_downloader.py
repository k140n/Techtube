import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

import requests
from dotenv import find_dotenv, load_dotenv


logger = logging.getLogger(__name__)
PEXELS_API_URL = "https://api.pexels.com/v1/search"
DEFAULT_DOWNLOAD_COUNT = 5
MAX_DOWNLOAD_COUNT = 80


@dataclass
class DownloadSummary:
    """Summary of a Pexels image download operation."""

    keyword: str
    images_downloaded: int
    failures: int
    saved_paths: List[Path]


class PexelsDownloader:
    """Downloader for images from the Pexels API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        downloads_root: Union[str, Path] = "downloads",
        timeout: int = 15,
    ) -> None:
        self.api_key = api_key or self._load_api_key()
        self.downloads_root = Path(downloads_root)
        self.downloads_root.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Authorization": self.api_key})

    def download_images(self, keyword: str, count: int = DEFAULT_DOWNLOAD_COUNT) -> DownloadSummary:
        """Search Pexels for a keyword and download a fixed number of images."""
        keyword = keyword.strip()

        if not keyword:
            raise ValueError("Keyword must be a non-empty string.")

        image_count = self._normalize_count(count)
        image_urls = self._search_image_urls(keyword, image_count)

        saved_paths: List[Path] = []
        failures = max(0, image_count - len(image_urls))

        if not image_urls:
            logger.warning("No images found for keyword '%s'.", keyword)
            return DownloadSummary(
                keyword=keyword,
                images_downloaded=0,
                failures=failures,
                saved_paths=saved_paths,
            )

        keyword_folder = self._ensure_keyword_folder(keyword)

        for index, url in enumerate(image_urls[:image_count], start=1):
            destination = keyword_folder / self._build_filename(url, index)
            if self._download_image(url, destination):
                saved_paths.append(destination)
            else:
                failures += 1

        summary = DownloadSummary(
            keyword=keyword,
            images_downloaded=len(saved_paths),
            failures=failures,
            saved_paths=saved_paths,
        )
        logger.info(
            "Downloaded %d images for '%s' with %d failures.",
            summary.images_downloaded,
            keyword,
            summary.failures,
        )
        return summary

    def _search_image_urls(self, keyword: str, per_page: int) -> List[str]:
        """Search Pexels and return a list of image URLs."""
        params = {"query": keyword, "per_page": per_page, "page": 1}

        try:
            response = self.session.get(PEXELS_API_URL, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            photos = payload.get("photos", [])
            return [
                photo["src"]["large2x"]
                for photo in photos
                if isinstance(photo, dict)
                and isinstance(photo.get("src"), dict)
                and photo["src"].get("large2x")
            ]
        except (requests.RequestException, ValueError) as error:
            logger.error("Pexels search failed for keyword '%s': %s", keyword, error)
            return []

    def _download_image(self, url: str, destination: Path) -> bool:
        """Download a single image and save it to disk."""
        try:
            response = self.session.get(url, stream=True, timeout=self.timeout)
            response.raise_for_status()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as output_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        output_file.write(chunk)
            logger.debug("Saved image to %s", destination)
            return True
        except requests.RequestException as error:
            logger.warning("Skipping failed download %s: %s", url, error)
            return False

    def _ensure_keyword_folder(self, keyword: str) -> Path:
        """Ensure the keyword-specific download folder exists."""
        folder = self.downloads_root / self._sanitize_keyword(keyword)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()

    @staticmethod
    def _build_filename(url: str, index: int) -> str:
        """Create a safe filename for a downloaded image."""
        extension = Path(url).suffix or ".jpg"
        return f"image_{index:02d}{extension}"

    @staticmethod
    def _normalize_count(count: int) -> int:
        """Normalize the requested download count to a safe integer range."""
        try:
            normalized = int(count)
        except (TypeError, ValueError):
            normalized = DEFAULT_DOWNLOAD_COUNT
        return max(1, min(normalized, MAX_DOWNLOAD_COUNT))

    @staticmethod
    def _sanitize_keyword(keyword: str) -> str:
        """Convert a keyword to a safe folder name."""
        sanitized = "".join(
            char if char.isalnum() or char in {" ", "-", "_"} else "_"
            for char in keyword
        )
        sanitized = sanitized.strip() or "keyword"
        return sanitized

    @staticmethod
    def _load_api_key() -> str:
        """Load the Pexels API key from the environment."""
        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            load_dotenv(dotenv_path, override=False)

        api_key_value = os.getenv("PEXELS_API_KEY", "").strip()
        if not api_key_value:
            raise EnvironmentError(
                "PEXELS_API_KEY is missing in the environment. Add it to .env."
            )
        return api_key_value
