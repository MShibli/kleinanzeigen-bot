import requests
from bs4 import BeautifulSoup
import statistics
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def extract_prices(html):
    soup = BeautifulSoup(html, "lxml")
    prices = []

    for price_tag in soup.select(".s-item__price"):
        text = price_tag.get_text()
        match = re.search(r"(\d+[.,]?\d*)", text)
        if match:
            price = float(match.group(1).replace(",", "."))
            if 20 < price < 5000:  # Filter Müll
                prices.append(price)

    return prices


def get_market_price(search_term: str) -> float | None:
    url = (
        "https://www.ebay.de/sch/i.html"
        f"?_nkw={search_term.replace(' ', '+')}"
        "&LH_Sold=1&LH_Complete=1"
    )

    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return None

    prices = extract_prices(resp.text)

    if len(prices) < 5:
        return None

    return round(statistics.median(prices), 2)
