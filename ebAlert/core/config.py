import os
import logging

class Settings:
    TOKEN = os.environ.get("TOKEN") or "Your_secret_key"
    CHAT_ID = os.environ.get("CHAT_ID") or "Your_chat_id"
    
    # Prüft, ob ein persistentes Verzeichnis definiert wurde (z.B. /app/data auf Railway)
    # Falls nicht, wird das Home-Verzeichnis (lokal) als Fallback genutzt.
    PERSISTENT_DIR = os.environ.get("CACHE_DIR") or os.path.expanduser("~")
    
    # Die Datenbankdatei wird nun im persistenten Verzeichnis abgelegt
    FILE_LOCATION = os.path.join(PERSISTENT_DIR, "ebayklein.db")
    
    TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&parse_mode=HTML&"
    LOGGING = os.environ.get("LOGGING") or logging.ERROR
    URL_BASE = "https://www.kleinanzeigen.de"
    OPEN_API_KEY = os.environ.get("OPEN_API_KEY") or "Your_OpenAI_Key"

settings = Settings()
