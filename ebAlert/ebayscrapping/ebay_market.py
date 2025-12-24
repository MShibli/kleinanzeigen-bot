import re
import statistics
import requests
import json
import os
import time
from urllib.parse import quote

# --- CACHE KONFIGURATION ---
# Prüft, ob CACHE_DIR in den Umgebungsvariablen existiert (Railway)
# Falls nicht (lokal), wird der aktuelle Ordner (.) verwendet
CACHE_DIR = os.getenv("CACHE_DIR", ".")
CACHE_FILE = os.path.join(CACHE_DIR, "ebay_price_cache.json")

# Stelle sicher, dass das Verzeichnis existiert (verhindert Fehler beim ersten Start)
if CACHE_DIR != "." and not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
    
CACHE_EXPIRY = 604800  # 1 Woche in Sekunden
CACHE_VERSION = "v4"  # Ändere dies auf v3, v4 etc., wenn du die Logik anpasst

# In deinen Funktionen nutzt du jetzt einfach CACHE_FILE
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except exception as e:
            print("ebay scrap load_cache Error:", e)
            return {}

    print("ebay scrap load_cache Error: Keine Cachedatei gefunden!")
    return {}

def save_cache(cache_data):
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
    
def get_ebay_median_price(query: str, offer_price: float):
    # 1. Cache laden und prüfen
    cache = load_cache()
    current_time = time.time()
    
    # Normalisiere die Query für den Cache-Key (Kleinschreibung, ohne unnötige Leerzeichen)
    cache_key = query.lower().strip()

    if cache_key in cache:
        entry = cache[cache_key]
        if entry.get('version') == CACHE_VERSION:
            if entry['price'] > 15:        
                # Prüfen, ob der Eintrag noch nicht abgelaufen ist
                if current_time - entry['timestamp'] < CACHE_EXPIRY:
                    print(f"📦 Cache-Hit für '{query}': {entry['price']}€ (Alter: {int((current_time - entry['timestamp'])/3600)}h)")
                    return entry['price']

        print(f"💾 Ebay scrap-Cache vorhanden ist aber abgelaufen! Aktuelles Datum: {current_time}, Entrydatum: {entry['timestamp']}")

    # 2. Wenn nicht im Cache oder abgelaufen -> Scrapen
    #url = f"https://www.ebay.de/sch/i.html?_nkw={query.replace(' ', '+')}&LH_Sold=1&LH_Complete=1&_ipg=120"
    url = build_refined_ebay_url(query.replace(' ', '+'))
    print(f"💾 Ebay scrap-URL: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9"
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        raw_matches = re.findall(r"EUR\s?(\d+(?:\.\d+)?,\d{2})", res.text)

        # Prüfen, ob eBay uns blockiert hat oder die Seite existiert
        if res.status_code != 200:
            print(f"⚠️ eBay Fehler: Status {res.status_code} für '{query}'")
            return None
       
        all_prices = []
        min_gate = offer_price * 0.5
        max_gate = offer_price * 3.0

        for p in raw_matches:
            val = float(p.replace('.', '').replace(',', '.'))
            if val <= 15:
                continue
            if min_gate <= val <= max_gate:
                all_prices.append(val)

        if len(all_prices) < 3:
            print(f"⚠️ Zu wenige Preise im Korridor ({min_gate:.2f}€ - {max_gate:.2f}€) für '{query}' gefunden.")
            return None

        # Clustering Logik
        bucket_size = 20 if offer_price < 150 else 50
        buckets = {}
        for p in all_prices:
            lower_bound = int(p // bucket_size) * bucket_size
            buckets[lower_bound] = buckets.get(lower_bound, []) + [p]

        sorted_buckets = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)
        main_cluster_prices = sorted_buckets[0][1]
        market_median = round(statistics.median(main_cluster_prices), 2)

        # 3. Ergebnis in Cache speichern
        cache[cache_key] = {
            "price": market_median,
            "timestamp": current_time,
            "version": CACHE_VERSION
        }
        save_cache(cache)
        
        print(f"📊 Analyse für '{query}':")
        print(f"   - Gefundene Preise im Korridor: {len(all_prices)}")
        print(f"   - Berechneter Marktwert: {market_median}€ (Neu gespeichert)")
        
        return market_median

    except Exception as e:
        print(f"❌ Fehler: {e}")
        return None
