"""
sheets_tracker.py — Deletes the first row from the Google Sheet after posting.

Uses gspread + google-auth service account credentials to delete the posted
row from the sheet. This way the next row automatically becomes row 1
for the next run. Also provides stats about how many rows remain.

Imports: gspread, google.oauth2.service_account, config, logger, time
Exports: delete_posted_row(), get_sheet_stats()
"""

import time
import gspread
from google.oauth2.service_account import Credentials
from config import config
from logger import get_logger

log = get_logger("sheets_tracker")

# Google API scopes needed for reading and writing spreadsheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _get_worksheet():
    """Authenticate and return the worksheet object."""
    log.info("Authenticating with Google Sheets for tracking...")
    try:
        credentials = Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_JSON_PATH, scopes=SCOPES
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(config.GOOGLE_SHEET_ID)
        worksheet = spreadsheet.worksheet(config.GOOGLE_SHEET_NAME)
        log.success("Connected to worksheet for tracking")
        return worksheet
    except Exception as e:
        log.error(f"Failed to connect for tracking: {e}")
        raise


def delete_posted_row(row_index):
    """
    Delete a row from the sheet after it has been successfully posted.

    Returns True on success, False on failure.
    Retries once after 3 seconds if the first attempt fails.
    """
    log.info(f"Deleting row {row_index} from the sheet...")

    # Try up to 2 times (initial attempt + 1 retry)
    for attempt in range(2):
        try:
            worksheet = _get_worksheet()

            # Delete the row from the sheet
            worksheet.delete_rows(row_index)
            log.success(f"Row {row_index} deleted successfully")
            return True

        except Exception as e:
            if attempt == 0:
                log.warning(f"Delete failed on attempt 1: {e}")
                log.warning("Retrying in 3 seconds...")
                time.sleep(3)
            else:
                log.error(f"Delete failed on attempt 2: {e}")
                log.error(f"FAILED to delete row {row_index}")
                return False

    return False


def get_sheet_stats():
    """
    Return a dict with the total number of rows remaining in the sheet.

    Used by main.py to print a summary at the end of each run.
    """
    log.info("Calculating sheet statistics...")
    try:
        worksheet = _get_worksheet()
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
