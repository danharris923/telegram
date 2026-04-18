"""
Phase 2: Amazon page scraper.

Reads Amazon URLs from column C, scrapes product details via logged-in Playwright
(persistent context from .amazon_chrome_profile). Runs N concurrent tabs under
one shared login. Writes to columns D-H:
  D = image URL (_AC_SL1500_)
  E = price
  F = discount
  G = coupons
  H = extra promo codes found on page

Standalone — no dependency on sheet_utils.py.
"""
import os
import re
import json
import asyncio
import random
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

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
USER_DATA_DIR = os.path.join(_HERE, ".amazon_chrome_profile")

DATA_START_ROW = 2
CONCURRENT_TABS = 3
PAGE_DELAY_MIN = 0.8
PAGE_DELAY_MAX = 2.0
FLUSH_EVERY = 20


def upscale_amazon_image_url(url):
    if not url or "images/I/" not in url:
        return url
    cleaned = re.sub(r"\._[^.]+_\.", "._AC_SL1500_.", url)
    if cleaned == url:
        cleaned = re.sub(r"\.(jpg|png|webp)", r"._AC_SL1500_.\1", url, flags=re.IGNORECASE)
    return cleaned


def fetch_image_via_requests(link):
    try:
        headers = {
            "User-Agent": (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{random.randint(120, 131)}.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-CA,en-US;q=0.9,en;q=0.8",
        }
        resp = requests.get(link, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        m = re.search(r"'colorImages'\s*:\s*\{\s*'initial'\s*:\s*(\[.+?\])\s*\}", html, re.DOTALL)
        if m:
            try:
                images = json.loads(m.group(1))
                for img in images:
                    hi = img.get("hiRes") or img.get("large")
                    if hi and "images/I/" in hi:
                        return upscale_amazon_image_url(hi)
            except (json.JSONDecodeError, TypeError):
                pass

        m = re.search(r'data-a-dynamic-image="([^"]+)"', html)
        if m:
            try:
                raw = m.group(1).replace("&quot;", '"')
                image_map = json.loads(raw)
                best = max(image_map, key=lambda u: max(image_map[u]))
                return upscale_amazon_image_url(best)
            except (json.JSONDecodeError, ValueError):
                pass

        soup = BeautifulSoup(html, "html.parser")
        landing = soup.find("img", id="landingImage")
        if landing:
            src = landing.get("data-old-hires") or landing.get("src", "")
            if src and "images/I/" in src and not src.startswith("data:"):
                return upscale_amazon_image_url(src)

        found = re.findall(r"https://m\.media-amazon\.com/images/I/[A-Za-z0-9_%+-]+\.(?:jpg|png)", html)
        if found:
            return upscale_amazon_image_url(found[0])
    except Exception:
        pass
    return ""


def extract_coupon(full_text):
    # "Coupon price" — keep the literal phrase in the output per user request.
    m = re.search(r"Coupon price[:\s]+\$?(\d+(?:\.\d+)?%?)", full_text, flags=re.IGNORECASE)
    if m:
        val = m.group(1)
        if val.endswith("%"):
            return f"coupon price {val}"
        return f"coupon price ${val}"

    patterns = [
        r"Coupon:\s+Apply\s+(\$\d+|\d+%)\s+coupon",
        r"Save\s+(\d+%)\s+at\s+checkout",
        r"Save\s+\$(\d+(?:\.\d+)?)\s+at\s+checkout",
        r"(\d+%)\s+off\s+coupon",
    ]
    for i, pat in enumerate(patterns):
        m = re.search(pat, full_text, flags=re.IGNORECASE)
        if m:
            val = m.group(1)
            if i == 2:
                return f"${val}"
            return val
    return ""


def extract_extra_codes(full_text):
    codes = []
    for m in re.finditer(r"([0-9]+%)\s*promo code[:\s]+([A-Z0-9]{6,12})", full_text, flags=re.IGNORECASE):
        codes.append(f"{m.group(1)} {m.group(2).upper()}")
    for m in re.finditer(r"\buse\s+code[:\s]+([A-Z0-9]{6,12})\b", full_text, flags=re.IGNORECASE):
        code = m.group(1).upper()
        if not any(code in c for c in codes):
            codes.append(code)
    return ", ".join(codes)


async def scrape_one(page, url, tab_id):
    image_url = fetch_image_via_requests(url)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)
    except Exception as e:
        print(Fore.RED + f"[Tab {tab_id}] goto failed: {e}")
        return image_url, "", "", "", ""

    if not image_url:
        try:
            img_el = page.locator("#landingImage").first
            if await img_el.is_visible(timeout=3000):
                dynamic = await img_el.get_attribute("data-a-dynamic-image")
                if dynamic:
                    try:
                        image_map = json.loads(dynamic.strip('"'))
                        best = max(image_map, key=lambda u: max(image_map[u]))
                        image_url = upscale_amazon_image_url(best)
                    except (json.JSONDecodeError, ValueError):
                        pass
                if not image_url:
                    src = await img_el.get_attribute("data-old-hires") or await img_el.get_attribute("src")
                    if src and "images/I/" in src and not src.startswith("data:"):
                        image_url = upscale_amazon_image_url(src)
        except Exception:
            pass

    price = ""
    try:
        whole_el = page.locator(".a-price-whole").first
        if await whole_el.is_visible(timeout=2000):
            whole = (await whole_el.inner_text()).strip().rstrip(".")
            frac_el = page.locator(".a-price-fraction").first
            frac = (await frac_el.inner_text()).strip() if await frac_el.is_visible() else "00"
            price = f"${whole}.{frac}"
    except Exception:
        pass

    discount = ""
    try:
        disc_el = page.locator(".savingsPercentage").first
        if await disc_el.is_visible(timeout=2000):
            discount = (await disc_el.inner_text()).strip()
    except Exception:
        pass

    try:
        full_text = await page.inner_text("body")
    except Exception:
        full_text = ""

    coupon = extract_coupon(full_text)
    extra_codes = extract_extra_codes(full_text)
    return image_url, price, discount, coupon, extra_codes


async def worker(tab_id, page, queue, results, lock):
    while True:
        try:
            row_num, url = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        print(Fore.YELLOW + f"[Tab {tab_id}] Row {row_num}: {url[:80]}")
        try:
            img, price, disc, coupon, extra = await scrape_one(page, url, tab_id)
            print(Fore.GREEN + f"[Tab {tab_id}] Row {row_num}: price={price} disc={disc} coupon={coupon} extra={extra}")
            async with lock:
                results.append((row_num, [img, price, disc, coupon, extra]))
        except Exception as e:
            print(Fore.RED + f"[Tab {tab_id}] Row {row_num} failed: {e}")
        await asyncio.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX))


