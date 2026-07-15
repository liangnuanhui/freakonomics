"""CLI entry for the Freakonomics HTTP downloader."""

from __future__ import annotations

import argparse
from pathlib import Path

from .downloader import CuratedDownloader


DEFAULT_LIST = (
    "https://freakonomics.com/get-started-with-freakonomics-radio-"
    "our-most-downloaded-episodes/"
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="freakonomics-dl",
        description=(
            "Download Freakonomics episode audio and/or transcripts "
            "from a curated list page or series archive (HTTP, no browser).\n\n"
            "Files are saved in the output folder as:\n"
            '  "<Episode Title>.mp3" and "<Episode Title>.md"\n\n'
            "Series pages: follows «Show Full Archive» when present, then\n"
            "paginates via «Older Posts». PLUS episodes are skipped by default;\n"
            "EXTRA is treated like a normal episode."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "status legend (runtime):\n"
            "  [list]     list/archive fetch, full-archive follow, pagination\n"
            "  [plan]     totals before download\n"
            "  [i/N]      per-episode steps (FETCH / WRITE / DOWNLOAD / DONE / FAIL / SKIP)\n"
            "  [progress] running ok/fail/left counters\n"
            "  ↻          automatic retry (HTTP 429/5xx or network error)\n"
            "  ⬇          audio download progress bar\n"
        ),
    )
    p.add_argument(
        "--from-page",
        default=DEFAULT_LIST,
        help="List / series / series-full URL (default: most-downloaded roundup)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("downloads/most-downloaded"),
        help="Output directory (default: downloads/most-downloaded)",
    )
    p.add_argument(
        "--audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Download mp3 audio (default: true)",
    )
    p.add_argument(
        "--transcript",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Save full transcript markdown (default: true)",
    )
    p.add_argument(
        "--skip-plus",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip PLUS (subscriber) episodes (default: true). EXTRA is kept.",
    )
    p.add_argument(
        "--follow-full-archive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If page has «Show Full Archive», use series-full (default: true)",
    )
    p.add_argument(
        "--max-pages",
        type=int,
        default=200,
        help="Max archive pages to follow (default: 200)",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Minimum seconds between HTTP requests (default: 1.5)",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=5,
        help="Max retries on rate-limit/network/5xx errors (default: 5)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N episodes from the list",
    )
    p.add_argument(
        "--min-transcript-chars",
        type=int,
        default=500,
        help="Reject transcripts shorter than this (default: 500)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if files/progress say completed",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    dl = CuratedDownloader(
        list_url=args.from_page,
        out_dir=args.out,
        want_audio=args.audio,
        want_transcript=args.transcript,
        min_transcript_chars=args.min_transcript_chars,
        delay=args.delay,
        limit=args.limit,
        force=args.force,
        max_retries=args.retries,
        skip_plus=args.skip_plus,
        follow_full_archive=args.follow_full_archive,
        max_pages=args.max_pages,
    )
    raise SystemExit(dl.run())
