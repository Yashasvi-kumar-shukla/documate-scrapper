import json
import re
import sys
import requests
from bs4 import BeautifulSoup

OPERATOR_UPI = {
    "Jio": "jio@axisbank",
    "Airtel": "airtel@axisbank",
    "Vi": "vi@axisbank",
    "BSNL": "bsnl@sbi",
}

PLAN_URLS = {
    "Jio": "https://www.gadgets360.com/mobile-recharge-plans/reliance-jio-prepaid",
    "Airtel": "https://www.gadgets360.com/mobile-recharge-plans/airtel-prepaid",
    "Vi": "https://www.gadgets360.com/mobile-recharge-plans/vodafone-idea-prepaid",
    "BSNL": "https://www.gadgets360.com/mobile-recharge-plans/bsnl-prepaid",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    )
}


def scrape_operator_plans(operator: str, url: str) -> list[dict]:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    plans = []
    seen = set()

    for block in soup.find_all(["tr", "div", "li"]):
        text = " ".join(block.get_text(" ", strip=True).split())
        if len(text) > 240 or "₹" not in text:
            continue

        price_match = re.search(r"₹\s*([0-9,]{2,4})\b", text)
        days_match = re.search(r"\b([0-9]{1,3})\s*Days?\b", text, re.IGNORECASE)
        data_match = re.search(
            r"\b([0-9.]+\s*GB(?:\s*/\s*Day)?|Unlimited\s*Data)\b",
            text,
            re.IGNORECASE,
        )

        if not price_match or not days_match:
            continue

        price = int(price_match.group(1).replace(",", ""))
        days = int(days_match.group(1))

        if price < 10 or price > 5000 or days < 1 or days > 365:
            continue

        key = (price, days)
        if key in seen:
            continue
        seen.add(key)

        benefit = data_match.group(1) if data_match else "Voice + Data Pack"
        plans.append({
            "operatorName": operator,
            "name": f"{benefit} ({days} Days)",
            "price": price,
            "days": days,
            "upiId": OPERATOR_UPI[operator],
        })

    plans.sort(key=lambda x: x["price"])
    return plans


def main():
    all_plans = {}
    total_count = 0

    for operator, url in PLAN_URLS.items():
        scraped = scrape_operator_plans(operator, url)
        all_plans[operator] = scraped
        total_count += len(scraped)
        print(f"Scraped {len(scraped)} live plans for {operator}")

    if total_count == 0:
        print("Error: No plans were scraped. Aborting to protect existing plans.json.")
        sys.exit(1)

    with open("plans.json", "w", encoding="utf-8") as f:
        json.dump(all_plans, f, indent=2, ensure_ascii=False)

    print(f"Successfully wrote {total_count} plans to plans.json")


if __name__ == "__main__":
    main()