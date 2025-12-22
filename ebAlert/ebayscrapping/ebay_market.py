import requests
from bs4 import BeautifulSoup
import re
import statistics

def get_ebay_median_price(query: str):
    """Scrapt verkaufte Artikel auf eBay.de und berechnet den Median."""
    url = f"https://www.ebay.de/sch/i.html?_nkw={query.replace(' ', '+')}&LH_Sold=1&LH_Complete=1&_ipg=60"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36"}
    
    try:
        print(f"Searching selling price for item: {query}")
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        prices = []
        
        for el in soup.find_all('span', class_='s-item__price'):
            p_text = el.get_text().replace('.', '').replace(',', '.')
            match = re.search(r"(\d+\.\d+)", p_text)
            if match:
                val = float(match.group(1))
                if val > 10: prices.append(val) # Kleinteile filtern

        if len(prices) < 3: return None # Zu wenig Daten für Statistik
        
        print(f"Average selling price for item: {query} is : {round(statistics.median(prices), 2)}")
        # Median ist robuster gegen Ausreißer (z.B. defekte Geräte)
        return round(statistics.median(prices), 2)
    except:
        return None
