import os
import json
import time
import logging
import requests
from bs4 import BeautifulSoup
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DATA_FILE = "products.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

def load_products():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_products(products):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

def get_price_trendyol(soup):
    try:
        price = soup.select_one(".prc-dsc")
        if price:
            return price.get_text(strip=True)
        price = soup.select_one(".product-price-container .prc-dsc")
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
        price = soup.select_one(".newPrice ins")
        if price:
            return price.get_text(strip=True)
        price = soup.select_one(".price ins")
        if price:
            return price.get_text(strip=True)
    except:
        pass
    return None

def fetch_price(url):
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        if "trendyol.com" in url:
            return get_price_trendyol(soup)
        elif "hepsiburada.com" in url:
            return get_price_hepsiburada(soup)
        elif "amazon.com.tr" in url:
            return get_price_amazon(soup)
        elif "n11.com" in url:
            return get_price_n11(soup)
        else:
            # Genel fiyat deneme
            for selector in [".price", ".product-price", "[class*='price']"]:
                el = soup.select_one(selector)
                if el:
                    return el.get_text(strip=True)
    except Exception as e:
        logger.error(f"Fiyat çekme hatası {url}: {e}")
    return None

def parse_price_value(price_str):
    if not price_str:
        return None
    import re
    # Sayısal değeri çıkar
    cleaned = re.sub(r"[^\d,\.]", "", price_str)
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except:
        return None

async def send_message(text):
    bot = Bot(token=TOKEN)
    await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")

def check_prices():
    products = load_products()
    if not products:
        return

    for url, data in products.items():
        try:
            current_price_str = fetch_price(url)
            if not current_price_str:
                logger.warning(f"Fiyat alınamadı: {url}")
                continue

            current_val = parse_price_value(current_price_str)
            old_val = parse_price_value(data.get("last_price"))

            logger.info(f"{data.get('name', url)}: {current_price_str}")

            if old_val and current_val and current_val < old_val:
                import asyncio
                msg = (
                    f"🎉 <b>İNDİRİM ALGILANDI!</b>\n\n"
                    f"📦 <b>{data.get('name', 'Ürün')}</b>\n"
                    f"💰 Eski fiyat: {data['last_price']}\n"
                    f"✅ Yeni fiyat: {current_price_str}\n"
                    f"🔗 <a href='{url}'>Ürüne git</a>"
                )
                asyncio.run(send_message(msg))

            products[url]["last_price"] = current_price_str
            save_products(products)

        except Exception as e:
            logger.error(f"Kontrol hatası {url}: {e}")

# --- Telegram Komutları ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Merhaba! Ben fiyat takip botuyum.\n\n"
        "📌 Komutlar:\n"
        "/ekle <url> <isim> - Ürün ekle\n"
        "/listele - Takip edilen ürünler\n"
        "/sil <url> - Ürün sil\n"
        "/kontrol - Şimdi fiyatları kontrol et"
    )

async def ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Kullanım: /ekle <url> <isim>")
        return

    url = context.args[0]
    name = " ".join(context.args[1:]) if len(context.args) > 1 else url[:50]

    await update.message.reply_text("🔍 Fiyat kontrol ediliyor...")

    price = fetch_price(url)
    if not price:
        await update.message.reply_text("❌ Fiyat alınamadı. URL'yi kontrol edin.")
        return

    products = load_products()
    products[url] = {"name": name, "last_price": price}
    save_products(products)

    await update.message.reply_text(
        f"✅ Eklendi!\n📦 {name}\n💰 Mevcut fiyat: {price}"
    )

async def listele(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    if not products:
        await update.message.reply_text("📭 Takip edilen ürün yok.")
        return

    msg = "📋 <b>Takip Edilen Ürünler:</b>\n\n"
    for url, data in products.items():
        msg += f"📦 {data.get('name', 'İsimsiz')}\n"
        msg += f"💰 Son fiyat: {data.get('last_price', 'Bilinmiyor')}\n"
        msg += f"🔗 {url[:60]}...\n\n"

    await update.message.reply_text(msg, parse_mode="HTML")

async def sil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Kullanım: /sil <url>")
        return

    url = context.args[0]
    products = load_products()

    if url in products:
        name = products[url].get("name", url)
        del products[url]
        save_products(products)
        await update.message.reply_text(f"🗑️ Silindi: {name}")
    else:
        await update.message.reply_text("❌ Ürün bulunamadı.")

async def kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Fiyatlar kontrol ediliyor...")
    check_prices()
    await update.message.reply_text("✅ Kontrol tamamlandı!")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ekle", ekle))
    app.add_handler(CommandHandler("listele", listele))
    app.add_handler(CommandHandler("sil", sil))
    app.add_handler(CommandHandler("kontrol", kontrol))

    # Her saat başı fiyat kontrol
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_prices, "interval", hours=1)
    scheduler.start()

    logger.info("Bot başlatıldı!")
    app.run_polling()

if __name__ == "__main__":
    main()
