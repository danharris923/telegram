"""
main.py — Orchestrator for the Telegram posting pipeline.

This is the entry point. It runs the full pipeline in order:
1. Load and validate config
2. Validate Telegram bot and channel
3. Read the next unposted row from Google Sheets
4. Send the link to the Telegram channel
5. Mark the row as posted in the sheet
6. Print a summary and exit

Imports: sys, uuid, traceback, config, logger, sheets_reader, sheets_tracker, telegram_sender
Exports: none (entry point)
"""

import os
import sys
import uuid
import html
import time
import random
import traceback
from logger import get_logger

log = get_logger("main")

# Random-sleep jitter window applied at the start of every run.
# Cron fires at fixed times (see CLAUDE.md for the recipe); this adds
# 0–JITTER_MAX_SECONDS of delay so the actual post time drifts day to day,
# making the feed look less automated. Keep this smaller than the cron
# spacing so runs don't collide.
JITTER_MAX_SECONDS = 20 * 60  # 20 minutes


def main():
    """Run the full Telegram posting pipeline."""

    # Step 1: Print the big start banner
    log.section("TELEGRAM PIPELINE — RUN START")

    # Generate a short run ID for tracking this specific execution
    run_id = str(uuid.uuid4())[:8]
    log.info(f"Run ID: {run_id}")

    # Step 1b: Random jitter sleep so post times vary day-to-day.
    # Cron schedules fixed slots across Canadian waking hours; this adds
    # 0 to JITTER_MAX_SECONDS of drift on top. Skipped if the env var
    # TELEGRAM_PIPELINE_NO_JITTER is set to any truthy value (useful for
    # manual runs / debugging where you don't want to wait).
    if os.environ.get("TELEGRAM_PIPELINE_NO_JITTER"):
        log.info("TELEGRAM_PIPELINE_NO_JITTER set — skipping jitter sleep")
    else:
        jitter = random.randint(0, JITTER_MAX_SECONDS)
        log.info(f"Jitter sleep: {jitter}s ({jitter // 60}m {jitter % 60}s)")
        time.sleep(jitter)

    # Step 2: Load and validate config (this happens on import)
    log.info("Loading configuration...")
    from config import config  # noqa: F401 — importing triggers validation
    log.success("Configuration loaded and validated")

    # Step 3: Validate Telegram bot token
    log.info("Validating Telegram bot...")
    from telegram_sender import validate_bot, validate_channel, send_message, send_photo

    if not validate_bot():
        log.error("Bot token is invalid — cannot continue. Check TELEGRAM_BOT_TOKEN in .env")
        sys.exit(1)

    # Step 4: Validate Telegram channel
    log.info("Validating Telegram channel...")
    if not validate_channel():
        log.error("Channel is invalid — cannot continue. Check TELEGRAM_CHANNEL_ID in .env")
        log.error("Make sure the bot is added as an admin to the channel")
        sys.exit(1)

    # Step 5: Get the first row from Google Sheets
    log.info("Checking Google Sheet for rows to post...")
    from sheets_reader import get_first_row

    row = get_first_row()

    if row is None:
        log.success("No rows remaining — pipeline complete!")
        log.section("TELEGRAM PIPELINE — RUN END")
        sys.exit(0)

    # Step 6: Log the row data we found
    log.info(f"Row {row['row_index']} will be posted: {row['link']}")

    # Step 7: Build the caption/message from optional sheet fields:
    #   G (coupon) or B (code) → "use promo code <X> and save"
    # The final line is always "View deal". The ENTIRE caption (all lines)
    # is wrapped in a single <a href=...> so every line is tappable — more
    # clickable real estate than just a "View deal" link.
    caption_lines = []
    promo_code = row.get("coupon") or row.get("code") or ""
    if promo_code:
        caption_lines.append(
            f"use promo code {html.escape(promo_code)} and save"
        )
    caption_lines.append("View deal")
    safe_link = html.escape(row["link"], quote=True)
    caption = f'<a href="{safe_link}">' + "\n".join(caption_lines) + "</a>"

    # Step 8: Send to Telegram. If the row has an image URL (column D), post
    # the photo with the caption. Otherwise send the caption as a text message.
    try:
        if row.get("image_url"):
            log.info("Sending photo with caption to Telegram channel...")
            send_photo(row["image_url"], caption)
        else:
            log.info("Sending text message to Telegram channel...")
            send_message(caption)
    except Exception as e:
        log.error(f"Failed to send message: {e}")
        log.error("Row was NOT marked as posted — will retry on next run")
        sys.exit(1)

    # Step 8: Archive the posted row (append to Sheet2, then delete from main).
    # Sheet2 is the permanent record of everything we've posted — the
    # guru_amz_pipeline's finalize.py reads col A from Sheet2 to skip
    # deals that have already been posted in a previous day's batch.
    log.info("Archiving posted row to Sheet2...")
    from sheets_tracker import archive_posted_row, get_sheet_stats

    success = archive_posted_row(row["row_index"], row["raw_row"])
    if not success:
        log.error("=" * 50)
        log.error("WARNING: MESSAGE WAS SENT BUT ROW WAS NOT CLEANLY ARCHIVED!")
        log.error(f"Check row {row['row_index']} and Sheet2 manually")
        log.error("=" * 50)

    # Step 9: Print summary stats
    stats = get_sheet_stats()
    log.success(f"Run complete. Remaining rows: {stats['remaining']}")

    # Done!
    log.section("TELEGRAM PIPELINE — RUN END")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        # Let sys.exit() calls pass through normally
        raise
    except Exception as e:
        # Catch any unexpected errors and print full traceback in red
        log.error(f"UNEXPECTED ERROR: {e}")
        log.error(traceback.format_exc())
        sys.exit(1)