def flush_updates(ws, results):
    if not results:
        return
    results.sort(key=lambda r: r[0])
    updates = [
        {"range": f"D{row}:H{row}", "values": [vals]}
        for (row, vals) in results
    ]
    ws.batch_update(updates, value_input_option="RAW")
    print(Fore.GREEN + f"[FLUSH] Wrote {len(updates)} rows")
    results.clear()


async def main():
    print(Fore.CYAN + f"[*] Creds: {CREDS_FILE}")
    print(Fore.CYAN + f"[*] Chrome profile: {USER_DATA_DIR}")
    print(Fore.CYAN + f"[*] Concurrent tabs: {CONCURRENT_TABS}")

    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(SHEET_ID).sheet1

    all_rows = ws.get_all_values()
    queue = asyncio.Queue()
    count = 0
    for idx, row in enumerate(all_rows, start=1):
        if idx < DATA_START_ROW:
            continue
        c = row[2].strip() if len(row) > 2 else ""
        d = row[3].strip() if len(row) > 3 else ""
        e = row[4].strip() if len(row) > 4 else ""
        if not c:
            continue
        if d and e:
            continue
        await queue.put((idx, c))
        count += 1

    print(Fore.CYAN + f"[*] {count} rows queued")
    if count == 0:
        return

    os.makedirs(USER_DATA_DIR, exist_ok=True)
    results = []
    lock = asyncio.Lock()
    processed_since_flush = [0]

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,
            channel="chrome",
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
            ],
        )
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )

        pages = []
        if context.pages:
            pages.append(context.pages[0])
        while len(pages) < CONCURRENT_TABS:
            pages.append(await context.new_page())

        async def worker_with_flush(tab_id, page):
            while True:
                try:
                    row_num, url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                print(Fore.YELLOW + f"[Tab {tab_id}] Row {row_num}: {url[:80]}")
                try:
                    img, price, disc, coupon, extra = await scrape_one(page, url, tab_id)
                    print(Fore.GREEN + f"[Tab {tab_id}] Row {row_num}: price={price} disc={disc} coupon={coupon}")
                    async with lock:
                        results.append((row_num, [img, price, disc, coupon, extra]))
                        processed_since_flush[0] += 1
                        if processed_since_flush[0] >= FLUSH_EVERY:
                            flush_updates(ws, results)
                            processed_since_flush[0] = 0
                except Exception as e:
                    print(Fore.RED + f"[Tab {tab_id}] Row {row_num} failed: {e}")
                await asyncio.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX))

        await asyncio.gather(*[worker_with_flush(i + 1, pg) for i, pg in enumerate(pages)])

        await context.close()

    async with lock:
        flush_updates(ws, results)


if __name__ == "__main__":
    asyncio.run(main())
