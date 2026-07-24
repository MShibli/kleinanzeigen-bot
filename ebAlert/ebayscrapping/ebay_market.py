import statistics
import requests
import json
import os
import shutil
import time

from ebAlert.core.config import settings

EBAY_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

# --- CACHE KONFIGURATION ---
# Prüft, ob CACHE_DIR in den Umgebungsvariablen existiert (Railway)
# Falls nicht (lokal), wird der aktuelle Ordner (.) verwendet
CACHE_DIR = os.getenv("CACHE_DIR", ".")
CACHE_FILE = os.path.join(CACHE_DIR, "ebay_price_cache.json")

# Stelle sicher, dass das Verzeichnis existiert (verhindert Fehler beim ersten Start)
if CACHE_DIR != "." and not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
    
# 8 Wochen in Sekunden: 8 * 7 * 24 * 60 * 60
CACHE_EXPIRY = 4838400

CACHE_VERSION = "v6"  # v5: Umstellung von Scraping auf die offizielle eBay Browse API
# (Angebotspreis statt versuchtem Verkaufspreis, mit Zustandsfilter) - alte v4-Einträge
# sind ein anderes Preissignal und sollen nicht mehr als Fallback verwendet werden.

# In deinen Funktionen nutzt du jetzt einfach CACHE_FILE
def load_cache():
    """Gibt {} zurück, wenn (noch) keine Datei existiert, aber None, wenn die Datei
    existiert und trotzdem nicht lesbar ist (z.B. beschädigt). Diese Unterscheidung
    ist wichtig: {} darf gefahrlos später überschrieben werden, None NICHT - sonst
    würde eine kaputte/nicht lesbare Datei beim nächsten save_cache() versehentlich
    mit einem leeren Cache überschrieben und die gesamte Historie ginge verloren."""
    if not os.path.exists(CACHE_FILE):
        print("ebay scrap load_cache Error: Keine Cachedatei gefunden!")
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"❌ ebay scrap load_cache Error: Cache-Datei beschädigt/nicht lesbar ({e}) - Datei bleibt unangetastet!")
        return None

    # Einträge mit abweichender CACHE_VERSION aussortieren - die werden wegen des
    # Versions-Checks in get_ebay_median_price ohnehin nie wieder benutzt, würden aber
    # bei jedem Speichern unnötig mitgeschrieben (Datei wird über Zeit immer größer).
    filtered = {k: v for k, v in raw.items() if isinstance(v, dict) and v.get("version") == CACHE_VERSION}
    dropped = len(raw) - len(filtered)
    if dropped:
        print(f"🧹 {dropped} veraltete Cache-Einträge (andere Version) beim Laden verworfen.")
    return filtered

def save_cache(cache_data):
    # Backup der bisherigen Datei anlegen, bevor überschrieben wird - falls doch mal
    # ein fehlerhafter Wert reingeschrieben wird, lässt sich der vorherige Stand
    # wiederherstellen (einfach ebay_price_cache.json.bak zurückkopieren).
    if os.path.exists(CACHE_FILE):
        try:
            shutil.copyfile(CACHE_FILE, CACHE_FILE + ".bak")
        except Exception as e:
            print(f"⚠️ Konnte kein Cache-Backup anlegen: {e}")

    print(f"💾 Speichere ebay scrap-Cache ({len(cache_data)} Einträge) in: {CACHE_FILE}")
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=4)

def clear_cache():
    files = ["ebay_price_cache.json"]
    base = os.environ.get("CACHE_DIR", os.path.expanduser("~"))
    for f in files:
        path = os.path.join(base, f)
        if os.path.exists(path):
            os.remove(path)
            print(f"🗑️ Cache gelöscht: {path}")

# In-Memory-Cache für den OAuth-Token (Client-Credentials-Token ist ~2h gültig,
# es lohnt sich nicht, ihn bei jeder Preisabfrage neu zu holen).
_token_cache = {"access_token": None, "expires_at": 0}


def get_ebay_oauth_token() -> str:
    now = time.time()
    # 60s Sicherheitsmarge vor dem tatsächlichen Ablauf
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    res = requests.post(
        EBAY_OAUTH_URL,
        auth=(settings.EBAY_CLIENT_ID, settings.EBAY_CLIENT_SECRET),
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=15,
    )
    res.raise_for_status()
    payload = res.json()
    _token_cache["access_token"] = payload["access_token"]
    _token_cache["expires_at"] = now + payload["expires_in"]
    return _token_cache["access_token"]


def search_ebay_listings(query: str) -> list:
    """Liefert aktive eBay-Angebote (Buy-it-now-Angebotspreise, keine Verkaufspreise -
    die Marketplace Insights API für echte Sold-Preise ist bei eBay separat beantragt)."""
    token = get_ebay_oauth_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": settings.EBAY_MARKETPLACE_ID,
    }
    params = {"q": query, "limit": 50}
    if settings.EBAY_CONDITION_IDS:
        params["filter"] = f"conditionIds:{{{settings.EBAY_CONDITION_IDS}}}"

    res = requests.get(
        EBAY_BROWSE_SEARCH_URL,
        headers=headers,
        params=params,
        timeout=20,
    )
    if res.status_code != 200:
        raise RuntimeError(f"eBay Browse API Status {res.status_code}: {res.text[:300]}")
    return res.json().get("itemSummaries", [])


