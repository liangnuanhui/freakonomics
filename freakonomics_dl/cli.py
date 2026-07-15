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
            "from a curated list page (HTTP, no browser)."
        ),
    )
    p.add_argument(
        "--from-page",
        default=DEFAULT_LIST,
        help=f"Curated list/article URL (default: most-downloaded roundup)",
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
        "--delay",
        type=float,
        default=1.5,
        help="Minimum seconds between HTTP requests (default: 1.5)",
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
    )
    raise SystemExit(dl.run())
