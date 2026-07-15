"""Shared HTTP session with polite defaults."""

from __future__ import annotations

import time
from typing import Optional

import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class HttpClient:
    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        timeout: float = 60.0,
        min_interval: float = 1.0,
    ):
        self.timeout = timeout
        self.min_interval = min_interval
        self._last_request_at = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def get_text(self, url: str, referer: Optional[str] = None) -> str:
        self._throttle()
        headers = {}
        if referer:
            headers["Referer"] = referer
        resp = self.session.get(url, headers=headers, timeout=self.timeout)
        self._last_request_at = time.monotonic()
        resp.raise_for_status()
        resp.encoding = resp.encoding or "utf-8"
        return resp.text

    def download_file(
        self,
        url: str,
        dest_path,
        referer: Optional[str] = None,
        chunk_size: int = 1024 * 256,
    ) -> int:
        """Stream download to path. Returns bytes written."""
        self._throttle()
        headers = {"Accept": "*/*"}
        if referer:
            headers["Referer"] = referer
        with self.session.get(
            url, headers=headers, timeout=self.timeout, stream=True
        ) as resp:
            self._last_request_at = time.monotonic()
            resp.raise_for_status()
            written = 0
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)
        return written
