"""
Phase 3: Finalize.

Filter + sort the sheet in place:
  - drop rows whose col A (guru URL) already appears in Sheet2 (the
    telegram-pipeline's archive of everything it has ever posted)
  - keep rows that have a code (col B or col H) OR a discount >= 30%
  - sort: code deals first (by discount desc), then non-code rows (by discount desc)
  - rows below the kept set are cleared

Sheet2 dedupe: the telegram-pipeline appends every successfully-posted
row to "Sheet2" before deleting it from the main sheet. We read col A
of Sheet2 here as a set and skip any incoming row whose guru URL is
already in that set. If Sheet2 doesn't exist yet (first run before
anything has been posted), we proceed with an empty dedupe set.
"""
import os
import re

import gspread
from google.oauth2.service_account import Credentials
from colorama import Fore, init

init(autoreset=True)

SHEET_ID = "1I4cZ-V6uA7MrIj7t-mlH8-9JeSsD7eIg0v252tbz_Jc"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_HERE = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(_HERE, "google_service_account.json")

# Name of the archive tab written by telegram-pipeline/sheets_tracker.py.
# Col A of this tab holds the guru URL of every deal we've ever posted.
ARCHIVE_SHEET_NAME = "Sheet2"

DATA_START_ROW = 2
NUM_COLS = 8  # A..H
DISCOUNT_COL = 5  # 0-indexed F
CODE_COLS = (1, 7)  # 0-indexed B and H
MIN_DISCOUNT = 30  # keep rows with discount >= this percent


def parse_discount(val):
    if not val:
        return 0
    m = re.search(r"(\d+)\s*%", val)
    return int(m.group(1)) if m else 0


def pad(row, n):
    return row + [""] * (n - len(row))


def load_posted_urls(spreadsheet):
    """
    Return a set of guru URLs (col A) that have already been posted,
    i.e. everything in Sheet2 col A. If Sheet2 doesn't exist, return
    an empty set.
    """
    try:
        archive = spreadsheet.worksheet(ARCHIVE_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        print(Fore.YELLOW + f"[!] '{ARCHIVE_SHEET_NAME}' not found — no posted history")
        return set()

    archive_rows = archive.get_all_values()
    posted = {r[0].strip() for r in archive_rows if r and r[0].strip()}
    print(Fore.CYAN + f"[*] {len(posted)} previously-posted URLs loaded from '{ARCHIVE_SHEET_NAME}'")
    return posted


def main():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(SHEET_ID)
    ws = spreadsheet.sheet1

    # Load the set of already-posted guru URLs from Sheet2 for dedupe.
    posted_urls = load_posted_urls(spreadsheet)

    all_rows = ws.get_all_values()
    if len(all_rows) < DATA_START_ROW:
        print(Fore.YELLOW + "[!] Nothing to finalize")
        return

    data = [pad(r, NUM_COLS)[:NUM_COLS] for r in all_rows[DATA_START_ROW - 1:]]
    data = [r for r in data if r[0].strip()]
    total_before = len(data)

    # Drop rows whose guru URL (col A) was already posted in a prior run.
    # Done before the code/discount filter so the "dropped as duplicate"
    # count is easy to read in the logs.
    deduped = [r for r in data if r[0].strip() not in posted_urls]
    dropped_as_dupes = total_before - len(deduped)
    if dropped_as_dupes:
        print(Fore.CYAN + f"[*] Dropped {dropped_as_dupes} rows already in '{ARCHIVE_SHEET_NAME}'")
    data = deduped

    kept = []
    for row in data:
        has_code = any(row[c].strip() for c in CODE_COLS)
        disc = parse_discount(row[DISCOUNT_COL])
        if has_code or disc >= MIN_DISCOUNT:
            kept.append((has_code, disc, row))

    # Code deals first, then non-code. Within each group, discount desc.
    kept.sort(key=lambda t: (0 if t[0] else 1, -t[1]))
    sorted_rows = [t[2] for t in kept]

    print(Fore.CYAN + f"[*] {total_before} rows in, {len(sorted_rows)} kept "
          f"({sum(1 for t in kept if t[0])} code deals, "
          f"{sum(1 for t in kept if not t[0])} discount-only)")

    end_col = chr(ord("A") + NUM_COLS - 1)  # H
    data_end = len(all_rows)

    if sorted_rows:
        last_row = DATA_START_ROW + len(sorted_rows) - 1
        ws.update(f"A{DATA_START_ROW}:{end_col}{last_row}", sorted_rows, value_input_option="RAW")
        print(Fore.GREEN + f"[OK] Wrote {len(sorted_rows)} sorted rows")
        clear_start = last_row + 1
    else:
        clear_start = DATA_START_ROW

    if clear_start <= data_end:
        ws.batch_clear([f"A{clear_start}:{end_col}{data_end}"])
        print(Fore.GREEN + f"[OK] Cleared rows {clear_start}-{data_end}")


if __name__ == "__main__":
    main()
