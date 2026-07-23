import re
import statistics
import requests
import json
import os
import shutil
import time
from urllib.parse import quote, urlencode

from ebAlert.core.config import settings

SCRAPER_API_ENDPOINT = "https://api.scraperapi.com/"

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

CACHE_VERSION = "v4"  # Ändere dies auf v3, v4 etc., wenn du die Logik anpasst

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
            return json.load(f)
    except Exception as e:
        print(f"❌ ebay scrap load_cache Error: Cache-Datei beschädigt/nicht lesbar ({e}) - Datei bleibt unangetastet!")
        return None

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

def build_refined_ebay_url(query: str):
    base_url = "https://www.ebay.de/sch/i.html"
    
    # 1. Query für die Textsuche säubern (GB bleibt hier drin)
    # Macht aus "iPhone+6s+16GB" -> "iPhone 6s 16GB"
    clean_query_for_nkw = query.replace("+", " ").strip()
    
    params = {
        "_nkw": clean_query_for_nkw,
        "LH_Sold": "1",
        "LH_Complete": "1",
        "_ipg": "120"
    }
    
    # 2. Modell-Filter (Spezialbehandlung für iPhone)
    ebay_filter = ""
    if "iphone" in clean_query_for_nkw.lower():
        # Modell-Name extrahieren (ohne Apple/iPhone/GB)
        model_part = clean_query_for_nkw.lower().replace("apple", "").replace("iphone", "")
        # Entferne Speicherangaben wie 16GB, 64 GB etc.
        model_part = re.sub(r"\d+\s?(gb|tb|mb)", "", model_part, flags=re.IGNORECASE).strip()
        
        # Formatierung: Apple iPhone [Modell]
        # Wir nutzen .title() und korrigieren danach das "iPhone"
        full_model = f"Apple iPhone {model_part.title()}".replace("Iphone", "iPhone").strip()
        
        # ERZWINGEN von %2520:
        # quote() macht Leerzeichen zu %20. Wir ersetzen %20 durch %2520.
        encoded_model = quote(full_model).replace("%20", "%2520")
        ebay_filter = f"&Modell={encoded_model}"

    # 3. URL zusammenbauen
    # Für _nkw nutzen wir das Standard-Verfahren (Leerzeichen zu +)
    query_string = "&".join([f"{k}={quote(v).replace('%20', '+')}" for k, v in params.items()])
    final_url = f"{base_url}?{query_string}{ebay_filter}"
    # Test mit: "iPhone 6s 16GB"
    # Ergebnis Modell-Teil: &Modell=Apple%2520iPhone%25206S
    return final_url


def build_scraperapi_url(target_url: str) -> str:
    """Wrappt eine Ziel-URL für den Abruf über ScraperAPI (umgeht eBays Akamai Bot Manager)."""
    params = {"api_key": settings.SCRAPER_API_KEY, "url": target_url}
    if settings.SCRAPER_API_RENDER:
        params["render"] = "true"
    if settings.SCRAPER_API_ULTRA_PREMIUM:
        params["ultra_premium"] = "true"
    elif settings.SCRAPER_API_PREMIUM:
        params["premium"] = "true"
    return f"{SCRAPER_API_ENDPOINT}?{urlencode(params)}"


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

    # 2. Kein ScraperAPI-Key konfiguriert -> Live-Abfrage würde ohnehin an eBays
    # Akamai Bot Manager scheitern (403). Lieber einen abgelaufenen Cache-Wert
    # weiterverwenden als eine Anzeige mangels Preisdaten komplett zu verpassen.
    if not settings.SCRAPER_API_KEY:
        if has_usable_cache:
            print(f"⚠️ Kein SCRAPER_API_KEY konfiguriert - nutze abgelaufenen Cache-Wert für '{query}': {cached_entry['price']}€")
            return cached_entry['price']
        print(f"⚠️ Kein SCRAPER_API_KEY konfiguriert und kein Cache-Eintrag für '{query}' - Fallback auf 1000€ (Marge künstlich hoch, um die Anzeige nicht zu verpassen)")
        return 1000

    # 3. Live-Abfrage über ScraperAPI
    target_url = build_refined_ebay_url(query.replace(' ', '+'))
    request_url = build_scraperapi_url(target_url)
    print(f"💾 Ebay scrap-URL (via ScraperAPI): {target_url}")

    try:
        # render=true lässt ScraperAPI die Seite per Headless-Browser laden, damit
        # Akamais JS-Challenge besteht wird. Das dauert entsprechend länger als ein
        # normaler Request, daher der großzügige Timeout.
        res = requests.get(request_url, timeout=70)

        if res.status_code != 200:
            print(f"⚠️ ScraperAPI Fehler: Status {res.status_code} für '{query}'")
            raise RuntimeError(f"ScraperAPI Status {res.status_code}")

        all_prices = []
        min_gate = offer_price * 0.5
        max_gate = offer_price * 3.0
        raw_matches = re.findall(r"EUR\s?(\d+(?:\.\d+)?,\d{2})", res.text)

        for p in raw_matches:
            val = float(p.replace('.', '').replace(',', '.'))
            if val <= 15:
                continue
            if min_gate <= val <= max_gate:
                all_prices.append(val)

        if len(all_prices) < 3:
            print(f"⚠️ Zu wenige Preise im Korridor ({min_gate:.2f}€ - {max_gate:.2f}€) für '{query}' gefunden.")
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
        elif settings.SCRAPER_API_CACHE_READONLY:
            print(f"   - 🔒 NICHT gespeichert: SCRAPER_API_CACHE_READONLY ist aktiv (Testmodus).")
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
        print(f"❌ Fehler bei ScraperAPI-Abfrage für '{query}': {e}")
        # 4. Live-Abfrage fehlgeschlagen -> genau wie bei fehlendem Key: lieber einen
        # abgelaufenen Cache-Wert nehmen als die Anzeige komplett zu verpassen.
        if has_usable_cache:
            print(f"↩️ Nutze abgelaufenen Cache-Wert für '{query}': {cached_entry['price']}€")
            return cached_entry['price']
        print(f"↩️ Kein Cache-Wert für '{query}' vorhanden - Fallback auf 1000€")
        return 1000
