import requests
import json
from ebAlert.core.config import settings
from ebAlert.ebayscrapping.ebayclass import EbayItem
from urllib.parse import quote

class SendingClass:
    def send_message(self, message, buttons=None):
        """
        Sendet eine Nachricht mit optionalen Inline-Buttons via POST.
        """
        url = f"{settings.TELEGRAM_API_URL.split('?')[0].replace('sendMessage', '')}sendMessage"
        
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

        try:
            response = requests.post(url, data=payload)
            return response.status_code == 200
        except Exception as e:
            print(f"Telegram Fehler: {e}")
            return False

    def send_formated_message(self, item_data, is_whitelist=False):
        # FALL A: Das angereicherte Paket (Dictionary)
        if isinstance(item_data, dict) and "obj" in item_data:
            item = item_data["obj"]
            score = item_data.get("score")
            m_price = item_data.get("m_price")
        # FALL B: Direktes Objekt (Whitelist oder alter Aufruf)
        else:
            item = item_data
            score = None
            m_price = None
        
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
        
        if score:
            message += (
                f"---------------------------\n"
                f"🎯 <b>KI-Score: {score}/100</b>\n"
            )
        
        # Buttons
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
        try:
            # Falls es schon ein String ist (aus deinem vorigen Fix)
            if isinstance(value, str):
                return value
            return value.strftime("%d.%m.%Y %H:%M")
        except:
            return str(value)

telegram = SendingClass()
