import requests
import json
from ebAlert.core.config import settings
from ebAlert.ebayscrapping.ebayclass import EbayItem
from urllib.parse import quote

class SendingClass:
    def send_message(self, message, buttons=None):
        """
        Sendet eine Nachricht mit optionalen Inline-Buttons.
        buttons: Liste von Dicts, z.B. [{"text": "Google", "url": "https://google.com"}]
        """
        # Wir nutzen POST, da reply_markup (Buttons) als JSON gesendet werden muss
        url = f"{settings.TELEGRAM_API_URL.split('?')[0].replace('sendMessage', '')}sendMessage"
        
        payload = {
            "chat_id": settings.CHAT_ID,  # Stelle sicher, dass die ID in der Config ist
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }

        if buttons:
            # Erstellt die Tastatur-Struktur für Telegram
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": [buttons]  # Eine Reihe von Buttons
            })

        try:
            response = requests.post(url, data=payload)
            return response.status_code == 200
        except Exception as e:
            print(f"Telegram Fehler: {e}")
            return False
    
    def send_formated_message(self, item: EbayItem, is_whitelist=False):
        # Nachrichtentext aufbauen
        prefix = "🚨 <b>WHITELIST TREFFER</b>\n" if is_whitelist else "🔥 <b>NEUER DEAL</b>\n"
        posted_date = self.format_date(item.date)
        message = (
            f"{prefix}"
            f"📦 <b>{item.title}</b>\n"
            f"📅 Inseriert: {posted_date}\n"
            f"💰 Preis: <code>{item.price}</code>\n"
            f"📍 Ort: {item.city}\n"
        )

        # Buttons erstellen
        # 1. Button zur Anzeige
        # 2. Button zum eBay Preischeck (Verkaufte Artikel)
        ebay_query = quote(item.title)
        ebay_url = f"https://www.ebay.de/sch/i.html?_nkw={ebay_query}&LH_Sold=1&LH_Complete=1"
        
        buttons = [
            {"text": "📱 Anzeige öffnen", "url": item.link},
            {"text": "📊 eBay Check", "url": ebay_url}
        ]

        return self.send_message(message, buttons=buttons)

    def format_date(self, value):
        if not value:
            return "unbekannt"
        return value.strftime("%d.%m.%Y %H:%M")

telegram = SendingClass()
