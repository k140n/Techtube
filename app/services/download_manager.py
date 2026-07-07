"""Download manager service.

Provides a central coordinator for image downloaders. The manager
delegates downloading to specific downloader implementations and
is intentionally free of any download logic itself.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol, Union

from app.downloaders.pexels_downloader import PexelsDownloader, DownloadSummary

logger = logging.getLogger(__name__)


class DownloaderProtocol(Protocol):
    """Protocol that downloader implementations must satisfy."""

    def download_images(self, keyword: str, count: int) -> DownloadSummary:  # pragma: no cover - protocol
        """Download images for a keyword and return a DownloadSummary.

        Implementations must perform network/file I/O.
        """
        ...


FactoryType = Union[Callable[[], DownloaderProtocol], DownloaderProtocol]


class DownloadManager:
    """Central coordinator for image downloaders.

    Responsibilities:
    - Select a downloader implementation by name.
    - Delegate the download request to the selected downloader.

    The manager itself must not implement downloading logic.
    """

    def __init__(
        self,
        downloads_root: Union[str, Path] = "downloads",
        registry: Optional[Dict[str, FactoryType]] = None,
    ) -> None:
        """Create a DownloadManager.

        Args:
            downloads_root: Base folder for downloads (passed to downloader factories).
            registry: Optional mapping of source name to downloader factory or instance.
                If omitted, a default registry providing `pexels` is installed.
        """
        self.downloads_root = Path(downloads_root)
        self.downloads_root.mkdir(parents=True, exist_ok=True)

        self._registry: Dict[str, FactoryType] = {}

        # Default registry entries (extendable)
        default_registry: Dict[str, FactoryType] = {
            "pexels": lambda: PexelsDownloader(downloads_root=self.downloads_root),
            "pixabay": self._not_implemented_factory("pixabay"),
            "google": self._not_implemented_factory("google"),
            "bing": self._not_implemented_factory("bing"),
        }

        # Merge user registry with defaults (user overrides defaults)
        if registry:
            merged = {**default_registry, **{k.lower(): v for k, v in registry.items()}}
        else:
            merged = default_registry

        # Normalize keys to lowercase
        self._registry = {k.lower(): v for k, v in merged.items()}

        logger.debug("DownloadManager initialized with sources: %s", list(self._registry.keys()))

    def register(self, name: str, factory: FactoryType) -> None:
        """Register or replace a downloader factory/instance under `name`."""
        self._registry[name.lower()] = factory
        logger.debug("Registered downloader '%s'", name.lower())

    def download(self, source: str, keyword: str, count: int) -> DownloadSummary:
        """Download images using the selected source.

        Args:
            source: Source name (e.g. 'pexels').
            keyword: Search keyword.
            count: Number of images to download.

        Returns:
            DownloadSummary returned by the selected downloader.

        Raises:
            ValueError: If the `source` is not supported.
            Exception: Propagates downloader-specific exceptions.
        """
        if not source:
            raise ValueError("`source` must be a non-empty string")

        key = source.lower()
        factory = self._registry.get(key)
        if factory is None:
            logger.error("Requested unsupported source: %s", source)
            raise ValueError(f"Unsupported source: {source}. Supported: {list(self._registry.keys())}")

        downloader = self._instantiate_downloader(factory)

        logger.info("Delegating download to '%s': keyword=%s count=%s", key, keyword, count)

        # Delegate actual work to the downloader
        summary = downloader.download_images(keyword=keyword, count=count)

        logger.info("Download completed for source=%s keyword=%s: %s images, %s failures",
                    key, keyword, summary.images_downloaded, summary.failures)
        return summary

    def _instantiate_downloader(self, factory: FactoryType) -> DownloaderProtocol:
        """Return a DownloaderProtocol instance from a factory or instance."""
        # If a callable was provided, call it to obtain an instance.
        if callable(factory):
            instance = factory()
        else:
            # Assume factory is already an instance
            instance = factory  # type: ignore[assignment]

        # Structural validation: ensure the instance exposes the required method.
        download_attr = getattr(instance, "download_images", None)
        if not callable(download_attr):
            raise TypeError("Downloader does not implement required 'download_images' method")

        return instance  # type: ignore[return-value]

    @staticmethod
    def _not_implemented_factory(name: str) -> Callable[[], DownloaderProtocol]:
        """Return a factory that raises NotImplementedError when invoked.

        This makes missing implementations explicit and easy to replace in tests.
        """
        def _factory() -> DownloaderProtocol:  # pragma: no cover - runtime placeholder
            raise NotImplementedError(f"Downloader for '{name}' is not implemented yet")

        return _factory
