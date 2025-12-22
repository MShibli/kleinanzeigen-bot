import requests
from bs4 import BeautifulSoup
import re
import statistics
import time

def get_ebay_median_price(query: str):
    """Scrapt verkaufte Artikel auf eBay.de mit Retry-Logik."""
    url = f"https://www.ebay.de/sch/i.html?_nkw={query.replace(' ', '+')}&LH_Sold=1&LH_Complete=1&_ipg=60"
    
    # Ein realistischerer Header eines echten Browsers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.google.com/"
    }
    
    max_retries = 2
    for attempt in range(max_retries):
        try:
            print(f"Searching selling price for item: {query}")
            # Timeout auf 10 Sekunden erhöht
            res = requests.get(url, headers=headers, timeout=10)
            print(f"ebay reqeust statuscode: {res.status_code}")
            res.raise_for_status() # Fehler bei 403, 404 etc. werfen
            
            # Wir nutzen Regex direkt auf dem Text, um "EUR 123,45" zu finden
            # Das Pattern sucht nach 'EUR', Leerzeichen, Ziffern, optional Tausenderpunkt, Komma, Ziffern
            raw_prices = re.findall(r"EUR\s?(\d+(?:\.\d+)?,\d{2})", res.text)
        
            cleaned_prices = []
            for p in raw_prices:
                # Umwandlung von Deutsch (1.234,56) in Float (1234.56)
                p_float = float(p.replace('.', '').replace(',', '.'))
            
                # Ausreißer-Schutz: 
                # 1. Sehr kleine Beträge sind meist Versand oder Zubehör
                # 2. Wir ignorieren den "Startpreis" oder "UVP", falls diese doppelt auftauchen
                if p_float > 15:
                    cleaned_prices.append(p_float)

            # WICHTIG: eBay listet oft "Ähnliche Artikel" am Ende. 
            # Wir nehmen daher nur die ersten ~20-30 Treffer, um den Median nicht zu verfälschen
            valid_prices = cleaned_prices[:30]

            if len(valid_prices) < 3:
                print(f"DEBUG: Zu wenige Preise ({len(valid_prices)}) gefunden für '{query}'")
                return None

            median_price = round(statistics.median(valid_prices), 2)
            print(f"✅ Median für '{query}': {median_price}€ ({len(valid_prices)} Treffer)")
            return median_price

        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout):
            print(f"⚠️ Timeout bei '{query}' (Versuch {attempt+1}/{max_retries})...")
            time.sleep(2) # Kurz warten vor dem nächsten Versuch
        except Exception as e:
            print(f"❌ Fehler bei eBay-Abruf: {e}")
            break
            
    return None
