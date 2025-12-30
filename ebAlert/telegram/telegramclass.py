import socket
import requests

# Erzwinge IPv4
requests.packages.urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET

import requests
import json
from ebAlert.core.config import settings
from ebAlert.ebayscrapping.ebayclass import EbayItem
from urllib.parse import quote

class SendingClass:

    def __init__(self):      
        # Session erstellen (Hält die Verbindung zum Server offen)
        self.session = requests.Session()
        
        # Retry-Strategie: Wenn der Server gar nicht antwortet oder schluckauf hat
        retries = Retry(
            total=5,                          # Insgesamt 5 Versuche
            backoff_factor=1,                 # Wartezeit zwischen Versuchen: 1s, 2s, 4s...
            status_forcelist=[429, 500, 502, 503, 504], # Bei diesen Fehlern wiederholen
            raise_on_status=False
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        
    def send_message(self, message, buttons=None, disable_notfication=False):
        """
        Sendet eine Nachricht mit optionalen Inline-Buttons via POST.
        """
        url = f"{settings.TELEGRAM_API_URL.split('?')[0].replace('sendMessage', '')}sendMessage"

        if disable_notfication:
             payload = {
                "chat_id": settings.CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "disable_notification": True
            }
        else:
            payload = {
                "chat_id": settings.CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }

        if buttons:
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": [buttons]
            })

        for attempt in range(3): # Zusätzliche manuelle Schleife für Timeouts
            try:
                # Timeout ist entscheidend: 5s für Connect, 15s für Datentransfer
                response = self.session.post(self.url, data=payload, timeout=(5, 15))
                
                if response.status_code == 200:
                    return response.json()
                
                if response.status_code == 429:
                    # Telegram sagt "zu schnell" -> Wartezeit aus der Antwort lesen
                    retry_after = response.json().get("parameters", {}).get("retry_after", 5)
                    print(f"⚠️ Rate Limit! Warte {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                print(f"❌ Fehler {response.status_code}: {response.text}")
            
            except requests.exceptions.RequestException as e:
                print(f"🔔 Verbindungsversuch {attempt + 1} fehlgeschlagen: {e}")
                time.sleep(2) # Kurze Pause vor dem nächsten Versuch

    def send_formated_message(self, item_data, is_whitelist=False):
        # FALL A: Das angereicherte Paket (Dictionary)
        if isinstance(item_data, dict) and "obj" in item_data:
            item = item_data["obj"]
            score = item_data.get("score")
            m_price = item_data.get("m_price")
            margin = item_data.get("margin_eur")
        # FALL B: Direktes Objekt (Whitelist oder alter Aufruf)
        else:
            item = item_data
            score = None
            m_price = None
            margin = None
            
        # Prefix wählen
        if is_whitelist:
            prefix = "🚨 <b>WHITELIST TREFFER</b>\n"
        elif score and score >= 90:
            prefix = "💎 <b>TOP DEAL</b>\n"
        else:
            prefix = "🔥 <b>NEUER DEAL</b>\n"
        
        posted_date = self.format_date(item.date)
        
        # Nachrichtentext zusammenbauen
        message = (
            f"{prefix}"
            f"📦 <b>{item.title}</b>\n"
            f"📅 Inseriert: {posted_date}\n"
            f"💰 Preis: <code>{item.price}</code>"
        )
        
        if m_price:
            message += f" (Ebay: ~{m_price}€)"
        
        message += f"\n📍 Ort: {item.city}\n"
        message += f"---------------------------\n"
        message += f"🛍️ <b>Verkäufer: {getattr(item, 'seller_name', 'Nicht verfügbar')}</b>\n"
        message += f"📅 <b>Aktiv seit: {getattr(item, 'seller_agedays', 'Nicht verfügbar')} Tagen</b>\n"
        
        if score is not None:
            message += (
                f"---------------------------\n"
                f"🎯 <b>KI-Score: {score}/100</b>\n"
            )
            if margin is not None:
                message += f"🎯 <b>KI-Margin: {margin} €</b>\n"
        
        # Buttons

        if is_whitelist == True:
            ebay_query = item.title
        else:
            ebay_query = item_data["cleanedquery"]
            
        ebay_url = f"https://www.ebay.de/sch/i.html?_nkw={ebay_query}&LH_Sold=1&LH_Complete=1"
        ebay_live_url = f"https://www.ebay.de/sch/i.html?_nkw={ebay_query}&LH_BIN=1&_sop=15"
        
        buttons = [
            {"text": "📱 Anzeige öffnen", "url": item.link},
            {"text": "📊 eBay Check", "url": ebay_url},
            {"text": "🛍️ eBay Live", "url": ebay_live_url}
        ]
        
        return self.send_message(message, buttons=buttons)

    def format_date(self, value):
        if not value:
            return "unbekannt"
        try:
            # Falls es schon ein String ist (aus deinem vorigen Fix)
            if isinstance(value, str):
                return value
            return value.strftime("%d.%m.%Y %H:%M")
        except:
            return str(value)

telegram = SendingClass()
