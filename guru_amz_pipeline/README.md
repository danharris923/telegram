# guru_amz_pipeline

Standalone two-phase scraper. Designed to be lifted out of BreakfastScripts into its own project.

## Sheet layout

Target sheet: `1I4cZ-V6uA7MrIj7t-mlH8-9JeSsD7eIg0v252tbz_Jc`

| Col | Written by     | Meaning                    |
|-----|----------------|----------------------------|
| A   | (manual input) | SavingsGuru URL            |
| B   | guru_scrape.py | Promo code(s)              |
| C   | guru_scrape.py | Resolved Amazon product URL|
| D   | amz_scrape.py  | Image URL (`_AC_SL1500_`)  |
| E   | amz_scrape.py  | Price                      |
| F   | amz_scrape.py  | Discount %                 |
| G   | amz_scrape.py  | Coupon value               |
| H   | amz_scrape.py  | Extra promo codes          |

Data starts on row 2 (row 1 = header).

## Run

```
python guru_scrape.py     # Phase 1 — guru pages → B, C
python amz_scrape.py      # Phase 2 — Amazon pages → D-H
```

Both are idempotent: already-populated rows are skipped.

## Dependencies

```
pip install gspread google-auth requests beautifulsoup4 playwright colorama
python -m playwright install chrome
```

## Required side files

Place alongside these scripts (or in the parent directory):

- `google_service_account.json` — Google service account with Sheets + Drive scopes, shared on the target sheet.
- `.amazon_chrome_profile/` — Playwright persistent Chrome profile. First run headful, sign in to amazon.ca, close; cookies persist for future runs.

The scripts look for both files next to themselves first, then one directory up — so they keep working both in-place inside BreakfastScripts and after being moved to a fresh project directory.

## Moving to a new project

1. Copy the `guru_amz_pipeline/` folder.
2. Copy `google_service_account.json` into the folder (or keep it one level up).
3. Copy `.amazon_chrome_profile/` into the folder (or re-login once).
4. `pip install ...` as above.
