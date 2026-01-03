import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

HEADERS = {
   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36","User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
}

DATE_PATTERN = re.compile(r"(\d{2}\.\d{2}\.\d{4})")

def fetch_seller_info(ad_url: str) -> dict | None:
    """
    Lädt eine Detailseite der Anzeige und extrahiert:
    - seller_name
    - seller_type (COMMERCIAL oder PRIVATE)
    - active_since (datetime)
    - seller_age_days (Tage seit Aktivität)
    - description (vollständiger Anzeigentext)
    """

    try:
        response = requests.get(ad_url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # ===== Verkäufername =====
        seller_name = None
        seller_tag = soup.select_one(
            ".text-body-regular-strong.text-force-linebreak.userprofile-vip a"
        )

        if not seller_tag:
            seller_tag = soup.select_one(
               ".text-body-regular-strong text-force-linebreak userprofile-vip a"
            )
       
        if seller_tag:
            seller_name = seller_tag.get_text(strip=True)

        # ===== Verkäufer-Typ (COMMERCIAL oder PRIVATE) =====
        seller_type = "UNKNOWN"
        # In der Nähe der Verkäuferinfos steht meist z.B. "Privater Nutzer" oder "Gewerblicher Anbieter"
        seller_type_tag = soup.find(
            "span", class_="userprofile-vip-details-text"
        )
        if seller_type_tag:
            text = seller_type_tag.get_text(strip=True).lower()
            if "privat" in text:
                seller_type = "PRIVATE"
            elif "gewerblich" in text or "commercial" in text:
                seller_type = "COMMERCIAL"

        # ===== Aktiv seit Datum =====
        active_since = None
        for span in soup.select(".userprofile-vip-details-text"):
            match = DATE_PATTERN.search(span.get_text(strip=True))
            if match:
                try:
                    active_since = datetime.strptime(match.group(1), "%d.%m.%Y")
                    break
                except:
                    pass

        # ===== Anzeigenbeschreibung =====
        description = None
        desc_tag = soup.select_one("#viewad-description-text")
        if desc_tag:
            description = desc_tag.get_text(separator="\n", strip=True)

        if not seller_name:
            return None

        seller_age_days = None
        if active_since:
            seller_age_days = (datetime.now() - active_since).days

        return {
            "seller_name": seller_name,
            "seller_type": seller_type,
            "active_since": active_since,
            "seller_age_days": seller_age_days
            "description": description,
        }

    except Exception as e:
        print(f"fetch_seller_info error: {e}")
        return None
