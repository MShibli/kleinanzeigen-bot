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
#from ebAlert.ebay_market import get_cached_market_price
from ebAlert.gpt_evaluator import evaluate_listings_batch

EXCLUDED_KEYWORDS = [
    "ddr3",
    "core 2 duo",
    "so-dimm",
    "sodimm",
    "laptop",
    "buds",
    "lightning",
    "ladestation",
    "fernbedienung",
    "watch",
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
    "für bastler",
    "tausch",
    "2400",
    "AM3",
    "2133",
    "gesprungen",
    "gesplittert",
    "kaputt",
    "schrott"
]

log = create_logger(__name__)

try:
    import click
    from click import BaseCommand
except ImportError:
    log.error("Click should be installed\npip install click")


@click.group()
def cli() -> BaseCommand:
    pass


@cli.command(help="Fetch new post and send telegramclass notification.")
def start():
    """
    loop through the urls in the database and send message
    """
    print(">> Starting Ebay alert")
    with get_session() as db:
        get_all_post(db=db, telegram_message=True)
    print("<< Ebay alert finished")


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
            batch_to_evaluate = []
            item_map = {}  # Um später schnell auf das Item-Objekt per ID zuzugreifen

            # 1. Sammeln und Vorfiltern
            for item in items:
                try:
                    price = parse_price(item.price)
                    title = item.title
                    description = item.description or ""
                    
                    if not price or contains_excluded_keywords(title, description):
                        continue

                    # Anzeige für Batch vorbereiten
                    listing_id = str(item.id)
                    batch_to_evaluate.append({
                        "id": listing_id,
                        "title": title,
                        "description": description[:500],  # Kürzen um Token zu sparen
                        "price": price
                    })
                    item_map[listing_id] = {
                        "item": item,
                        "price": price
                    }
                    print(f"Processing Item - id: {listing_id} - title: {title} - price: {price}")
                except Exception as e:
                    log.error(f"Error preparing item: {e}")

            # 2. Batch-Anfrage an GPT (z.B. in 15er Blöcken, falls die Liste sehr lang ist)
            chunk_size = 15 
            for i in range(0, len(batch_to_evaluate), chunk_size):
                chunk = batch_to_evaluate[i:i + chunk_size]
                results = evaluate_listings_batch(chunk)

                # 3. Ergebnisse verarbeiten
                for res in results:
                    res_id = str(res.get("id"))
                    if res_id not in item_map:
                        continue
                    
                    original_data = item_map[res_id]
                    item = original_data["item"]
                    price = original_data["price"]
                    
                    score = res.get("score", 0)
                    expected_margin = float(res.get("expected_margin", 0))

                    if "DDR5" in item.title:
                        expected_margin = expected_margin * 2
                        
                    negotiability = res.get("negotiability", "niedrig")
                    
                    # Logik für Marge und Filter
                    market_price = price + expected_margin
                    negotiated_price = estimate_negotiated_price(price, negotiability)
                    current_margin_pct = margin_percent(price, market_price)
                    negotiated_margin_pct = margin_percent(negotiated_price, market_price)

                    if max(current_margin_pct, negotiated_margin_pct) >= 0.40 and score >= 75:
                        posted_date = format_date(item.date)
                        telegram.send_message(
                            f"🔥 GPT BATCH DEAL {score}/100\n"
                            f"{item.title}\n"
                            f"📅 Inseriert: {posted_date}\n"
                            f"💰 Preis: {price} €\n"
                            f"📈 Marge: {expected_margin} €\n"
                            f"🤝 Verhandelbar: {negotiability}\n"
                            f"🔗 {item.link}"
                        )

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

def format_date(value):
    if not value:
        return "unbekannt"
    return value.strftime("%d.%m.%Y %H:%M")
