import sys
import re
from random import randint
from time import sleep

from sqlalchemy.orm import Session

from ebAlert import create_logger
from ebAlert.crud.base import crud_link, get_session
from ebAlert.crud.post import crud_post
from ebAlert.ebayscrapping import ebayclass
from ebAlert.telegram.telegramclass import telegram
from ebAlert.gpt_evaluator import generate_search_queries_batch, evaluate_listings_batch
from ebAlert.ebayscrapping.ebay_market import get_ebay_median_price
from datetime import datetime, timedelta
from ebAlert.models.sqlmodel import EbayPost  # Importiere dein Modell
from ebAlert.ebayscrapping.seller_helper import fetch_seller_info

WHITELIST = ["bundle", "aufrüstkit", "5800x3d", "5700x3d"]
MINIMUM_SCORE = 60
MINIMUM_MARGIN_EUR = 40
MAX_ITEM_PRICE = 800
MIN_ITEM_PRICE = 20
NONE_PRICE = 50
SCORE_BOOSTERS = [
    "ddr4 64gb",
    "64gb ddr4",
    "ddr5"
]
EXCLUDED_KEYWORDS = [
    "ddr3",
    "core 2 duo",
    "so-dimm",
    "sodimm",
    "uleway",
    "emporia",
    "creative",
    "soundkarte",
    "unihertz",
    "t phone",
    "hp thunderbolt",
    "joystick",
    "displayschaden",
    "display schaden",
    "fairphone",
    "medion",
    "rx560",
    "rx570",
    "rx580",
    "galaxy tab",
    "note 20",
    "s10",
    "s9",
    "s7",
    "j5",
    "j7",
    "a7",
    "sd-ram",
    "sd ram",
    "display-fehler",
    "display fehler",
    "funktioniert nicht",
    "imac",
    "oukitel",
    "s20",
    "quadro",
    "macbook",
    "phillips",
    "senioren handy",
    "alcatel",
    "retro",
    "thrust",
    "sound card",
    "display beschädigt",
    "webcam",
    "gigaset",
    "klapphandy",
    "festnetz",
    "yealink",
    "htc",
    "amd fx",
    "captian dma"
    "oppo",
    "ericsson",
    "omen",
    "mac book",
    "moza",
    "seniorenhandy",
    "klapphandy",
    "am2",
    "am3",
    "anrufbeantworter",
    "brille",
    "nokia",
    "poco",
    "sandisk",
    "xcover",
    "lenovo",
    "displayschaden",
    "telekom",
    "aldi",
    "pedale",
    "siemens",
    "wiko",
    "headset",
    "scanner",
    "satelliten",
    "bastler",
    "fanatec",
    "beelink",
    "handycam",
    "panasonic",
    "xperia",
    "thinkpad",
    "ideapad",
    "intel",
    "i5",
    "i7",
    "i9",
    "honor",
    "xiaomi",
    "realme",
    "huawei",
    "redmi",
    "großhandel",
    "raspberry",
    "mini pc",
    "motorola",
    "iphone xs",
    "iphone x",
    "iphone xr",
    "iphone 6",
    "iphone 7",
    "iphone 8",
    "laptop",
    "amplifier",
    "pico",
    "drucker",
    "air pod",
    "docking station",
    "gesucht",
    "lcd",
    "oppo",
    "ersatz",
    "logitech",
    "seat",
    "racing",
    "ally",
    "handheld",
    "buds",
    "ladestation",
    "lenkrad",
    "stuhl",
    "dockingstation",
    "mobile",
    "macbook",
    "fernbedienung",
    "ipad",
    "ich suche",
    "watch",
    "a16",
    "kein versand",
    "airpods",
    "huawei",
    "notebook",
    "pentium",
    "defekt",
    "athlon",
    "ich tausch",
    "wackelkontakt",
    "2400",
    "AM3",
    "2133",
    "gebrochen",
    "gesprungen",
    "gesplittert",
    "kaputt",
    "schrott"
]

def delete_old_items(db: Session):
    """Löscht alle Anzeigen aus der Datenbank, die älter als 24 Stunden sind."""
    try:
        threshold = datetime.now() - timedelta(hours=24)
        old_items = db.query(EbayPost).filter(EbayPost.date < threshold)
        count = old_items.count()
        if count > 0:
            old_items.delete(synchronize_session=False)
            db.commit()
            print(f"🧹 Cleanup: {count} alte Einträge gelöscht.")
    except Exception as e:
        db.rollback()
        print(f"❌ Cleanup Fehler: {e}")

