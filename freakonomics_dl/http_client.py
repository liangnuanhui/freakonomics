"""Shared HTTP session with throttling, retries, and download progress."""

from __future__ import annotations

import sys
import time
from typing import Callable, Optional

import requests
from requests import Response
from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Retry these HTTP statuses (rate limit + transient server errors)
RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}


class HttpClient:
    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        timeout: float = 90.0,
        min_interval: float = 1.0,
        max_retries: int = 5,
        backoff_base: float = 2.0,
        backoff_max: float = 60.0,
    ):
        self.timeout = timeout
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
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

    def _retry_delay(self, attempt: int, resp: Optional[Response] = None) -> float:
        # Honor Retry-After when present
        if resp is not None:
            ra = resp.headers.get("Retry-After")
            if ra:
                try:
                    return min(float(ra), self.backoff_max)
                except ValueError:
                    pass
        delay = self.backoff_base ** attempt
        return min(delay, self.backoff_max)

    def _log(self, msg: str) -> None:
        print(msg, flush=True)

    def request(
        self,
        method: str,
        url: str,
        *,
        referer: Optional[str] = None,
        stream: bool = False,
        extra_headers: Optional[dict] = None,
        label: str = "request",
    ) -> Response:
        headers = dict(extra_headers or {})
        if referer:
            headers["Referer"] = referer

        last_err: Optional[BaseException] = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                resp = self.session.request(
                    method,
                    url,
                    headers=headers,
                    timeout=self.timeout,
                    stream=stream,
                )
                self._last_request_at = time.monotonic()

                if resp.status_code in RETRY_STATUSES:
                    delay = self._retry_delay(attempt, resp)
                    if attempt >= self.max_retries:
                        resp.raise_for_status()
                    self._log(
                        f"  ↻ HTTP {resp.status_code} on {label} "
                        f"(try {attempt}/{self.max_retries}), "
                        f"retry in {delay:.1f}s…"
                    )
                    resp.close()
                    time.sleep(delay)
                    continue

                resp.raise_for_status()
                return resp

            except (ConnectionError, Timeout, ChunkedEncodingError) as e:
                last_err = e
                delay = self._retry_delay(attempt)
                if attempt >= self.max_retries:
                    break
                self._log(
                    f"  ↻ network error on {label}: {type(e).__name__}: {e} "
                    f"(try {attempt}/{self.max_retries}), "
                    f"retry in {delay:.1f}s…"
                )
                time.sleep(delay)

        raise RuntimeError(
            f"{label} failed after {self.max_retries} tries: {last_err}"
        )

    def get_text(self, url: str, referer: Optional[str] = None, label: str = "GET") -> str:
        resp = self.request("GET", url, referer=referer, stream=False, label=label)
        resp.encoding = resp.encoding or "utf-8"
        return resp.text

    def download_file(
        self,
        url: str,
        dest_path,
        referer: Optional[str] = None,
        chunk_size: int = 256 * 1024,
        label: str = "audio",
        on_progress: Optional[Callable[[int, Optional[int]], None]] = None,
    ) -> int:
        """
        Stream download with retries. Writes to dest_path.
        on_progress(bytes_written, total_or_None)
        """
        last_err: Optional[BaseException] = None
        tmp_path = str(dest_path) + ".part"

        for attempt in range(1, self.max_retries + 1):
            written = 0
            try:
                resp = self.request(
                    "GET",
                    url,
                    referer=referer,
                    stream=True,
                    extra_headers={"Accept": "*/*"},
                    label=label,
                )
                total = resp.headers.get("Content-Length")
                total_n = int(total) if total and total.isdigit() else None

                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if not chunk:
                            continue
                        f.write(chunk)
                        written += len(chunk)
                        if on_progress:
                            on_progress(written, total_n)

                resp.close()

                # basic sanity: if server sent length, match it
                if total_n is not None and written != total_n:
                    raise IOError(
                        f"incomplete download: got {written} of {total_n} bytes"
                    )

                # atomic replace
                import os

                os.replace(tmp_path, dest_path)
                return written

            except Exception as e:
                last_err = e
                # clean partial
                try:
                    import os

                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    pass

                if attempt >= self.max_retries:
                    break
                # request() already retried HTTP statuses; this covers mid-stream failures
                delay = self._retry_delay(attempt)
                self._log(
                    f"  ↻ {label} download error: {e} "
                    f"(try {attempt}/{self.max_retries}), "
                    f"retry in {delay:.1f}s…"
                )
                time.sleep(delay)

        raise RuntimeError(
            f"{label} download failed after {self.max_retries} tries: {last_err}"
        )


def format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def progress_bar(written: int, total: Optional[int], width: int = 28) -> str:
    if total and total > 0:
        ratio = min(written / total, 1.0)
        filled = int(width * ratio)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {ratio * 100:5.1f}% {format_bytes(written)}/{format_bytes(total)}"
    return f"{format_bytes(written)} downloaded"


def print_download_progress(written: int, total: Optional[int]) -> None:
    line = "  ⬇ " + progress_bar(written, total)
    sys.stdout.write("\r" + line + "   ")
    sys.stdout.flush()
    if total and written >= total:
        sys.stdout.write("\n")
        sys.stdout.flush()
