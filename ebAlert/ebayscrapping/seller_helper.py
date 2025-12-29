import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
}

DATE_PATTERN = re.compile(r"Aktiv seit\s+(\d{2}\.\d{2}\.\d{4})")


def fetch_seller_info(ad_url: str) -> dict | None:
    """
    Lädt die Anzeige-Seite und extrahiert:
    - Verkäufername
    - Eintrittsdatum
    - Alter des Accounts in Tagen
    """

    try:
        r = requests.get(ad_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # ----------------------------
        # Verkäufername
        # ----------------------------
        seller_name = None
        seller_tag = soup.select_one(
            ".text-body-regular-strong.text-force-linebreak.userprofile-vip a"
        )

        if seller_tag:
            seller_name = seller_tag.get_text(strip=True)

        # ----------------------------
        # Aktiv seit Datum
        # ----------------------------
        active_since = None

        for span in soup.select(".userprofile-vip-details-text"):
            text = span.get_text(strip=True)
            match = DATE_PATTERN.search(text)
            if match:
                active_since = datetime.strptime(match.group(1), "%d.%m.%Y")
                break

        if not seller_name or not active_since:
            return None

        seller_age_days = (datetime.now() - active_since).days

        return {
            "seller_name": seller_name,
            "active_since": active_since,
            "seller_age_days": seller_age_days
        }

    except Exception as e:
        print("Seller fetch error:", e)
        return None
