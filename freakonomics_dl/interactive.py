"""Interactive CLI wizard for URL probe + scoped download."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .curated import EpisodeRef, _slug_from_url
from .downloader import CuratedDownloader
from .http_client import HttpClient
from .probe import ProbeResult, print_probe_report, probe_url


def _prompt(msg: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        raw = input(f"{msg}{suffix}: ").strip()
    except EOFError:
        print()
        return default or ""
    return raw if raw else (default or "")


def _prompt_choice(msg: str, allowed: Sequence[str], default: str) -> str:
    allowed_l = {a.lower(): a for a in allowed}
    while True:
        raw = _prompt(msg, default)
        key = raw.lower()
        if key in allowed_l:
            return allowed_l[key]
        print(f"  请输入 {', '.join(allowed)} 之一", flush=True)


def parse_selection(expr: str, total: int) -> List[int]:
    """
    Parse 1-based selection like: 1-10, 3, 5-7, 12
    Returns sorted unique 0-based indices.
    """
    expr = expr.strip()
    if not expr:
        raise ValueError("空选择")
    indices: set[int] = set()
    for part in re.split(r"\s*,\s*", expr):
        if not part:
            continue
        if re.fullmatch(r"\d+", part):
            n = int(part)
            if n < 1 or n > total:
                raise ValueError(f"序号 {n} 超出范围 1-{total}")
            indices.add(n - 1)
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if not m:
            raise ValueError(f"无法解析: {part!r}（示例: 1-20 或 3 或 1,3,5-8）")
        a, b = int(m.group(1)), int(m.group(2))
        if a > b:
            a, b = b, a
        if a < 1 or b > total:
            raise ValueError(f"范围 {a}-{b} 超出 1-{total}")
        for n in range(a, b + 1):
            indices.add(n - 1)
    return sorted(indices)


def _print_episode_preview(episodes: List[EpisodeRef], head: int = 5, tail: int = 3) -> None:
    n = len(episodes)
    if n == 0:
        return
    print(f"\n  列表共 {n} 集（已跳过 PLUS）:", flush=True)
    show = set(range(min(head, n))) | set(range(max(0, n - tail), n))
    last = -2
    for i in range(n):
        if i not in show:
            continue
        if last != -2 and i > last + 1:
            print("    …", flush=True)
        print(f"   {i + 1:4d}. {episodes[i].title[:72]}", flush=True)
        last = i


def run_interactive(
    *,
    out_dir: Path,
    want_audio: bool = True,
    want_transcript: bool = True,
    min_transcript_chars: int = 500,
    delay: float = 1.5,
    max_retries: int = 5,
    skip_plus: bool = True,
    follow_full_archive: bool = True,
    max_pages: int = 200,
    force: bool = False,
) -> int:
    print("=" * 64, flush=True)
    print(" Freakonomics 交互式下载器", flush=True)
    print("=" * 64, flush=True)
    print(f" 输出目录:  {out_dir.resolve()}", flush=True)
    print(
        f" 资源:      音频={'开' if want_audio else '关'}  "
        f"文稿={'开' if want_transcript else '关'}",
        flush=True,
    )
    print(
        f" 过滤:      跳过 PLUS={'开' if skip_plus else '关'}  "
        f"跟随 Full Archive={'开' if follow_full_archive else '关'}",
        flush=True,
    )
    print(
        " 说明:      支持精选页 / series / series-full / 单集 /podcast/…",
        flush=True,
    )
    print("=" * 64, flush=True)

    http = HttpClient(min_interval=delay, max_retries=max_retries)

    while True:
        print("\n请输入要抓取的网址（回车退出）", flush=True)
        raw = _prompt("URL")
        if not raw:
            print("已退出。", flush=True)
            return 0

        print("\n[probe] 正在访问并分析页面结构…", flush=True)
        result = probe_url(
            raw,
            http,
            skip_plus=skip_plus,
            follow_full_archive=follow_full_archive,
            sample_episode=True,
        )
        print_probe_report(result)

        if not result.ok:
            print("\n该网址当前不可抓取，或没有可用公开内容。", flush=True)
            again = _prompt_choice("重新输入网址? (y/n)", ["y", "n"], "y")
            if again == "y":
                continue
            return 1

        # ---- single episode ----
        if result.page_kind == "episode":
            print("\n下一步:", flush=True)
            print("  [1] 下载这一集", flush=True)
            print("  [2] 重新输入网址", flush=True)
            print("  [0] 退出", flush=True)
            choice = _prompt_choice("选择", ["1", "2", "0"], "1")
            if choice == "0":
                return 0
            if choice == "2":
                continue
            ep = result.sample_episodes[0]
            dl = _make_downloader(
                list_url=ep.url,
                out_dir=out_dir,
                want_audio=want_audio,
                want_transcript=want_transcript,
                min_transcript_chars=min_transcript_chars,
                delay=delay,
                max_retries=max_retries,
                skip_plus=skip_plus,
                follow_full_archive=False,
                max_pages=1,
                force=force,
            )
            return dl.run(episodes=[ep])

        # ---- list / series ----
        print("\n下一步:", flush=True)
        print("  [1] 抓取全部（自动翻页，跳过 PLUS）", flush=True)
        print("  [2] 自行选择范围（先构建完整列表）", flush=True)
        print("  [3] 只抓取某一个单集", flush=True)
        print("  [4] 重新输入网址", flush=True)
        print("  [0] 退出", flush=True)
        choice = _prompt_choice("选择", ["1", "2", "3", "4", "0"], "1")

        if choice == "0":
            return 0
        if choice == "4":
            continue

        list_url = result.effective_list_url or result.input_url
        dl = _make_downloader(
            list_url=list_url,
            out_dir=out_dir,
            want_audio=want_audio,
            want_transcript=want_transcript,
            min_transcript_chars=min_transcript_chars,
            delay=delay,
            max_retries=max_retries,
            skip_plus=skip_plus,
            follow_full_archive=follow_full_archive,
            max_pages=max_pages,
            force=force,
        )

        if choice == "1":
            # full list via downloader pagination
            return dl.run()

        # choice 2 or 3: need full episode list
        print("\n[list] 正在构建完整剧集列表（含翻页）…", flush=True)
        try:
            episodes = dl.fetch_episode_list()
        except Exception as e:
            print(f"[list] FAIL  {e}", flush=True)
            return 1
        if not episodes:
            print("[list] FAIL  列表为空", flush=True)
            return 1

        _print_episode_preview(episodes)

        if choice == "2":
            print(
                "\n请输入范围（1-based）。示例: 1-20   或  5   或  1,3,5-10",
                flush=True,
            )
            while True:
                expr = _prompt(f"范围 (共 {len(episodes)} 集)")
                try:
                    idxs = parse_selection(expr, len(episodes))
                    break
                except ValueError as e:
                    print(f"  ✗ {e}", flush=True)
            selected = [episodes[i] for i in idxs]
            print(f"\n将下载 {len(selected)} 集。", flush=True)
            return dl.run(episodes=selected)

        # choice == 3: one episode
        print("\n方式:", flush=True)
        print("  [1] 按列表序号选择", flush=True)
        print("  [2] 粘贴单集 URL", flush=True)
        sub = _prompt_choice("选择", ["1", "2"], "1")
        if sub == "1":
            while True:
                raw_n = _prompt(f"序号 (1-{len(episodes)})")
                if raw_n.isdigit() and 1 <= int(raw_n) <= len(episodes):
                    ep = episodes[int(raw_n) - 1]
                    break
                print("  无效序号", flush=True)
        else:
            u = _prompt("单集 URL")
            # try match in list first
            u_norm = u.rstrip("/") + "/"
            matched = next(
                (e for e in episodes if e.url.rstrip("/") == u_norm.rstrip("/")),
                None,
            )
            if matched:
                ep = matched
            else:
                ep = EpisodeRef(
                    title="Episode",
                    url=u_norm if "://" in u else "https://" + u_norm,
                    slug=_slug_from_url(u),
                )
                # normalize url
                if not ep.url.startswith("http"):
                    ep = EpisodeRef(
                        title=ep.title,
                        url="https://" + ep.url.lstrip("/"),
                        slug=ep.slug,
                    )
        print(f"\n将下载: {ep.title}\n  {ep.url}", flush=True)
        return dl.run(episodes=[ep])


def _make_downloader(**kwargs) -> CuratedDownloader:
    return CuratedDownloader(**kwargs)
