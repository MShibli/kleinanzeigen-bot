import re
import statistics
import requests
import json
import os
import time

# --- CACHE KONFIGURATION ---
# Prüft, ob CACHE_DIR in den Umgebungsvariablen existiert (Railway)
# Falls nicht (lokal), wird der aktuelle Ordner (.) verwendet
CACHE_DIR = os.getenv("CACHE_DIR", ".")
CACHE_FILE = os.path.join(CACHE_DIR, "ebay_price_cache.json")

# Stelle sicher, dass das Verzeichnis existiert (verhindert Fehler beim ersten Start)
if CACHE_DIR != "." and not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
    
CACHE_EXPIRY = 604800  # 24 Stunden in Sekunden (24 * 60 * 60)

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

def get_ebay_median_price(query: str, offer_price: float):
    # 1. Cache laden und prüfen
    cache = load_cache()
    current_time = time.time()
    
    # Normalisiere die Query für den Cache-Key (Kleinschreibung, ohne unnötige Leerzeichen)
    cache_key = query.lower().strip()

    if cache_key in cache:
        entry = cache[cache_key]
        # Prüfen, ob der Eintrag noch nicht abgelaufen ist
        if current_time - entry['timestamp'] < CACHE_EXPIRY:
            print(f"📦 Cache-Hit für '{query}': {entry['price']}€ (Alter: {int((current_time - entry['timestamp'])/3600)}h)")
            return entry['price']

    # 2. Wenn nicht im Cache oder abgelaufen -> Scrapen
    url = f"https://www.ebay.de/sch/i.html?_nkw={query.replace(' ', '+')}&LH_Sold=1&LH_Complete=1&_ipg=60"
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
        max_gate = offer_price * 2.0

        for p in raw_matches:
            val = float(p.replace('.', '').replace(',', '.'))
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
            "timestamp": current_time
        }
        save_cache(cache)
        
        print(f"📊 Analyse für '{query}':")
        print(f"   - Gefundene Preise im Korridor: {len(all_prices)}")
        print(f"   - Berechneter Marktwert: {market_median}€ (Neu gespeichert)")
        
        return market_median

    except Exception as e:
        print(f"❌ Fehler: {e}")
        return None
