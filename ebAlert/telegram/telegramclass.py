import requests
import json
import re
import html
from ebAlert.core.config import settings
from ebAlert.ebayscrapping.ebayclass import EbayItem
from urllib.parse import quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time

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
        
    def send_message(self, message, buttons=None, disable_notfication=False, is_whitelistChat=False):
        """
        Sendet eine Nachricht mit optionalen Inline-Buttons via POST.
        """
        url = ""

        if is_whitelistChat == False:
            url =f"{settings.TELEGRAM_API_URL.split('?')[0].replace('sendMessage', '')}sendMessage"
        else:
            url =f"{settings.TELEGRAM_API_WHITELIST_URL.split('?')[0].replace('sendMessage', '')}sendMessage"

        target_chat_id = settings.WHITELIST_CHAT_ID if is_whitelistChat else settings.CHAT_ID
        
        if disable_notfication:
            payload = {
                "chat_id": target_chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
                "disable_notification": True
            }
        else:
            payload = {
                "chat_id": target_chat_id,
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
                response = self.session.post(url, data=payload, timeout=(5, 15))
                
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

        # Den Titel ebenfalls sicher machen (manche Leute schreiben "<Suche>" in den Titel)
        safe_title = html.escape(item.title)
        
        # Nachrichtentext zusammenbauen
        message = (
            f"{prefix}"
            f"📦 <b>{safe_title}</b>\n"
            f"📅 Inseriert: {posted_date}\n"
            f"💰 Preis: <code>{item.price}</code>"
        )
        
        if m_price:
            message += f" (Ebay: ~{m_price}€)"

        # Den Verkäufernamen sicher machen
        raw_seller = getattr(item, 'seller_name', 'Nicht verfügbar')
        safe_seller = html.escape(str(raw_seller))
                
        message += f"\n📍 Ort: {item.city}\n"
        message += f"---------------------------\n"
        message += f"🛍️ <b>Verkäufer: {safe_seller}</b>\n"
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
            ebay_query = self.get_safe_telegram_button_text(item.title)
        else:
            ebay_query = item_data["cleanedquery"]
            
        ebay_url = f"https://www.ebay.de/sch/i.html?_nkw={ebay_query}&LH_Sold=1&LH_Complete=1"
        ebay_live_url = f"https://www.ebay.de/sch/i.html?_nkw={ebay_query}&LH_BIN=1&_sop=15"
        
        buttons = [
            {"text": "📱 Anzeige öffnen", "url": item.link},
            {"text": "📊 eBay Check", "url": ebay_url},
            {"text": "🛍️ eBay Live", "url": ebay_live_url}
        ]

        result = self.send_message(message, buttons=buttons, is_whitelistChat=False)
        
        if is_whitelist == True:
            return self.send_message(message, buttons=buttons, is_whitelistChat=True)
        else:
            return result

    def edit_message(self, message_id, text):
        url = f"{settings.TELEGRAM_API_URL.split('?')[0].replace('sendMessage', '')}editMessageText"
        payload = {
            "chat_id": settings.CHAT_ID,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            response = self.session.post(url, data=payload, timeout=(5, 10))
            return response.json()
        except Exception as e:
            print(f"⚠️ Fehler beim Editieren der Status-Nachricht: {e}")
            return None

    
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

    @staticmethod
    def get_safe_telegram_button_text(query_text):
        # 1. Nur wichtige Zeichen behalten (Buchstaben, Zahlen, Leerzeichen)
        clean_query = re.sub(r'[^a-zA-Z0-9\säöüÄÖÜß]', '', query_text)
        # 2. URL-konform kodieren
        return quote(clean_query)

telegram = SendingClass()
