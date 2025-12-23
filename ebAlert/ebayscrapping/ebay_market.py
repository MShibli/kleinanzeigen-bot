import re
import statistics
import requests

def get_ebay_median_price(query: str):
    url = f"https://www.ebay.de/sch/i.html?_nkw={query.replace(' ', '+')}&LH_Sold=1&LH_Complete=1&_ipg=60"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9"
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        # 1. Alle Preise finden, die auf "EUR " folgen
        raw_matches = re.findall(r"EUR\s?(\d+(?:\.\d+)?,\d{2})", res.text)
        
        all_prices = []
        for p in raw_matches:
            val = float(p.replace('.', '').replace(',', '.'))
            if val > 5:  # Kleinstbeträge unter 5€ ignorieren
                all_prices.append(val)

        if len(all_prices) < 5:
            return None

        # 2. Clustering: Preise in 20€-Schritte (Buckets) einteilen
        # Beispiel: Ein Preis von 157€ landet im Bucket "140-160"
        bucket_size = 20
        buckets = {}

        for p in all_prices:
            lower_bound = int(p // bucket_size) * bucket_size
            buckets[lower_bound] = buckets.get(lower_bound, []) + [p]

        # 3. Die Gruppe mit den meisten Einträgen finden
        # Wir sortieren die Buckets nach der Anzahl der enthaltenen Preise
        sorted_buckets = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)
        
        # Die größte Gruppe (Main Cluster)
        main_cluster_prices = sorted_buckets[0][1]
        
        # Optional: Wenn die zweitgrößte Gruppe direkt angrenzt, nehmen wir sie dazu 
        # (falls ein Preis genau auf der Grenze liegt)
        main_bucket_val = sorted_buckets[0][0]
        for b_val, b_prices in sorted_buckets[1:]:
            if abs(b_val - main_bucket_val) <= bucket_size:
                main_cluster_prices.extend(b_prices)

        # 4. Median nur aus diesem Cluster berechnen
        market_median = round(statistics.median(main_cluster_prices), 2)
        
        print(f"📊 Analyse für '{query}':")
        print(f"   - Treffer gesamt: {len(all_prices)}")
        print(f"   - Cluster-Größe: {len(main_cluster_prices)}")
        print(f"   - Berechneter Marktwert: {market_median}€")
        
        return market_median

    except Exception as e:
        print(f"❌ Clustering Error: {e}")
        return None
