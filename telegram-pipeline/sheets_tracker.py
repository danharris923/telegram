"""
sheets_tracker.py — Archives posted rows from the main Google Sheet to Sheet2.

After a row is successfully posted to Telegram, this module:
  1. Appends the row's values to "Sheet2" (the archive tab — auto-created
     if missing). Sheet2 becomes the permanent record of everything we've
     ever posted, used by the producer pipeline to dedupe new scrapes.
  2. Deletes the row from the main sheet so the next row becomes row 1.

Also exposes get_sheet_stats() for end-of-run summary logging.

Imports: gspread, google.oauth2.service_account, config, logger, time
Exports: archive_posted_row(), get_sheet_stats()
"""

import time
import gspread
from google.oauth2.service_account import Credentials
from config import config
from logger import get_logger

log = get_logger("sheets_tracker")

# Google API scopes needed for reading and writing spreadsheets.
# "spreadsheets" scope covers adding worksheets within an existing sheet,
# so no Drive write scope is required.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Name of the archive tab. Google Sheets' default name for a new second
# tab is "Sheet2" — we hardcode that and auto-create the tab if it
# doesn't exist yet (first run after this change).
ARCHIVE_SHEET_NAME = "Sheet2"


def _get_spreadsheet():
    """Authenticate and return the full Spreadsheet object (not a worksheet)."""
    log.info("Authenticating with Google Sheets for tracking...")
    try:
        credentials = Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_JSON_PATH, scopes=SCOPES
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(config.GOOGLE_SHEET_ID)
        log.success("Connected to spreadsheet for tracking")
        return spreadsheet
    except Exception as e:
        log.error(f"Failed to connect for tracking: {e}")
        raise


def _get_main_worksheet(spreadsheet):
    """Return the main (source) worksheet — the one we read and delete from."""
    return spreadsheet.worksheet(config.GOOGLE_SHEET_NAME)


def _get_or_create_archive_worksheet(spreadsheet):
    """
    Return the archive worksheet (Sheet2). Creates it if it doesn't exist.

    The archive is a flat log — no header row is written automatically.
    If you want headers, add them manually to Sheet2 in the UI.
    """
    try:
        ws = spreadsheet.worksheet(ARCHIVE_SHEET_NAME)
        log.info(f"Found existing archive tab '{ARCHIVE_SHEET_NAME}'")
        return ws
    except gspread.exceptions.WorksheetNotFound:
        log.info(f"Archive tab '{ARCHIVE_SHEET_NAME}' not found — creating it")
        # 1000 rows / 10 cols is plenty; sheet will auto-grow as needed.
        ws = spreadsheet.add_worksheet(title=ARCHIVE_SHEET_NAME, rows=1000, cols=10)
        log.success(f"Created archive tab '{ARCHIVE_SHEET_NAME}'")
        return ws


def archive_posted_row(row_index, row_data, max_retries=1):
    """
    Move a posted row from the main sheet to the archive tab (Sheet2).

    Steps, in order:
      1. Append `row_data` (the full raw row, A..last-non-empty-col) to Sheet2.
      2. Only if the append succeeds, delete row `row_index` from the main sheet.

    This ordering is intentional: if the append fails, the row stays in the
    main sheet and will be re-posted next run (safer than losing the record).
    If the delete fails after a successful append, the row will be archived
    AND reposted next run — worse than a duplicate post, so we retry the
    delete once with a 3-second backoff.

    Returns True on full success, False if either step ultimately failed.
    """
    log.info(f"Archiving row {row_index} — appending to '{ARCHIVE_SHEET_NAME}'...")

    # Step 1: append to archive. One retry on failure.
    for attempt in range(2):
        try:
            spreadsheet = _get_spreadsheet()
            archive_ws = _get_or_create_archive_worksheet(spreadsheet)
            # row_data is the raw row from gspread — a list of strings,
            # possibly trimmed of trailing empties. append_row handles this.
            archive_ws.append_row(row_data, value_input_option="RAW")
            log.success(f"Row appended to '{ARCHIVE_SHEET_NAME}'")
            break
        except Exception as e:
            if attempt == 0:
                log.warning(f"Archive append failed on attempt 1: {e}")
                log.warning("Retrying in 3 seconds...")
                time.sleep(3)
            else:
                log.error(f"Archive append failed on attempt 2: {e}")
                log.error(f"FAILED to archive row {row_index} — NOT deleting from main sheet")
                return False

    # Step 2: delete from main sheet. One retry on failure.
    log.info(f"Deleting row {row_index} from main sheet...")
    for attempt in range(2):
        try:
            # Re-fetch the spreadsheet/worksheet — the append above may have
            # taken a few seconds and we want a fresh handle.
            spreadsheet = _get_spreadsheet()
            main_ws = _get_main_worksheet(spreadsheet)
            main_ws.delete_rows(row_index)
            log.success(f"Row {row_index} deleted from main sheet")
            return True
        except Exception as e:
            if attempt == 0:
                log.warning(f"Delete failed on attempt 1: {e}")
                log.warning("Retrying in 3 seconds...")
                time.sleep(3)
            else:
                log.error(f"Delete failed on attempt 2: {e}")
                log.error(f"Row {row_index} was archived but NOT deleted — will repost next run")
                return False

    return False


def get_sheet_stats():
    """
    Return a dict with the total number of rows remaining in the main sheet.

    Used by main.py to print a summary at the end of each run.
    """
    log.info("Calculating sheet statistics...")
    try:
        spreadsheet = _get_spreadsheet()
        worksheet = _get_main_worksheet(spreadsheet)
        all_rows = worksheet.get_all_values()

        # Column index for the link column
        link_col_index = ord(config.GOOGLE_SHEET_LINK_COLUMN.upper()) - ord("A")

        # Count rows that have a non-empty link
        total = 0
        for row in all_rows:
            if len(row) > link_col_index and row[link_col_index].strip():
                total += 1

        log.info(f"Stats — Remaining rows: {total}")

        return {
            "remaining": total,
        }

    except Exception as e:
        log.error(f"Failed to get sheet stats: {e}")
        return {"remaining": 0}
