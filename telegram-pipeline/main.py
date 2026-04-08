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

import sys
import uuid
import traceback
from logger import get_logger

log = get_logger("main")


def main():
    """Run the full Telegram posting pipeline."""

    # Step 1: Print the big start banner
    log.section("TELEGRAM PIPELINE — RUN START")

    # Generate a short run ID for tracking this specific execution
    run_id = str(uuid.uuid4())[:8]
    log.info(f"Run ID: {run_id}")

    # Step 2: Load and validate config (this happens on import)
    log.info("Loading configuration...")
    from config import config  # noqa: F401 — importing triggers validation
    log.success("Configuration loaded and validated")

    # Step 3: Validate Telegram bot token
    log.info("Validating Telegram bot...")
    from telegram_sender import validate_bot, validate_channel, send_message

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

    # Step 7: Send the message to Telegram
    log.info("Sending message to Telegram channel...")
    try:
        send_message(row["link"])
    except Exception as e:
        log.error(f"Failed to send message: {e}")
        log.error("Row was NOT marked as posted — will retry on next run")
        sys.exit(1)

    # Step 8: Delete the posted row from the sheet
    log.info("Deleting posted row from Google Sheet...")
    from sheets_tracker import delete_posted_row, get_sheet_stats

    success = delete_posted_row(row["row_index"])
    if not success:
        log.error("=" * 50)
        log.error("WARNING: MESSAGE WAS SENT BUT ROW WAS NOT DELETED!")
        log.error(f"You must manually delete row {row['row_index']} from the sheet")
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