log = create_logger(__name__)

try:
    import click
    from click import BaseCommand
except ImportError:
    log.error("Click should be installed\npip install click")


@click.group()
def cli() -> BaseCommand:
    pass
    
@cli.command(help="Fetch new post and send telegram notification in an infinite loop.")
def start():
    """
    Endlosschleife für den Bot-Betrieb.
    """
    print(">> Starting Ebay alert Service (Infinite Loop)")
    
    # Timer für den stündlichen Cleanup initialisieren
    last_cleanup = datetime.now() - timedelta(hours=1)

    while True:
        try:
            now = datetime.now()
            current_hour = now.hour
            print(f"\n--- 🛰️ Scan gestartet: {now.strftime('%H:%M:%S')} ---")
            
            with get_session() as db:
                # 1. Stündlicher Cleanup
                if now - last_cleanup > timedelta(minutes=60):
                    delete_old_items(db)
                    last_cleanup = now
                
                # 2. Die eigentliche Arbeit (Anzeigen holen)
                get_all_post(db=db, telegram_message=True)
            
            # 3. Dynamische Pausenzeit berechnen
            # Nachtmodus: 02:00 bis 07:00 Uhr
            if 2 <= current_hour < 7:
                # Lange Pause in der Nacht (z.B. 15 bis 25 Minuten)
                wait_time = randint(1500, 3600)
                mode_text = "🌙 Nachtmodus"
            else:
                # Standard-Pause am Tag (60 bis 95 Sekunden)
                wait_time = randint(60, 95)
                mode_text = "☀️ Tagmodus"


            next_scan_time = (datetime.now() + timedelta(seconds=wait_time)).strftime("%H:%M:%S")
        
            # 3. Status-Update an Telegram senden
            status_text = f"🤖 **Bot-Status**\n" \
                          f"Letzter Scan: {datetime.now().strftime('%H:%M:%S')}\n" \
                          f"Nächster Scan: ca. {next_scan_time}\n" \
                          f"Modus: {mode_text}"
        
            telegram.send_message(status_text,disable_notfication=True) # Du müsstest eine send_message Methode haben
            
            print(f"--- ✅ Scan fertig ({mode_text}). Pause: {wait_time // 60}m {wait_time % 60}s ---")
            sleep(wait_time)

        except KeyboardInterrupt:
            print("\n<< Bot manuell beendet.")
            sys.exit(0)
        except Exception as e:
            print(f"⚠️ Loop-Fehler: {e}")
            # Bei Fehlern (z.B. Internet weg) 30 Sek warten und neu versuchen
            sleep(30)

@cli.command(options_metavar="<options>", help="Add/Show/Remove URL from database.")
@click.option("-r", "--remove_link", 'remove', metavar="<link id>", help="Remove link from database.")
@click.option("-c", "--clear", is_flag=True, help="Clear post database.")
@click.option("-a", "--add_url", 'url', metavar='<URL>', help="Add URL to database and fetch posts.")
@click.option("-i", "--init", is_flag=True, help="Initialise database after clearing.")
@click.option("-s", "--show", is_flag=True, help="Show all urls and corresponding id.")
def links(show, remove, clear, url, init):
    """
    cli related to the links. Add, remove, clear, init and show
    """
    # TODO: Add verification if action worked.
    with get_session() as db:
        if show:
            print(">> List of URL")
            links = crud_link.get_all(db)
            if links:
                for link_model in links:
                    print("{0:<{1}}{2}".format(link_model.id, 8 - len(str(link_model.id)), link_model.link))
            print("<< List of URL")
        elif remove:
            print(">> Removing link")
            if crud_link.remove(db=db, id=remove):
                print("<< Link removed")
            else:
                print("<< No link found")
        elif clear:
            print(">> Clearing item database")
            crud_post.clear_database(db=db)
            print("<< Database cleared")
        elif url:
            print(">> Adding url")
            if crud_link.get_by_key(key_mapping={"link": url}, db=db):
                print("<< Link already exists")
            else:
                crud_link.create({"link": url}, db)
                ebay_items = ebayclass.EbayItemFactory(url)
                crud_post.add_items_to_db(db, ebay_items.item_list)
                print("<< Link and post added to the database")
        elif init:
            print(">> Initializing database")
            get_all_post(db)
            print("<< Database initialized")


