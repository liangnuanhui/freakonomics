# Freakonomics Downloader

**Language / 语言:** [中文](README.md) | [**English**](README.en.md)

---

Download **podcast audio (mp3)** and **full transcripts (Markdown)** from [freakonomics.com](https://freakonomics.com/). You can also bulk-download audio from a **podcast RSS feed** (e.g. No Stupid Questions on Simplecast).

**Primary path: HTTP (requests + BeautifulSoup)** — no browser required. Works with roundup/list articles and **series archive pages** (follows “Show Full Archive” and paginates via “Older Posts”).

By default **PLUS** (subscriber) episodes are skipped; **EXTRA** episodes are treated like regular episodes.

---

## Quick start

### Install

```bash
poetry install
poetry run python -m freakonomics_dl --help
```

### Interactive mode (recommended)

If you omit `--from-page`, an interactive wizard starts:

```bash
poetry run python -m freakonomics_dl --out downloads/new_folder
```

Flow:

1. Enter a URL (roundup / `series/` / `series-full/` / single `/podcast/...`)
2. **Probe the page structure** — scrapeable or not, episode count, PLUS count, pagination, sample audio/transcript
3. **Choose what to download:** audio + transcript / transcript only / audio only
4. Choose next step:
   - **Download all** (auto-pagination, skip PLUS)
   - **Select a range** (e.g. `1-20` / `5` / `1,3,5-10`)
   - **Single episode** (by index or paste URL)
   - Enter another URL / quit

### Batch mode (website)

```bash
# ~20 “most downloaded” episodes
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/get-started-with-freakonomics-radio-our-most-downloaded-episodes/" \
  --out downloads/most-downloaded

# Full series archive
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/series/freakonomics-radio/" \
  --out downloads/freakonomics-radio
```

### RSS mode (audio enclosures)

Pull the episode list from a podcast RSS feed and download mp3s (resume + `progress.json` same as the website path).  
RSS does **not** include full site transcripts; default is **audio only**. Pass `--transcript` to also save the feed description as `.md`.

```bash
# No Stupid Questions shortcut
poetry run python -m freakonomics_dl --from-rss nsq --out downloads/nsq-audio

# Any feed URL; smoke-test one episode
poetry run python -m freakonomics_dl \
  --from-rss "https://feeds.simplecast.com/dfh_verV" \
  --out downloads/nsq-audio \
  --limit 1

# Audio + RSS show notes markdown
poetry run python -m freakonomics_dl \
  --from-rss nsq \
  --out downloads/nsq-audio \
  --transcript \
  --limit 3
```

RSS filenames: `{N}-{title}.mp3` when an episode number is available, else `{title}.mp3`.

---

## CLI options

| Option | Description | Default |
|--------|-------------|---------|
| `--from-page URL` | Roundup / series / single episode; **omit (and no --from-rss) for interactive mode** | none (interactive) |
| `--from-rss URL\|nsq` | Podcast RSS; `nsq` = No Stupid Questions Simplecast feed | none |
| `--interactive` | Force interactive wizard | off |
| `--out DIR` | Output directory | `downloads/most-downloaded` |
| `--audio` / `--no-audio` | Download mp3 (batch mode) | on |
| `--transcript` / `--no-transcript` | Website: full transcript. RSS: off by default; pass `--transcript` for feed show notes | website on / RSS off |
| `--skip-plus` / `--no-skip-plus` | Skip PLUS episodes (EXTRA kept) | on |
| `--follow-full-archive` / `--no-follow-full-archive` | Follow “Show Full Archive” when present | on |
| `--max-pages N` | Max archive pages to follow | `200` |
| `--delay SEC` | Min interval between HTTP requests | `1.5` |
| `--retries N` | Max retries on 429 / 5xx / network errors | `5` |
| `--limit N` | Process only first N episodes (batch) | all |
| `--force` | Re-download even if already complete | off |
| `--min-transcript-chars N` | Fail if transcript shorter than this | `500` |

### Examples

```bash
# Smoke-test one episode
poetry run python -m freakonomics_dl --limit 1 --out downloads/smoke-test

# Transcripts only
poetry run python -m freakonomics_dl --no-audio --out downloads/most-downloaded

# Audio only
poetry run python -m freakonomics_dl --no-transcript --out downloads/most-downloaded

# Another roundup page
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/some-other-roundup/" \
  --out downloads/other-roundup

# Freakonomics Radio series (full archive + pagination, skip PLUS)
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/series/freakonomics-radio/" \
  --out downloads/freakonomics-radio

# Transcripts only, first 3 episodes
poetry run python -m freakonomics_dl \
  --from-page "https://freakonomics.com/series/freakonomics-radio/" \
  --out downloads/freakonomics-radio \
  --no-audio --limit 3

# Force re-download
poetry run python -m freakonomics_dl --force --out downloads/most-downloaded
```

List parsing: group anchors by `/podcast/` URL; title = longest non-label text; URLs labeled **PLUS** are dropped by default; **EXTRA** is kept. Series pages with “Show Full Archive” jump to `series-full`, then follow “Older Posts”.

---

## Output layout

Audio and transcript for each episode share the **same basename** in the **same folder**:

```
downloads/most-downloaded/
├── episodes.json      # parsed list
├── progress.json      # resume state
├── Air Travel Is a Miracle. Why Do We Hate It.mp3
├── Air Travel Is a Miracle. Why Do We Hate It.md
├── Why Are There So Many Bad Bosses.mp3
├── Why Are There So Many Bad Bosses.md
└── …
```

### Progress & resume

Example `progress.json`:

```json
{
  "completed": ["air-travel-is-a-miracle-why-do-we-hate-it"],
  "failed": {
    "some-slug": "transcript missing or too short (0 chars)"
  },
  "last_updated": "2026-07-15T16:00:00+08:00"
}
```

- In `completed` **or** matching files already on disk → **SKIP**
- `--force` ignores that and re-downloads
- Interrupt and re-run the same command to resume

---

## Runtime status labels

| Tag | Meaning |
|-----|---------|
| `[probe]` | Interactive URL structure check |
| `[list]` | Fetch/parse list or archive pages |
| `[plan]` | Totals before download |
| `[i/N] status:` | Per episode: `FETCH` / `WRITE` / `DOWNLOAD` / `DONE` / `FAIL` / `SKIP` |
| `[progress]` | Running ok / fail / left / elapsed |
| `↻` | Automatic retry (HTTP 429, 5xx, network) |
| `⬇` | Audio download progress bar |

---

## End-to-end pipeline

1. GET `--from-page` (or URL from interactive prompt)  
2. If “Show Full Archive” exists → use `series-full` (optional)  
3. Parse episodes; skip PLUS; follow “Older Posts” until done or `--max-pages` / `--limit`  
4. Write `episodes.json`  
5. For each episode: GET page → extract `audio[src]` + Episode Transcript  
6. Stream `<title>.mp3` and write `<title>.md` in the same folder  
7. Update `progress.json`; retry on 429 / 5xx / network errors  

Transcripts are usually already in the static HTML — no need to click expand, no Playwright required.

```
series/ or roundup page
  → (optional) series-full
  → page/1 … Older Posts → page/2 …
  → filter PLUS; keep EXTRA + regular shows
episode page
  → mp3 + Episode Transcript → <title>.mp3 / <title>.md
```

---

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| No episodes / `no episode links` | Check `--from-page`; page still has `/podcast/` links? |
| `no audio URL` | Page structure changed; open episode and look for `<audio>` |
| `transcript … too short` | Missing transcript or selector drift |
| 403 / connection reset | Increase `--delay`; retry later; browser fallback only if needed later |
| Disk filling up | Use `--no-audio` or `--limit` |
| Re-download one episode | Delete its `.mp3`/`.md` and re-run, or use `--force` |

---

## Project layout

```
freakonomics/
├── freakonomics_dl/          # main package (HTTP downloader)
│   ├── cli.py
│   ├── curated.py            # list/series parsing
│   ├── episode.py            # single-episode audio + transcript
│   ├── downloader.py         # website list → download
│   ├── rss.py                # podcast RSS parsing
│   ├── rss_downloader.py     # RSS → audio (+ optional notes)
│   ├── http_client.py
│   ├── interactive.py        # interactive wizard
│   ├── probe.py              # URL structure probe
│   ├── names.py              # title → filename
│   └── progress.py
├── simple_downloader.py      # legacy: NSQ + Playwright
├── pyproject.toml
├── README.md                 # Chinese docs
└── README.en.md              # English docs
```

---

## Legacy: `simple_downloader.py`

Early NSQ-only downloader using a visible Playwright browser. Kept for reference only — prefer `freakonomics_dl`.

| | `freakonomics_dl` | `simple_downloader.py` |
|--|-------------------|------------------------|
| Transport | HTTP | Playwright browser |
| Lists | Roundups / series / episodes | Fixed NSQ series-full |
| Audio | Yes | No |
| Transcript | Yes | Yes |
| Status | **Recommended** | Legacy |

```bash
# Optional browser stack (only for the legacy script)
poetry install -E browser
poetry run playwright install chromium
poetry run python simple_downloader.py
```

---

## Notes

- Audio files are large (tens of MB each); a 20-episode set can be ~1GB — keep disk free and respect rate limits  
- Intended for personal offline use; do not bulk-mirror or redistribute content  
- If the site starts returning 403/Cloudflare often, a cookie/Playwright fallback could be added later (not the main path today)  
- Transcripts shorter than the threshold (default 500 chars) are treated as failures so DOM changes surface quickly  

## License & copyright

Site content belongs to Freakonomics and respective rights holders. This tool only automates downloading for your own use; you are responsible for compliance with their terms.
