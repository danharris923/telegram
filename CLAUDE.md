# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated Telegram posting pipeline in Python. Reads links from a Google Sheet one at a time, posts each to a Telegram channel, marks the row as "posted" to prevent double-posting, then exits. Designed to run as a cron job (every 3 hours on a Debian droplet).

## Running

All code lives in `telegram-pipeline/`. Run from that directory:

```bash
cd telegram-pipeline
pip install -r requirements.txt
python main.py
```

Cron line (every 3 hours):
```
0 */3 * * * cd /path/to/telegram-pipeline && /usr/bin/python3 main.py >> /var/log/telegram-pipeline.log 2>&1
```

## Architecture

**Single-run pipeline** — each invocation posts exactly one row then exits. The flow in `main.py` is:

1. Load config (importing `config.py` triggers env var validation)
2. Validate Telegram bot token and channel via Bot API
3. `sheets_reader.get_first_row()` — reads row 1 from the sheet
4. `telegram_sender.send_message()` — posts to channel via HTTP (requests library, not python-telegram-bot)
5. `sheets_tracker.delete_posted_row()` — deletes row 1 so the next row becomes first
6. `sheets_tracker.get_sheet_stats()` — prints remaining count, then exits

**Module responsibilities:**

- `config.py` — Loads all env vars from `.env` via python-dotenv, validates on import, exposes a single `config` class instance (not a dict)
- `sheets_reader.py` — Read-only Google Sheets access via gspread + service account auth
- `sheets_tracker.py` — Deletes posted rows from Google Sheets. Has retry logic (1 retry after 3s)
- `telegram_sender.py` — Telegram Bot API calls via raw `requests` (not a wrapper library). Has 3-second rate limiting between sends
- `logger.py` — Colorama-based colored console logger. All modules use `get_logger("module_name")`

## Conventions

- **Logger pattern**: Every module does `from logger import get_logger; log = get_logger("module_name")` with a hardcoded string name (not `__name__`)
- **Config pattern**: `from config import config` then access attributes like `config.TELEGRAM_BOT_TOKEN`
- **Code style**: Verbose and heavily commented — this codebase is maintained by a non-professional programmer. Long descriptive variable names, comments above every logical block
- **Error handling**: Fail loud with full exception details. Never silently swallow errors
- **No .env in git**: Only `.env.example` is committed. Real `.env` is user-created

## Environment Variables

All required (see `.env.example` for details): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `GOOGLE_CREDENTIALS_JSON_PATH`, `GOOGLE_SHEET_ID`, `GOOGLE_SHEET_NAME`, `GOOGLE_SHEET_LINK_COLUMN`

## Dependencies

gspread, google-auth, requests, colorama, python-dotenv (all pinned in `requirements.txt`)
