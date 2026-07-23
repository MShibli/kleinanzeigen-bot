import os
import logging

class Settings:
    TOKEN = os.environ.get("TOKEN") or "Your_secret_key"
    WHITELIST_TOKEN = os.environ.get("WHITELIST_TOKEN") or "Your_secret_key"
    TOKEN_P2 = os.environ.get("TOKEN_P2") or "Your_secret_key_P2"
    CHAT_ID = os.environ.get("CHAT_ID") or "Your_chat_id"
    CHAT_ID_P2 = os.environ.get("CHAT_ID_P2") or "Your_chat_id2"

    # Prüft, ob ein persistentes Verzeichnis definiert wurde (z.B. /app/data auf Railway)
    # Falls nicht, wird das Home-Verzeichnis (lokal) als Fallback genutzt.
    PERSISTENT_DIR = os.environ.get("CACHE_DIR") or os.path.expanduser("~")
    os.makedirs(PERSISTENT_DIR, exist_ok=True)
    # Die Datenbankdatei wird nun im persistenten Verzeichnis abgelegt
    FILE_LOCATION = os.path.join(PERSISTENT_DIR, "ebayklein.db")
    
    TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&parse_mode=HTML&"
    TELEGRAM_API_WHITELIST_URL = f"https://api.telegram.org/bot{WHITELIST_TOKEN}/sendMessage?chat_id={CHAT_ID}&parse_mode=HTML&"
    TELEGRAM_API_URL_P2 = f"https://api.telegram.org/bot{TOKEN_P2}/sendMessage?chat_id={CHAT_ID_P2}&parse_mode=HTML&"
    LOGGING = os.environ.get("LOGGING") or logging.ERROR
    URL_BASE = "https://www.kleinanzeigen.de"
    OPEN_API_KEY = os.environ.get("OPEN_API_KEY") or "Your_OpenAI_Key"

    # ZenRows (umgeht eBays mehrschichtige Bot-Abwehr bei der Preisrecherche).
    # Bewusst KEIN Platzhalter-Fallback: leerer String = "kein Key konfiguriert"
    # wird in ebay_market.py ausgewertet, um Live-Abfragen zu überspringen.
    ZENROWS_API_KEY = os.environ.get("ZENROWS_API_KEY") or ""
    ZENROWS_JS_RENDER = (os.environ.get("ZENROWS_JS_RENDER") or "true").lower() != "false"
    ZENROWS_PREMIUM_PROXY = (os.environ.get("ZENROWS_PREMIUM_PROXY") or "true").lower() != "false"
    ZENROWS_PROXY_COUNTRY = os.environ.get("ZENROWS_PROXY_COUNTRY") or "de"
    # CSS-Selektor, auf den ZenRows vor der Rückgabe wartet - verhindert, dass die
    # Seite abgegriffen wird, bevor die echten Suchergebnisse geladen sind (genau
    # das Problem, das wir mit ScraperAPI hatten). "s-item" ist eBays langjährige
    # Ergebnis-Listen-Klasse; falls eBay das Markup ändert, hier anpassen.
    ZENROWS_WAIT_FOR = os.environ.get("ZENROWS_WAIT_FOR") or ".s-item"
    # Testmodus: ZenRows wird aufgerufen und die Preise fürs Scoring genutzt, aber
    # NICHT in ebay_price_cache.json geschrieben. Auf "true" setzen, solange du dir
    # noch nicht sicher bist, dass der Scraper zuverlässig korrekte Preise liefert -
    # so bleiben die bestehenden Cache-Werte unangetastet.
    EBAY_PRICE_CACHE_READONLY = (os.environ.get("EBAY_PRICE_CACHE_READONLY") or "false").lower() == "true"

settings = Settings()
