"""
sheets_reader.py — Reads the first row from a Google Sheet.

Uses gspread + google-auth service account credentials to connect to
the Google Sheet specified in config. Returns the first row (row 1)
which is the next item to post. After posting, the row will be deleted
by sheets_tracker so the next row becomes row 1.

Imports: gspread, google.oauth2.service_account, config, logger
Exports: get_first_row()
"""

import gspread
from google.oauth2.service_account import Credentials
from config import config
from logger import get_logger

log = get_logger("sheets_reader")

# Google API scopes needed for reading spreadsheets
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _get_client():
    """Authenticate with Google and return a gspread client."""
    log.info(f"Authenticating with service account: {config.GOOGLE_CREDENTIALS_JSON_PATH}")
    try:
        credentials = Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_JSON_PATH, scopes=SCOPES
        )
        client = gspread.authorize(credentials)
        log.success("Google Sheets authentication successful")
        return client
    except Exception as e:
        log.error(f"Google Sheets authentication FAILED: {e}")
        raise


def get_first_row():
    """
    Read and return the first row from the Google Sheet.

    Returns a dict with keys: row_index, link, image_url, raw_row
    image_url is pulled from column D (if present and non-empty), else None.
    Returns None if the sheet is empty or the link cell is empty.
    row_index is always 1 (the first row).
    """
    # Connect to Google Sheets
    client = _get_client()

    # Open the spreadsheet by ID and select the correct tab
    log.info(f"Opening sheet ID: {config.GOOGLE_SHEET_ID}")
    log.info(f"Selecting tab: {config.GOOGLE_SHEET_NAME}")
    try:
        spreadsheet = client.open_by_key(config.GOOGLE_SHEET_ID)
        worksheet = spreadsheet.worksheet(config.GOOGLE_SHEET_NAME)
        log.success(f"Opened worksheet: {worksheet.title}")
    except Exception as e:
        log.error(f"Failed to open spreadsheet: {e}")
        raise

    # Get all values from the sheet
    log.info("Fetching all rows from the sheet...")
    try:
        all_rows = worksheet.get_all_values()
    except Exception as e:
        log.error(f"Failed to fetch rows: {e}")
        raise

    log.info(f"Total rows found: {len(all_rows)}")

    # Convert link column letter to 0-based index (A=0, B=1, etc.)
    link_col_index = ord(config.GOOGLE_SHEET_LINK_COLUMN.upper()) - ord("A")
    log.debug(f"Link column '{config.GOOGLE_SHEET_LINK_COLUMN}' = index {link_col_index}")

    # Image URL lives in column D (hardcoded). 0-based index 3.
    image_col_index = 3

    # Check if the sheet has any rows
    if len(all_rows) == 0:
        log.info("Sheet is empty — no rows to post")
        return None

    # Get the first row
    first_row = all_rows[0]

    # Make sure the row has enough columns for the link column
    if len(first_row) <= link_col_index:
        log.info("First row does not have enough columns — skipping")
        return None

    # Get the link value from the first row
    link_value = first_row[link_col_index].strip()

    # Skip if the link cell is empty
    if not link_value:
        log.info("First row has an empty link column — skipping")
        return None

    # Pull the optional image URL from column D, if the row is wide enough
    # and the cell is non-empty. Otherwise image_url stays None and main.py
    # falls back to the plain-text sendMessage path.
    image_url = None
    if len(first_row) > image_col_index:
        candidate = first_row[image_col_index].strip()
        if candidate:
            image_url = candidate
            log.info(f"Image URL found in column D: {image_url}")
        else:
            log.info("Column D is empty — will post text only")
    else:
        log.info("Row has no column D — will post text only")

    # Return the first row data
    log.success(f"First row ready to post: {link_value}")
    return {
        "row_index": 1,
        "link": link_value,
        "image_url": image_url,
        "raw_row": first_row,
    }
