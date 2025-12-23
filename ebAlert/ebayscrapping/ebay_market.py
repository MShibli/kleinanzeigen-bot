import re
import statistics
import requests

def get_ebay_median_price(query: str, offer_price: float):
    url = f"https://www.ebay.de/sch/i.html?_nkw={query.replace(' ', '+')}&LH_Sold=1&LH_Complete=1&_ipg=60"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9"
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        # Findet alle Preise im Format EUR 123,45
        raw_matches = re.findall(r"EUR\s?(\d+(?:\.\d+)?,\d{2})", res.text)
        
        all_prices = []
        
        # DEFINIERE DEN KORRIDOR
        # Wir suchen nur Preise, die mindestens 50% des Angebotspreises entsprechen
        # und maximal 200% (um Zubehör vs. überteuerte Sammlerstücke zu trennen)
        min_gate = offer_price * 0.5
        max_gate = offer_price * 2.0

        for p in raw_matches:
            val = float(p.replace('.', '').replace(',', '.'))
            
            # Filter: Nur Preise im realistischen Korridor berücksichtigen
            # Das wirft Versandkosten (6,19€) bei einer 300€ Karte sofort raus!
            if min_gate <= val <= max_gate:
                all_prices.append(val)

        if len(all_prices) < 3:
            print(f"⚠️ Zu wenige Preise im Korridor ({min_gate:.2f}€ - {max_gate:.2f}€) gefunden.")
            return None

        # Clustering innerhalb des Korridors
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
        print(f"   - Berechneter Marktwert: {market_median}€ (Angebot war: {offer_price}€)")
        
        return market_median

    except Exception as e:
        print(f"❌ Fehler: {e}")
        return None
