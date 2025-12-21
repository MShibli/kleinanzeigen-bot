import sys
from random import randint
from time import sleep

from sqlalchemy.orm import Session

from ebAlert import create_logger
from ebAlert.crud.base import crud_link, get_session
from ebAlert.crud.post import crud_post
from ebAlert.ebayscrapping import ebayclass
from ebAlert.telegram.telegramclass import telegram
#from ebAlert.ebay_market import get_cached_market_price
from ebAlert.gpt_evaluator import evaluate_listing

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

        if telegram_message:
            for item in items:
                try:
                    title = item.title
                    description = item.description or ""
                    price = float(item.price)
                    url = item.link

                    # 🔍 Produkt-Suchbegriff (erstmal simpel)
                    product_query = title.lower()

                   # market_price = get_cached_market_price(product_query)
                    #if not market_price:
                     #   continue

                    # 💸 Vorfilter → GPT nur bei Sinn
                    #if not cheap_precheck(price, market_price):
                        #continue

                    # 🤖 GPT Bewertung
                    result = evaluate_listing(
                        title=title,
                        description=description,
                        price=price,
                        market_price=market_price
                    )

                    if not result:
                        continue

                    score = result.get("score", 0)

                    if score >= 75:
                        telegram.send_message(
                            f"🔥 GPT DEAL {score}/100\n"
                            f"{title}\n"
                            f"💰 Preis: {price} €\n"
                            f"📊 Markt: {market_price} €\n"
                            f"📈 Marge: {result.get('expected_margin')} €\n"
                            f"🤝 Verhandelbar: {result.get('negotiability')}\n"
                            f"🔗 {url}"
                        )

                except Exception as e:
                    log.error(f"GPT evaluation failed: {e}")

        sleep(randint(0, 40) / 10)


if __name__ == "__main__":
    cli(sys.argv[1:])
