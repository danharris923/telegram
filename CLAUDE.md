# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Two sibling Python pipelines that share one Google Sheet as their message queue:

- `guru_amz_pipeline/` — **Producer**. Three-phase scraper (guru → Amazon → finalize) that fills rows A–H with deal data, dedupes against the archive tab, then filters+sorts them.
- `telegram-pipeline/` — **Consumer**. Reads row 1, posts it to a Telegram channel, archives the row to `Sheet2`, deletes it from the main sheet, exits. Designed to run on cron 20× per day at staggered times across Canadian waking hours.

Both pipelines use the same `google_service_account.json` credentials file (checked-in copy at the repo root; `guru_amz_pipeline/` also has its own copy).

**Dedupe loop:** the consumer appends every posted row to `Sheet2` (auto-created on first post) before deleting it from the main sheet. The producer's Phase 3 (`finalize.py`) reads col A of `Sheet2` into a set and drops any incoming row whose guru URL is already in that set — so a deal posted yesterday won't be posted again today even if it re-appears in today's scrape.

## Shared Sheet Contract

Target sheet: `1I4cZ-V6uA7MrIj7t-mlH8-9JeSsD7eIg0v252tbz_Jc`. Row 1 is a header; data starts on row 2 in the producer, but the consumer treats row 1 as the next item to post (it deletes after posting, so whatever header existed is gone after the first run — the two pipelines effectively own the sheet at different times).

| Col | Producer writer      | Meaning                     | Consumer use (caption field)         |
|-----|----------------------|-----------------------------|--------------------------------------|
| A   | (manual input)       | SavingsGuru URL             | **link** — the href                  |
| B   | `guru_scrape.py`     | Promo code                  | `code` (fallback for coupon)         |
| C   | `guru_scrape.py`     | Resolved Amazon product URL | —                                    |
| D   | `amz_scrape.py`      | Image URL (`_AC_SL1500_`)   | `image_url` — triggers sendPhoto     |
| E   | `amz_scrape.py`      | Price                       | —                                    |
| F   | `amz_scrape.py`      | Discount %                  | `discount` → "`<F>` off"             |
| G   | `amz_scrape.py`      | Coupon value                | `coupon` → "use promo code `<G>`…"   |
| H   | `amz_scrape.py`      | Extra promo codes           | —                                    |

The consumer reads column A as the link (via `GOOGLE_SHEET_LINK_COLUMN` env var), but B/D/F/G column positions are **hardcoded** in `sheets_reader.py`. If producer columns are rearranged, update both the `amz_scrape.py` / `guru_scrape.py` writers and the consumer's `sheets_reader.py` indices.

## guru_amz_pipeline/

Run locally on Windows:

```bash
cd guru_amz_pipeline
pip install gspread google-auth requests beautifulsoup4 playwright colorama
python -m playwright install chrome
run_pipeline.bat          # runs all three phases in order
# or individually:
python guru_scrape.py     # Phase 1 — guru pages → B, C
python amz_scrape.py      # Phase 2 — Amazon pages → D, E, F, G, H
python finalize.py        # Phase 3 — filter + sort in place
```