def get_all_post(db: Session, telegram_message=False):
    links = crud_link.get_all(db=db)
    if not links:
        return

    all_scraped_items = []

    # SCHRITT 1: Sammeln aller neuen Items von allen Links
    for link_model in links:
        try:
            print(f"Processing link - id: {link_model.id} - link: {link_model.link}")
            post_factory = ebayclass.EbayItemFactory(link_model.link)
            # add_items_to_db gibt nur die wirklich NEUEN Items zurück
            new_items = crud_post.add_items_to_db(db=db, items=post_factory.item_list)
            if new_items:
                all_scraped_items.extend(new_items)
        except Exception as e:
            print(f"❌ Fehler beim Scraping von Link {link_model.id}: {e}")

    if not telegram_message or not all_scraped_items:
        return

    # SCHRITT 2: Vorfilterung & Vorbereitung (Python-Logik)
    potential_items = []
    for item in all_scraped_items:
        try: 
            p = parse_price(item.price)
            
            if not p or p <= 0:
                p = NONE_PRICE
            else:
                if p > MAX_ITEM_PRICE:
                    continue
            
                if p < MIN_ITEM_PRICE:
                    continue
            
            if not contains_excluded_keywords(item.title, item.description):               
                seller_info = fetch_seller_info(item.link)
                sleep(0.3)

                print(f"Processing Item - title: {item.title} - price: {p} - id: {item.id} - Seller: {seller_info['seller_name']}, Sellertype: {seller_info['seller_type']}")
                # Verkäufer-Typ prüfen
                if seller_info["seller_type"] == "COMMERCIAL":
                    print(f"🔎 Überspringe gewerblichen Verkäufer: {seller_info['seller_name']}")
                    continue
                
                # ❌ Neue Accounts rausfiltern
                if seller_info["seller_age_days"] < 7:
                    print(f"⛔ Neuer Verkäufer ({seller_info['seller_name']}, "f"{seller_info['seller_age_days']} Tage) → Skip")
                    continue

                #if contains_excluded_keywords(seller_info["description"]):
                    # Hier: 'description' statt "description"
                #    print(f"Backlist Word! title: {item.title} - price: {p} - id: {item.id} - description: {seller_info['description']} → Skip")
                #    continue

                item.seller_name = seller_info['seller_name']
                item.seller_agedays = seller_info['seller_age_days']
                title_lower = item.title.lower()
            
                # --- WHITELIST CHECK (Sofort-Benachrichtigung) ---
                whitelist_match = [word for word in WHITELIST if word.lower() in title_lower]
            
                if whitelist_match:
                    telegram.send_formated_message(item, is_whitelist=True)           
                    # Wichtig: Mit 'continue' springen wir zum nächsten Artikel in der Schleife.
                    # So wird für diesen Artikel kein eBay-Preis gesucht und kein GPT genutzt.
                    continue


                potential_items.append({"id": item.id, "title": item.title, "item": item, "price": p, "seller_name": seller_info['seller_name'], "seller_agedays": seller_info['seller_age_days'], "date": item.date.strftime("%d.%m.%Y %H:%M") if hasattr(item.date, 'strftime') else str(item.date)})
        except Exception as e:
            print(f"⚠️ Fehler bei Vorfilterung Item {item.id}: {e}")
            
    if not potential_items:
        return

    # SCHRITT 3: Batch-Generierung der Suchbegriffe (1 GPT Call für alle)
    clean_queries = []
    try:
        clean_queries = generate_search_queries_batch(potential_items)
    except Exception as e:
        print(f"❌ Fehler bei Batch-Query-Generierung: {e}")
        return
    
    # SCHRITT 4: Median-Preise & GPT-Vorbereitung
    batch_for_gpt = []
    item_map = {}  # Um später schnell auf das Item-Objekt per ID zuzugreifen
   
    for q_data in clean_queries:
        try:
            item_id = q_data['id']
            # Finde das originale Item-Objekt
            orig = next((x for x in potential_items if str(x['id']) == item_id), None)
            if not orig: continue
        
            cleaned_query = q_data['query']
            m_price = get_ebay_median_price(cleaned_query, orig['price'])
        
            if not m_price:
                m_price = 1000
            
            batch_for_gpt.append({
                "id": item_id,
                "title": orig['title'],
                "offer_price_eur": orig['price'],
                "ebay_median_eur": m_price,
                "description": (orig['item'].description or "")[:400]
            })
            
            item_map[item_id] = {"obj": orig['item'], "m_price": m_price, "price": orig['price'], "date": orig['date'], "cleanedquery": cleaned_query, "seller_name": orig['seller_name'], "seller_agedays": orig['seller_agedays']}
        except Exception as e:
            print(f"⚠️ Fehler bei Median-Check für {q_data.get('id')}: {e}")
    
    # SCHRITT 5: Großes Batch-Scoring (1 GPT Call für alle Items)
    try:
        results = evaluate_listings_batch(batch_for_gpt)
    except Exception as e:
        print(f"❌ Fehler bei Batch-Evaluation: {e}")
        return
        
    # SCHRITT 6: Finale Berechnung & Telegram
    for res in results:
        try:
            rid = str(res.get('id'))   
            
            # Sicherheits-Check: Wenn rid nicht in Map, können wir nichts senden
            if rid not in item_map:
                continue
        
            info = item_map[rid]
            itemPrice = parse_price(info['obj'].price)
            ebayMedianPrice = info['m_price']
                
            expected_margin, score = calculate_score(
            itemTitle=info['obj'].title,
            itemDescription=info['obj'].description,
            offer_price=itemPrice,
            ebay_median=ebayMedianPrice,
            gpt_flags=res  # GPT liefert nur Flags!
            )
        
            print(
            f"id={rid} "
            f"buy={itemPrice} "
            f"median={ebayMedianPrice} "
            f"margin={expected_margin} "
            f"score={score} "
            f"flags={res}"
            )
            
            # Standardmäßig überspringen, außer ein Kriterium passt
            skipItem = True
            
            # Kriterium 1: Margin passt
            if expected_margin is not None and expected_margin >= MINIMUM_MARGIN_EUR:
                skipItem = False
        
            # Kriterium 2: Score passt
            if skipItem and score >= MINIMUM_SCORE:
                skipItem = False 
            
            # Sicherheits-Check gegen KI-Fehler (Price > Median trotz hohem Score)
            if score == 0:
                skipItem = True
            
            if skipItem:
                continue
                
            # Wir reichern das Dictionary mit den GPT-Ergebnissen an
            info['score'] = score
            info['margin_eur'] = expected_margin
            # ÜBERGABE DES GANZEN DICTS STATT NUR info["obj"]
            telegram.send_formated_message(info)
            #telegram.send_formated_message(info["obj"])
            sleep(randint(0, 30) / 10)
        except Exception as e:
            print(f"⚠️ Fehler bei finaler Verarbeitung von Item {res.get('id')}: {e}")

