# Fiyat Takip Botu

Trendyol, Hepsiburada, Amazon TR ve N11 ürünlerini takip eden Telegram botu.

## Kurulum (Railway)

1. GitHub'a yükle
2. Railway.app'te "New Project > Deploy from GitHub" seç
3. Şu environment variable'ları ekle:
   - `TELEGRAM_TOKEN` → BotFather'dan aldığın token
   - `TELEGRAM_CHAT_ID` → Senin chat ID'n

## Kullanım

- `/ekle <url> <isim>` → Ürün ekle
- `/listele` → Tüm ürünleri gör
- `/sil <url>` → Ürün sil
- `/kontrol` → Hemen fiyat kontrol et

Bot her saat başı otomatik kontrol eder, indirim olunca bildirim gönderir.