- **Phase 1 (`guru_scrape.py`)**: threaded (`MAX_WORKERS=3`) HTTP scraper. Uses `requests` + BeautifulSoup. Regex patterns in `PROMO_PATTERNS` extract promo codes from guru post bodies; first `amzn.to`/`amazon.` link inside `div.entry-content` gets followed (cache-busted) and written to C.
- **Phase 2 (`amz_scrape.py`)**: Playwright persistent context at `.amazon_chrome_profile/`. **Must be run headful and logged into amazon.ca once** — cookies persist for future runs. `CONCURRENT_TABS=3` workers share that one login. Image extraction has a `requests` fast path (parses `colorImages` JSON / `data-a-dynamic-image`) before falling back to Playwright DOM. Batch-flushes every 20 rows via `ws.batch_update`.
- **Phase 3 (`finalize.py`)**: in-place dedupe + filter + sort. Reads col A of `Sheet2` (the telegram-pipeline's archive) into a set and drops any matching row. Of the survivors, keeps rows that have a promo code (B or H) **or** discount ≥ `MIN_DISCOUNT` (currently **30%**, col F). Sorts: code deals first (by discount desc), then non-code rows (by discount desc). Clears every row below the kept set — **destructive**, run only after phases 1–2 complete.

Both scrapers are idempotent: already-populated rows are skipped (phase 1 skips if B+C filled; phase 2 skips if D+E filled).

Credentials and Chrome-profile lookup: each script checks next to itself first, then one directory up. This lets the folder be lifted out to a new project without editing paths.

## telegram-pipeline/

```bash
cd telegram-pipeline
pip install -r requirements.txt
python main.py                             # normal run (with jitter sleep)
TELEGRAM_PIPELINE_NO_JITTER=1 python main.py  # skip the jitter for debugging
```

### Schedule — 20 posts/day at random waking-hour times

Goal: up to 20 posts/day, staggered across ~7 AM – 10 PM Canadian local time, with timing that drifts day-to-day so the feed doesn't look automated. Two mechanisms combined:

1. **20 explicit systemd OnCalendar entries** at ~48-minute intervals, each qualified with `America/Toronto` so the droplet can stay on UTC without affecting other workloads.
2. **In-script jitter sleep**: `main.py` sleeps a uniform random 0–20 min at the start of every run (see `JITTER_MAX_SECONDS` in `main.py`). Set `TELEGRAM_PIPELINE_NO_JITTER=1` to disable for manual testing.

Deployment on the scraper droplet uses **systemd timers, not cron** (the crontab contains only a migration-note comment). Two units:

`/etc/systemd/system/telegram-pipeline.service`:
```ini
[Unit]
Description=Telegram posting pipeline
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/telegram/telegram-pipeline
ExecStart=/usr/bin/python3 /opt/telegram/telegram-pipeline/main.py
TimeoutStartSec=300
```

`/etc/systemd/system/telegram-pipeline.timer`:
```ini
[Unit]
Description=Telegram pipeline — 20 posts/day across Canadian waking hours

[Timer]
# 20 slots at ~48-min intervals, 07:03 to 22:15 America/Toronto.
# main.py adds an in-script 0-20 min random jitter on top of these fixed times.
OnCalendar=*-*-* 07:03:00 America/Toronto
OnCalendar=*-*-* 07:51:00 America/Toronto
OnCalendar=*-*-* 08:39:00 America/Toronto
OnCalendar=*-*-* 09:27:00 America/Toronto
OnCalendar=*-*-* 10:15:00 America/Toronto
OnCalendar=*-*-* 11:03:00 America/Toronto
OnCalendar=*-*-* 11:51:00 America/Toronto
OnCalendar=*-*-* 12:39:00 America/Toronto
OnCalendar=*-*-* 13:27:00 America/Toronto
OnCalendar=*-*-* 14:15:00 America/Toronto
OnCalendar=*-*-* 15:03:00 America/Toronto
OnCalendar=*-*-* 15:51:00 America/Toronto
OnCalendar=*-*-* 16:39:00 America/Toronto
OnCalendar=*-*-* 17:27:00 America/Toronto
OnCalendar=*-*-* 18:15:00 America/Toronto
OnCalendar=*-*-* 19:03:00 America/Toronto
OnCalendar=*-*-* 19:51:00 America/Toronto
OnCalendar=*-*-* 20:39:00 America/Toronto
OnCalendar=*-*-* 21:27:00 America/Toronto
OnCalendar=*-*-* 22:15:00 America/Toronto
Persistent=true
RandomizedDelaySec=0

[Install]
WantedBy=timers.target
```

Notes on the settings:
- `Persistent=true` — if the box is down at a trigger time, systemd runs the missed job once it comes back up.
- `RandomizedDelaySec=0` — deliberate. The in-script jitter in `main.py` already handles day-to-day drift; stacking systemd's randomization on top would double-jitter.
- Timezone is specified **per entry** (`America/Toronto`), not via `timedatectl`. This keeps the system clock on UTC for logs and other scraper workloads on the same droplet.

After editing either unit: `systemctl daemon-reload && systemctl restart telegram-pipeline.timer`. Verify: `systemctl list-timers telegram-pipeline.timer`.

If the sheet runs out mid-day, each remaining trigger exits cleanly with "No rows remaining" — no harm done.

**Single-run pipeline** — each invocation posts exactly one row then exits. Flow in `main.py`:

1. Random 0–20 min jitter sleep (skipped when `TELEGRAM_PIPELINE_NO_JITTER=1`)
2. Import `config` (triggers env var validation)
3. Validate Telegram bot + channel via Bot API
4. `sheets_reader.get_first_row()` — reads row 1, pulls link (A), image (D), code (B), discount (F), coupon (G)
5. Build HTML caption: `<discount> off` / `use promo code <X> and save` / `View deal`, then wrap **the entire multi-line caption in a single `<a href=link>` tag** so every line is a tappable target (deliberate — more click real estate than just "View deal")
6. If `image_url` present → `sendPhoto` with caption; else → `sendMessage`
7. On success, `sheets_tracker.archive_posted_row(1, raw_row)` — appends the row to `Sheet2` (auto-creating the tab if needed), then deletes row 1 from the main sheet
8. Print remaining count, exit

**Module responsibilities:**

- `config.py` — Loads all env vars from `.env` via python-dotenv, validates on import, exposes a single `config` class instance (not a dict)
- `sheets_reader.py` — Read-only Google Sheets access via gspread + service account auth. Column positions for code/discount/coupon/image are hardcoded (see Shared Sheet Contract above)
- `sheets_tracker.py` — Archives posted rows to `Sheet2` then deletes them from the main sheet. Both steps have retry-once-after-3s logic. Auto-creates `Sheet2` if missing.
- `telegram_sender.py` — Telegram Bot API via raw `requests` (not python-telegram-bot). Has 3-second rate limiting between sends. Uses `parse_mode=HTML` for captions
- `logger.py` — Colorama-based colored console logger

**Failure behavior is asymmetric and deliberate:**
- Telegram send fails → row stays in main sheet, retried next run.
- Telegram send succeeds + archive-append fails → row stays in main sheet, reposts next run (duplicate post possible, but no data loss).
- Archive-append succeeds + delete-from-main fails → row is in both Sheet2 and main; will repost next run. `main.py` prints a loud warning.

## Conventions

- **Logger pattern** (telegram-pipeline): every module does `from logger import get_logger; log = get_logger("module_name")` with a hardcoded string name (not `__name__`)
- **Logger pattern** (guru_amz_pipeline): bare `colorama` with `Fore.COLOR + f"[TAG] ..."` `print()` calls
- **Config pattern** (telegram-pipeline): `from config import config` then `config.TELEGRAM_BOT_TOKEN`. Importing `config` is what validates — don't try to import it conditionally.
- **Code style**: verbose and heavily commented — this codebase is maintained by a non-professional programmer. Long descriptive variable names, comments above every logical block. Match this style when editing.
- **Error handling**: fail loud with full exception details. Never silently swallow errors.
- **No `.env` in git**: only `.env.example` is committed. Real `.env` is user-created.

## Environment Variables (telegram-pipeline only)

All required (see `.env.example`): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `GOOGLE_CREDENTIALS_JSON_PATH`, `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_NAME`, `GOOGLE_SHEET_LINK_COLUMN`.

Optional:
- `TELEGRAM_PIPELINE_NO_JITTER` — if set to any value, disables the 0–20 min random sleep at the start of `main.py`. Use for manual/debug runs where you don't want to wait.

`guru_amz_pipeline/` has **no** env vars — sheet ID and paths are baked in at the top of each script.
