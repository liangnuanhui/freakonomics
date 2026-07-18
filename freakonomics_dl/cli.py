"""CLI entry for the Freakonomics HTTP downloader."""

from __future__ import annotations

import argparse
from pathlib import Path

from .downloader import CuratedDownloader
from .interactive import run_interactive
from .rss import DEFAULT_NSQ_RSS
from .rss_downloader import RssDownloader


DEFAULT_LIST = (
    "https://freakonomics.com/get-started-with-freakonomics-radio-"
    "our-most-downloaded-episodes/"
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="freakonomics-dl",
        description=(
            "Download Freakonomics episode audio and/or transcripts "
            "(HTTP, no browser).\n\n"
            "Modes:\n"
            "  1) Website (interactive when --from-page omitted):\n"
            "       poetry run python -m freakonomics_dl --out downloads/new_folder\n"
            "  2) Website batch:\n"
            "       poetry run python -m freakonomics_dl --from-page URL --out DIR\n"
            "  3) Podcast RSS (audio from enclosure; optional show notes):\n"
            "       poetry run python -m freakonomics_dl --from-rss FEED_URL --out DIR\n"
            "       poetry run python -m freakonomics_dl --from-rss nsq --out DIR\n\n"
            "Website files: \"<Episode Title>.mp3\" and \"<Episode Title>.md\".\n"
            "RSS files: \"[N-]Title.mp3\" (+ optional .md from feed description).\n"
            "PLUS skipped by default on website path; EXTRA kept; series auto-paginate."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "status legend (runtime):\n"
            "  [probe]    interactive URL structure check\n"
            "  [list]     list/archive fetch, full-archive follow, pagination\n"
            "  [rss]      podcast RSS fetch / parse\n"
            "  [plan]     totals before download\n"
            "  [i/N]      per-episode steps\n"
            "  [progress] running ok/fail/left counters\n"
            "  ↻          automatic retry\n"
            "  ⬇          audio download progress bar\n"
        ),
    )
    p.add_argument(
        "--from-page",
        default=None,
        help=(
            "List / series / series-full / episode URL. "
            "If omitted (and no --from-rss), enter interactive mode."
        ),
    )
    p.add_argument(
        "--from-rss",
        default=None,
        metavar="URL|nsq",
        help=(
            "Podcast RSS feed URL, or the shortcut 'nsq' for the "
            f"No Stupid Questions Simplecast feed ({DEFAULT_NSQ_RSS}). "
            "Downloads audio enclosures; use --transcript to also save "
            "RSS description as Markdown (not full site transcripts)."
        ),
    )
    p.add_argument(
        "--interactive",
        action="store_true",
        help="Force interactive wizard (even if --from-page is set, page is pre-filled only via prompt)",
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
        help=(
            "Website: save full episode transcript. "
            "RSS: save feed description/show notes as .md (default: true for website; "
            "for RSS you typically want --no-transcript unless you need notes)."
        ),
    )
    p.add_argument(
        "--skip-plus",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip PLUS (subscriber) episodes (default: true). EXTRA is kept. Website only.",
    )
    p.add_argument(
        "--follow-full-archive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If page has «Show Full Archive», use series-full (default: true). Website only.",
    )
    p.add_argument(
        "--max-pages",
        type=int,
        default=200,
        help="Max archive pages to follow (default: 200). Website only.",
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
        help="Batch/RSS mode only: first N episodes from the list/feed",
    )
    p.add_argument(
        "--min-transcript-chars",
        type=int,
        default=500,
        help="Website only: reject transcripts shorter than this (default: 500)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if files/progress say completed",
    )
    return p


def _resolve_rss_url(value: str) -> str:
    key = value.strip().lower()
    if key in {"nsq", "no-stupid-questions", "nostupidquestions"}:
        return DEFAULT_NSQ_RSS
    return value.strip()


def _rss_want_description(args: argparse.Namespace, argv: list[str] | None) -> bool:
    """
    RSS feeds do not include full transcripts — only show notes/description.

    Default for RSS is audio-only. Write .md only when the user explicitly
    passes --transcript (website mode still defaults --transcript to on).
    """
    import sys

    tokens = list(argv if argv is not None else sys.argv[1:])
    if "--transcript" in tokens:
        return True
    if "--no-transcript" in tokens:
        return False
    return False


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.from_rss and args.from_page:
        raise SystemExit(
            "error: use either --from-rss or --from-page, not both"
        )

    if args.from_rss:
        feed_url = _resolve_rss_url(args.from_rss)
        dl = RssDownloader(
            feed_url=feed_url,
            out_dir=args.out,
            want_audio=args.audio,
            want_description=_rss_want_description(args, argv),
            delay=args.delay,
            limit=args.limit,
            force=args.force,
            max_retries=args.retries,
        )
        raise SystemExit(dl.run())

    use_interactive = args.interactive or not args.from_page

    if use_interactive:
        code = run_interactive(
            out_dir=args.out,
            want_audio=args.audio,
            want_transcript=args.transcript,
            min_transcript_chars=args.min_transcript_chars,
            delay=args.delay,
            max_retries=args.retries,
            skip_plus=args.skip_plus,
            follow_full_archive=args.follow_full_archive,
            max_pages=args.max_pages,
            force=args.force,
        )
        raise SystemExit(code)

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
