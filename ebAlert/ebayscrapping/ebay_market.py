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
            
            soup = BeautifulSoup(res.text, 'html.parser')
            prices = []
            
            # Alle Preis-Elemente finden
            for el in soup.find_all('span', class_='s-item__price'):
                p_text = el.get_text().replace('.', '').replace(',', '.')
                # Extrahiert nur die Zahlen (auch bei Preisspannen)
                match = re.search(r"(\d+\.\d+)", p_text)
                if match:
                    val = float(match.group(1))
                    if val > 10: 
                        prices.append(val)

            if len(prices) < 3:
                return None

            print(f"Average selling price for item: {query} is : {round(statistics.median(prices), 2)}")
            return round(statistics.median(prices), 2)

        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout):
            print(f"⚠️ Timeout bei '{query}' (Versuch {attempt+1}/{max_retries})...")
            time.sleep(2) # Kurz warten vor dem nächsten Versuch
        except Exception as e:
            print(f"❌ Fehler bei eBay-Abruf: {e}")
            break
            
    return None
