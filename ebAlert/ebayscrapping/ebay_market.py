import requests
from bs4 import BeautifulSoup
import re
import statistics

def get_ebay_sold_price(query: str):
    """Sucht nach verkauften Artikeln auf eBay.de und gibt den Median-Preis zurück."""
    # Bereinige den Suchbegriff (Sonderzeichen entfernen)
    clean_query = re.sub(r'[^a-zA-Z0-9\s]', '', query)
    url = f"https://www.ebay.de/sch/i.html?_nkw={clean_query.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Suche nach allen Preis-Elementen
        price_elements = soup.find_all('span', class_='s-item__price')
        prices = []
        
        for el in price_elements:
            # Extrahiere Zahl aus Strings wie "EUR 150,00" oder "150,00 EUR"
            text = el.get_text().replace('.', '').replace(',', '.')
            match = re.search(r"(\d+\.\d+)", text)
            if match:
                price = float(match.group(1))
                if price > 5: # Ignoriere Kleinteile/Versand
                    prices.append(price)

        if not prices:
            return None
            
        # Wir nutzen den Median, um Ausreißer (Ersatzteile/defekte Geräte) zu ignorieren
        return round(statistics.median(prices), 2)
    except Exception as e:
        print(f"Fehler beim eBay-Abruf für {query}: {e}")
        return None