if __name__ == "__main__":
    cli(sys.argv[1:])

def parse_price(raw_price) -> float | None:
    if not raw_price:
        return NONE_PRICE

    text = str(raw_price).lower()

    # Zu verschenken / VB ohne Zahl
    if "verschenk" in text or text.strip() in ["vb", "verhandlungsbasis"]:
        return NONE_PRICE

    # Zahl extrahieren
    match = re.search(r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)", text)
    if not match:
        return NONE_PRICE

    number = match.group(1)

    # Tausenderpunkte entfernen
    number = number.replace(".", "").replace(",", ".")

    try:
        return float(number)
    except:
        return NONE_PRICE


def calculate_score(itemTitle, itemDescription, offer_price, ebay_median, gpt_flags):
    net_sale = ebay_median * 0.92
    target_buy = offer_price * 0.88
    margin_eur = net_sale - target_buy
    margin_pct = margin_eur / target_buy if target_buy else -1
    score = margin_pct * 200

    if gpt_flags.get("bundle"):
        score = 100 # Bundles Sonderbehandlung!
    if gpt_flags.get("obsolete"):
        score -= 40
    if gpt_flags.get("accessory_only"):
        score = 0

    # Score boosters-
    if ([word for word in SCORE_BOOSTERS if word.lower() in itemTitle] or [word for word in SCORE_BOOSTERS if word.lower() in itemDescription]):
        score += 30

    score = max(0, min(100, int(score)))
    return round(margin_eur, 2), score
    
def estimate_negotiated_price(price, negotiability):
    if negotiability == "hoch":
        return price * 0.85
    if negotiability == "mittel":
        return price * 0.92
    return price

def margin_percent(buy_price, sell_price):
    return (sell_price - buy_price) / buy_price

def contains_excluded_keywords(title, description=""):
    text = f"{title} {description}".lower()
    return any(word in text for word in EXCLUDED_KEYWORDS)
