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

WHITELIST = ["bundle", "aufrüstkit", "5800x3d", "5700x3d"]
MINIMUM_SCORE = 60
MINIMUM_MARGIN_EUR = 40
MAX_ITEM_PRICE = 800
MIN_ITEM_PRICE = 20
EXCLUDED_KEYWORDS = [
    "ddr3",
    "core 2 duo",
    "so-dimm",
    "sodimm",
    "joystick",
    "sound card",
    "webcam",
    "gigaset",
    "klapphandy",
    "festnetz",
    "yealink",
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
    "laptop",
    "amplifier",
    "pico",
    "drucker",
    "air pod",
    "handyhülle",
    "docking station",
    "halterung",
    "gesucht",
    "lcd",
    "ersatz",
    "logitech",
    "seat",
    "racing",
    "ally",
    "handheld",
    "buds",
    "lightning",
    "ladestation",
    "magsafe",
    "lenkrad",
    "universal",
    "stuhl",
    "dockingstation",
    "netzteil",
    "mobile",
    "macbook",
    "fernbedienung",
    "suche",
    "watch",
    "nur paypal",
    "a16",
    "kein versand",
    "nur abholung",
    "airpods",
    "huawei",
    "notebook",
    "pentium",
    "defekt",
    "athlon",
    "defekt",
    "tausch",
    "2400",
    "AM3",
    "2133",
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
            print(f"\n--- 🛰️ Scan gestartet: {now.strftime('%H:%M:%S')} ---")
            
            with get_session() as db:
                # 1. Stündlicher Cleanup
                if now - last_cleanup > timedelta(minutes=60):
                    delete_old_items(db)
                    last_cleanup = now
                
                # 2. Die eigentliche Arbeit (Anzeigen holen)
                get_all_post(db=db, telegram_message=True)
            
            # 3. Random Pause (zwischen 120 und 180 Sekunden)
            wait_time = randint(120, 180)
            print(f"--- ✅ Scan fertig. Pause: {wait_time}s ---")
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

    for link_model in links:
        print(f"Processing link - id: {link_model.id} - link: {link_model.link}")

        post_factory = ebayclass.EbayItemFactory(link_model.link)
        items = crud_post.add_items_to_db(db=db, items=post_factory.item_list)

        if telegram_message and items:
            potential_items = []
            batch_for_gpt = []
            item_map = {}  # Um später schnell auf das Item-Objekt per ID zuzugreifen

            for item in items:    
                item_date_str = item.date.strftime("%d.%m.%Y %H:%M") if hasattr(item.date, 'strftime') else str(item.date)
                p = parse_price(item.price)

                if not p or p <= 0:
                    p = 50
                else:
                    if p > MAX_ITEM_PRICE:
                        continue

                    if p < MIN_ITEM_PRICE:
                        continue

                if not contains_excluded_keywords(item.title, item.description):
                    print(f"Processing Item - title: {item.title} - price: {p}")

                    title_lower = item.title.lower()
    
                    # --- WHITELIST CHECK (Sofort-Benachrichtigung) ---
                    whitelist_match = [word for word in WHITELIST if word.lower() in title_lower]
    
                    if whitelist_match:
                        telegram.send_formated_message(item, is_whitelist=True)
        
                        # Wichtig: Mit 'continue' springen wir zum nächsten Artikel in der Schleife.
                        # So wird für diesen Artikel kein eBay-Preis gesucht und kein GPT genutzt.
                        continue
                    
                    potential_items.append({"id": item.id, "title": item.title, "item": item, "price": p, "date": item_date_str})

            if not potential_items: continue
            
            # 2. KI: Saubere Suchbegriffe generieren (Batch)
            clean_queries = generate_search_queries_batch(potential_items)

            for q_data in clean_queries:
                item_id = q_data['id']
                # Finde das originale Item-Objekt
                orig = next((x for x in potential_items if str(x['id']) == item_id), None)
                if not orig: continue

                cleaned_query = q_data['query']
                m_price = get_ebay_median_price(cleaned_query, orig['price'])

                if not m_price:
                    continue
                
                batch_for_gpt.append({
                    "id": item_id,
                    "title": orig['title'],
                    "offer_price_eur": orig['price'],
                    "ebay_median_eur": m_price,
                    "description": (orig['item'].description or "")[:400]
                })
                
                item_map[item_id] = {"obj": orig['item'], "m_price": m_price, "price": orig['price'], "date": orig['date'], "cleanedquery": cleaned_query}

            # 4. KI: Finales Batch-Scoring
            results = evaluate_listings_batch(batch_for_gpt)

            # 5. Telegram
            for res in results:
                rid = str(res.get('id'))   
                
                # Sicherheits-Check: Wenn rid nicht in Map, können wir nichts senden
                if rid not in item_map:
                    continue

                info = item_map[rid]
                itemPrice = parse_price(info['obj'].price)
                ebayMedianPrice = info['m_price']
                    
                expected_margin, score = calculate_score(
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
                    
            sleep(randint(0, 40) / 10)


if __name__ == "__main__":
    cli(sys.argv[1:])

def parse_price(raw_price) -> float | None:
    if not raw_price:
        return None

    text = str(raw_price).lower()

    # Zu verschenken / VB ohne Zahl
    if "verschenk" in text or text.strip() in ["vb", "verhandlungsbasis"]:
        return None

    # Zahl extrahieren
    match = re.search(r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)", text)
    if not match:
        return None

    number = match.group(1)

    # Tausenderpunkte entfernen
    number = number.replace(".", "").replace(",", ".")

    try:
        return float(number)
    except:
        return None


def calculate_score(offer_price, ebay_median, gpt_flags):
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
