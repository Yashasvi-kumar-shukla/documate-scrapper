import json
import os
import re
import sys
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

OPERATOR_UPI = {
    "Jio": "jio@axisbank",
    "Airtel": "airtel@axisbank",
    "Vi": "vi@axisbank",
    "BSNL": "bsnl@sbi",
}

# Corrected live Gadgets360 URLs
PLAN_URLS = {
    "Jio": "https://www.gadgets360.com/mobile-recharge-plans/jio-prepaid",
    "Airtel": "https://www.gadgets360.com/mobile-recharge-plans/airtel-prepaid",
    "Vi": "https://www.gadgets360.com/mobile-recharge-plans/vi-prepaid",
    "BSNL": "https://www.gadgets360.com/mobile-recharge-plans/bsnl-prepaid",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
}

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "").strip()


def fetch_html(url: str) -> str:
    # 1. Try ScraperAPI proxy if secret key is configured
    if SCRAPER_API_KEY:
        try:
            proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={quote_plus(url)}"
            resp = requests.get(proxy_url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 5000:
                print(f"  [ScraperAPI] Fetched {len(resp.content)} bytes")
                return resp.content.decode("utf-8", errors="ignore")
            print(f"  [ScraperAPI] Status {resp.status_code}, falling back...")
        except Exception as e:
            print(f"  [ScraperAPI] Error: {e}, falling back...")

    # 2. Try cloudscraper directly
    if cloudscraper is not None:
        try:
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            resp = scraper.get(url, headers=HEADERS, timeout=25)
            if resp.status_code == 200 and len(resp.content) > 5000:
                print(f"  [Cloudscraper] Fetched {len(resp.content)} bytes")
                return resp.content.decode("utf-8", errors="ignore")
            print(f"  [Cloudscraper] Status {resp.status_code}")
        except Exception as e:
            print(f"  [Cloudscraper] Error: {e}")

    # 3. Standard requests fallback
    resp = requests.get(url, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    print(f"  [Requests] Fetched {len(resp.content)} bytes")
    return resp.content.decode("utf-8", errors="ignore")


def parse_validity_days(text: str) -> int | None:
    # Matches "28 Days", "28.0", "for 28.0 Pack", or "Calendar Month"
    days_match = re.search(r"\b([0-9]{1,3})(?:\.0)?\s*Days?\b", text, re.IGNORECASE)
    if days_match:
        return int(days_match.group(1))

    decimal_pack = re.search(r"\bfor\s+([0-9]{1,3})\.0\s*Pack\b", text, re.IGNORECASE)
    if decimal_pack:
        return int(decimal_pack.group(1))

    standalone_decimal = re.search(r"\b([0-9]{1,3})\.0\b", text)
    if standalone_decimal:
        return int(standalone_decimal.group(1))

    if "calendar month" in text.lower() or "1 month" in text.lower():
        return 30

    return None


def scrape_operator_plans(operator: str, url: str) -> list[dict]:
    print(f"Scraping {operator} from {url}...")
    try:
        html = fetch_html(url)
        # Normalize any mangled Rupee symbols or HTML entities
        html = html.replace("â‚¹", "₹").replace("&#8377;", "₹")
        soup = BeautifulSoup(html, "lxml")

        plans = []
        seen = set()

        for block in soup.find_all(["tr", "div", "li"]):
            text = " ".join(block.get_text(" ", strip=True).split())
            if len(text) > 260 or ("₹" not in text and "Rs" not in text):
                continue

            price_match = re.search(r"(?:₹|Rs\.?)\s*([0-9,]{1,5})\b", text, re.IGNORECASE)
            if not price_match:
                continue

            price = int(price_match.group(1).replace(",", ""))
            days = parse_validity_days(text)
            if not days:
                continue

            if price < 10 or price > 5000 or days < 1 or days > 365:
                continue

            key = (price, days)
            if key in seen:
                continue
            seen.add(key)

            data_match = re.search(
                r"\b([0-9.]+\s*GB(?:\s*/\s*Day)?|Unlimited\s*Data)\b",
                text,
                re.IGNORECASE,
            )
            benefit = data_match.group(1).upper().replace("DAY", "Day") if data_match else "Voice + Data Pack"

            plans.append({
                "operatorName": operator,
                "name": f"{benefit} ({days} Days)",
                "price": price,
                "days": days,
                "upiId": OPERATOR_UPI[operator],
            })

        plans.sort(key=lambda x: x["price"])
        print(f"  -> Found {len(plans)} live plans for {operator}")
        return plans
    except Exception as e:
        print(f"  -> Failed to scrape {operator}: {e}")
        return []


def main():
    all_plans = {}
    total_count = 0

    for operator, url in PLAN_URLS.items():
        scraped = scrape_operator_plans(operator, url)
        all_plans[operator] = scraped
        total_count += len(scraped)

    if total_count == 0:
        print("Error: 0 plans extracted across all operators.")
        sys.exit(1)

    with open("plans.json", "w", encoding="utf-8") as f:
        json.dump(all_plans, f, indent=2, ensure_ascii=False)

    print(f"Successfully wrote {total_count} live plans to plans.json")


if __name__ == "__main__":
    main()