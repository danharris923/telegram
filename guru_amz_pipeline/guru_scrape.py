"""
Phase 1: Guru page scraper.

Reads SavingsGuru URLs from column A, extracts promo code + Amazon link,
writes them to columns B and C.

Standalone — no dependency on sheet_utils.py.
"""
import os
import re
import sys
import time
import random
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

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

DATA_START_ROW = 2
MAX_WORKERS = 3
REQUEST_TIMEOUT = 15

PROMO_PATTERNS = [
    r"use\s+code\s+<[^>]+>([A-Z0-9]{6,12})<",
    r"use\s+code[:\s]+([A-Z0-9]{6,12})",
    r"\bcode[:\s]+([A-Z0-9]{6,12})\b",
    r"promo\s+code[:\s]+([A-Z0-9]{6,12})",
]


def random_headers():
    return {
        "User-Agent": (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{random.randint(120, 131)}.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def resolve_amazon_link(url):
    """Follow redirects (amzn.to shorteners) to get the full Amazon URL."""
    try:
        sep = "&" if "?" in url else "?"
        busted = f"{url}{sep}_={int(time.time())}&nocache={random.randint(1000, 9999)}"
        session = requests.Session()
        session.cookies.clear()
        resp = session.get(busted, timeout=REQUEST_TIMEOUT, allow_redirects=True, headers=random_headers())
        resolved = resp.url.split("?_=")[0].split("&_=")[0]
        session.close()
        return resolved
    except requests.RequestException:
        return url


def extract_from_guru(url):
    """Return (promo_code, amazon_link) for a single guru URL. Blank strings if not found."""
    try:
        sep = "&" if "?" in url else "?"
        busted = f"{url}{sep}_={int(time.time())}&nocache={random.randint(1000, 9999)}"
        resp = requests.get(busted, headers=random_headers(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(Fore.RED + f"[X] Fetch failed {url}: {e}")
        return "", ""

    soup = BeautifulSoup(resp.text, "html.parser")
    post_body = soup.select_one("div.entry-content")

    amazon_link = ""
    if post_body:
        for a in post_body.find_all("a", href=True):
            href = a["href"]
            if "amzn.to" in href or "amazon." in href:
                amazon_link = resolve_amazon_link(href)
                break

    body_html = str(post_body) if post_body else resp.text
    promo_codes = []
    for pat in PROMO_PATTERNS:
        for m in re.findall(pat, body_html, flags=re.IGNORECASE):
            code = m.upper()
            if code not in promo_codes:
                promo_codes.append(code)
    promo_code = ", ".join(promo_codes)

    return promo_code, amazon_link


def process_row(row_num, url, existing_b, existing_c):
    if existing_b and existing_c:
        print(Fore.BLUE + f"[=] Row {row_num}: already populated, skipping")
        return row_num, existing_b, existing_c
    code, amz = extract_from_guru(url)
    print(Fore.GREEN + f"[OK] Row {row_num}: code={code or '-'} amz={amz[:70] or '-'}")
    return row_num, code, amz


def main():
    print(Fore.CYAN + f"[*] Using creds: {CREDS_FILE}")
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(SHEET_ID).sheet1

    all_rows = ws.get_all_values()
    print(Fore.CYAN + f"[*] Sheet has {len(all_rows)} rows")

    tasks = []
    for idx, row in enumerate(all_rows, start=1):
        if idx < DATA_START_ROW:
            continue
        a = row[0].strip() if len(row) > 0 else ""
        b = row[1].strip() if len(row) > 1 else ""
        c = row[2].strip() if len(row) > 2 else ""
        if not a:
            continue
        tasks.append((idx, a, b, c))

    print(Fore.CYAN + f"[*] {len(tasks)} rows to process")

    results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(process_row, r, u, b, c): r for (r, u, b, c) in tasks}
        for fut in as_completed(futures):
            try:
                row_num, code, amz = fut.result()
                results[row_num] = (code, amz)
            except Exception as e:
                print(Fore.RED + f"[X] Worker error: {e}")

    if not results:
        print(Fore.YELLOW + "[!] No results to write")
        return

    updates = []
    for row_num in sorted(results):
        code, amz = results[row_num]
        updates.append({"range": f"B{row_num}:C{row_num}", "values": [[code, amz]]})

    ws.batch_update(updates, value_input_option="RAW")
    print(Fore.GREEN + f"[OK] Wrote {len(updates)} rows to sheet")


if __name__ == "__main__":
    main()