def get_ebay_median_price(query: str, offer_price: float):
    # 1. Cache laden und prüfen
    cache = load_cache()
    # Wenn die Datei beschädigt war (None statt {}), arbeiten wir für diesen Lauf
    # mit einem leeren Dict weiter, merken uns aber, dass NICHT gespeichert werden
    # darf - sonst würden wir die (potenziell noch reparierbare) Datei überschreiben.
    cache_is_writable = cache is not None
    if cache is None:
        cache = {}
    current_time = time.time()

    # Normalisiere die Query für den Cache-Key (Kleinschreibung, ohne unnötige Leerzeichen)
    cache_key = query.lower().strip()

    cached_entry = cache.get(cache_key)
    has_usable_cache = (
        cached_entry is not None
        and cached_entry.get('version') == CACHE_VERSION
        and cached_entry.get('price', 0) > 15
    )

    # 1a. Frischer Cache-Treffer -> direkt verwenden, kein Request nötig
    if has_usable_cache and current_time - cached_entry['timestamp'] < CACHE_EXPIRY:
        print(f"📦 Cache-Hit für '{query}': {cached_entry['price']}€ (Alter: {int((current_time - cached_entry['timestamp'])/3600)}h)")
        return cached_entry['price']

    if has_usable_cache:
        print(f"💾 Ebay scrap-Cache vorhanden ist aber abgelaufen! Aktuelles Datum: {current_time}, Entrydatum: {cached_entry['timestamp']}")

    # 2. Kein eBay-API-Key konfiguriert -> Live-Abfrage überspringen. Lieber einen
    # abgelaufenen Cache-Wert weiterverwenden als eine Anzeige mangels Preisdaten
    # komplett zu verpassen.
    if not settings.EBAY_CLIENT_ID or not settings.EBAY_CLIENT_SECRET:
        if has_usable_cache:
            print(f"⚠️ Kein EBAY_CLIENT_ID/EBAY_CLIENT_SECRET konfiguriert - nutze abgelaufenen Cache-Wert für '{query}': {cached_entry['price']}€")
            return cached_entry['price']
        print(f"⚠️ Kein EBAY_CLIENT_ID/EBAY_CLIENT_SECRET konfiguriert und kein Cache-Eintrag für '{query}' - Fallback auf 1000€ (Marge künstlich hoch, um die Anzeige nicht zu verpassen)")
        return 1000

    # 3. Live-Abfrage über die offizielle eBay Browse API
    print(f"💾 Ebay Browse API Suche: '{query}'")

    try:
        items = search_ebay_listings(query)

        all_prices = []
        min_gate = offer_price * 0.5
        max_gate = offer_price * 3.0
        for item in items:
            price_info = item.get("price")
            if not price_info or price_info.get("currency") != "EUR":
                continue
            try:
                val = float(price_info["value"])
            except (KeyError, TypeError, ValueError):
                continue
            if val <= 15:
                continue
            if min_gate <= val <= max_gate:
                all_prices.append(val)

        if len(all_prices) < 2:
            print(f"⚠️ Zu wenige Preise im Korridor ({min_gate:.2f}€ - {max_gate:.2f}€) für '{query}' gefunden ({len(items)} Angebote insgesamt).")
            raise RuntimeError("zu wenige Preise im Korridor gefunden")

        # Clustering Logik
        bucket_size = 20 if offer_price < 150 else 50
        buckets = {}
        for p in all_prices:
            lower_bound = int(p // bucket_size) * bucket_size
            buckets[lower_bound] = buckets.get(lower_bound, []) + [p]

        sorted_buckets = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)
        main_cluster_prices = sorted_buckets[0][1]
        market_median = round(statistics.median(main_cluster_prices), 2)

        print(f"📊 Analyse für '{query}':")
        print(f"   - Gefundene Preise im Korridor: {len(all_prices)}")
        print(f"   - Berechneter Marktwert: {market_median}€")

        # Ergebnis in Cache speichern - außer wir befinden uns im Read-Only-Testmodus
        # oder die Cache-Datei war beim Laden beschädigt. In beiden Fällen wird der
        # frische Wert trotzdem für DIESEN Lauf zurückgegeben (Scoring profitiert
        # sofort), nur eben nicht dauerhaft persistiert.
        if not cache_is_writable:
            print(f"   - ⚠️ NICHT gespeichert: Cache-Datei war beim Laden beschädigt.")
        elif settings.EBAY_PRICE_CACHE_READONLY:
            print(f"   - 🔒 NICHT gespeichert: EBAY_PRICE_CACHE_READONLY ist aktiv (Testmodus).")
        else:
            cache[cache_key] = {
                "price": market_median,
                "timestamp": current_time,
                "version": CACHE_VERSION
            }
            save_cache(cache)
            print(f"   - Gespeichert.")

        return market_median

    except Exception as e:
        print(f"❌ Fehler bei eBay Browse API-Abfrage für '{query}': {e}")
        # 4. Live-Abfrage fehlgeschlagen -> genau wie bei fehlendem Key: lieber einen
        # abgelaufenen Cache-Wert nehmen als die Anzeige komplett zu verpassen.
        if has_usable_cache:
            print(f"↩️ Nutze abgelaufenen Cache-Wert für '{query}': {cached_entry['price']}€")
            return cached_entry['price']
        print(f"↩️ Kein Cache-Wert für '{query}' vorhanden - Fallback auf 1000€")
        return 1000
