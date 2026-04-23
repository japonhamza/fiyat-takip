import os
import json
import logging
import requests
import telebot
from bs4 import BeautifulSoup
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SCRAPER_KEY = os.environ.get("SCRAPER_API_KEY")
DATA_FILE = "products.json"

bot = telebot.TeleBot(TOKEN)

def scrape_url(url):
    try:
        api_url = f"http://api.scraperapi.com?api_key={SCRAPER_KEY}&url={url}&render=true&country_code=tr"
        resp = requests.get(api_url, timeout=60)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        logger.error(f"Scrape hatasi {url}: {e}")
    return None

def get_price_trendyol(soup):
    try:
        price = soup.select_one("span.discounted")
        if price:
            return price.get_text(strip=True)
        price = soup.select_one(".prc-dsc")
        if price:
            return price.get_text(strip=True)
        price = soup.select_one(".product-price-container span")
        if price:
            return price.get_text(strip=True)
    except:
        pass
    return None

def get_price_hepsiburada(soup):
    try:
        price = soup.select_one("[data-test-id='price-current-price']")
        if price:
            return price.get_text(strip=True)
        price = soup.select_one(".product-price")
        if price:
            return price.get_text(strip=True)
    except:
        pass
    return None

def get_price_amazon(soup):
    try:
        price = soup.select_one(".a-price-whole")
        fraction = soup.select_one(".a-price-fraction")
        if price:
            p = price.get_text(strip=True).replace(".", "").replace(",", "")
            if fraction:
                return f"{p},{fraction.get_text(strip=True)} TL"
            return f"{p} TL"
    except:
        pass
    return None

def get_price_n11(soup):
    try:
        # JSON-LD structured data dene
        import json
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get("@type") == "Product":
                        offers = data.get("offers", {})
                        price = offers.get("price")
                        if price:
                            return f"{price} TL"
            except:
                pass
        # Normal selector
        price = soup.select_one("div.newPrice ins")
        if price:
            return price.get_text(strip=True)
        price = soup.select_one(".newPrice ins")
        if price:
            return price.get_text(strip=True)
    except:
        pass
    return None

def get_price_generic(soup):
    for selector in [".price", ".product-price", "[class*='price']", "[class*='Price']"]:
        try:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                if any(c.isdigit() for c in text):
                    return text
        except:
            pass
    return None

def fetch_price(url):
    if "n11.com" in url:
        return fetch_price_n11_direct(url)
    
    soup = scrape_url(url)
    if not soup:
        return None

    if "trendyol.com" in url:
        return get_price_trendyol(soup)
    elif "hepsiburada.com" in url:
        return get_price_hepsiburada(soup)
    elif "amazon.com.tr" in url:
        return get_price_amazon(soup)
    else:
        return get_price_generic(soup)

def fetch_price_n11_direct(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "tr-TR,tr;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        return get_price_n11(soup)
    except Exception as e:
        logger.error(f"N11 direkt hatasi: {e}")
    return None

def parse_price_value(price_str):
    if not price_str:
        return None
    import re
    cleaned = re.sub(r"[^\d,\.]", "", price_str)
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except:
        return None

def load_products():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_products(products):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

def send_notification(text):
    try:
        bot.send_message(CHAT_ID, text)
    except Exception as e:
        logger.error(f"Bildirim hatasi: {e}")

def check_prices():
    products = load_products()
    if not products:
        return

    for url, data in products.items():
        try:
            current_price_str = fetch_price(url)
            if not current_price_str:
                logger.warning(f"Fiyat alinamadi: {url}")
                continue

            current_val = parse_price_value(current_price_str)
            old_val = parse_price_value(data.get("last_price"))

            logger.info(f"{data.get('name', url)}: {current_price_str}")

            if old_val and current_val and current_val < old_val:
                msg = (
                    f"Indirim Algilandi!\n\n"
                    f"Urun: {data.get('name', 'Urun')}\n"
                    f"Eski fiyat: {data['last_price']}\n"
                    f"Yeni fiyat: {current_price_str}\n"
                    f"Link: {url}"
                )
                send_notification(msg)

            products[url]["last_price"] = current_price_str
            save_products(products)

        except Exception as e:
            logger.error(f"Kontrol hatasi {url}: {e}")

@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.reply_to(message,
        "Merhaba! Ben fiyat takip botuyum.\n\n"
        "Komutlar:\n"
        "/ekle <url> <isim> - Urun ekle\n"
        "/listele - Takip edilen urunler\n"
        "/sil <url> - Urun sil\n"
        "/kontrol - Simdi fiyatlari kontrol et"
    )

@bot.message_handler(commands=["ekle"])
def cmd_ekle(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        bot.reply_to(message, "Kullanim: /ekle <url> <isim>")
        return

    url = parts[1]
    name = parts[2] if len(parts) > 2 else url[:50]

    bot.reply_to(message, "Fiyat kontrol ediliyor... (30-60 saniye sürebilir)")

    price = fetch_price(url)
    if not price:
        bot.reply_to(message, "Fiyat alinamadi. URL'yi kontrol edin.")
        return

    products = load_products()
    products[url] = {"name": name, "last_price": price}
    save_products(products)

    bot.reply_to(message, f"Eklendi!\nUrun: {name}\nMevcut fiyat: {price}")

@bot.message_handler(commands=["listele"])
def cmd_listele(message):
    products = load_products()
    if not products:
        bot.reply_to(message, "Takip edilen urun yok.")
        return

    msg = "Takip Edilen Urunler:\n\n"
    for url, data in products.items():
        msg += f"Urun: {data.get('name', 'Isimsiz')}\n"
        msg += f"Son fiyat: {data.get('last_price', 'Bilinmiyor')}\n"
        msg += f"Link: {url[:60]}\n\n"

    bot.reply_to(message, msg)

@bot.message_handler(commands=["sil"])
def cmd_sil(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Kullanim: /sil <url>")
        return

    url = parts[1]
    products = load_products()

    if url in products:
        name = products[url].get("name", url)
        del products[url]
        save_products(products)
        bot.reply_to(message, f"Silindi: {name}")
    else:
        bot.reply_to(message, "Urun bulunamadi.")

@bot.message_handler(commands=["kontrol"])
def cmd_kontrol(message):
    bot.reply_to(message, "Fiyatlar kontrol ediliyor...")
    check_prices()
    bot.reply_to(message, "Kontrol tamamlandi!")

def main():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_prices, "interval", hours=1)
    scheduler.start()
    logger.info("Bot baslatildi!")
    bot.infinity_polling()

if __name__ == "__main__":
    main()
