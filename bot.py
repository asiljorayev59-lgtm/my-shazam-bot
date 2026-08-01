import os
import logging
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.request import HTTPXRequest
from shazamio import Shazam
import yt_dlp

# --- RENDER UCHUN KICHIK WEB SERVER (SLEEP BO'LMASLIGI UCHUN) ---
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "Bot 24/7 ishlamoqda!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
# -------------------------------------------------------------

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

shazam = Shazam()

TOKEN = os.environ.get("BOT_TOKEN", "8646777619:AAG4M7m-ERiRgMRPz2Dt-YFMS6d_nTtrpw8")
CHANNEL_USERNAME = "@uzfrelanse"
CHANNEL_URL = "https://t.me/uzfrelanse"

SUB_CACHE = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡️ **Tezkor AI Qo'shiq Topar Bot!**\n\n"
        "🎙 Qo'shiqdan **golos/audio** yuboring\n"
        "✍️ Yoki **qo'shiq / ijrochi nomini** yozing!\n\n"
        "Men soniyalar ichida qo'shiqni aniqlayman va MP3 variantlarini yuklab beraman.",
        parse_mode='Markdown'
    )

async def check_subscription(user_id, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if SUB_CACHE.get(user_id):
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        is_sub = member.status in ['creator', 'administrator', 'member']
        if is_sub:
            SUB_CACHE[user_id] = True
        return is_sub
    except Exception:
        return True

async def send_sub_request(update: Update):
    keyboard = [
        [InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=CHANNEL_URL)],
        [InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    msg = "⚠️ Botdan foydalanish uchun rasmiy kanalimizga obuna bo'ling:"
    try:
        if update.message:
            await update.message.reply_text(msg, reply_markup=markup)
        elif update.callback_query:
            await update.callback_query.message.reply_text(msg, reply_markup=markup)
    except Exception as e:
        logger.error(f"Xabar yuborish xatosi: {e}")

# SOUNDCLOUD VA XAFVS IZLASH TIZIMI
def search_tracks(query, limit=5):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'ignoreerrors': True,
    }

    entries = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            res = ydl.extract_info(f"scsearch{limit}:{query}", download=False)
            if res and res.get('entries'):
                entries = [e for e in res.get('entries', []) if e]
        except Exception as e:
            logger.error(f"SoundCloud search error: {e}")

    results = []
    for e in entries:
        if e:
            url = e.get('url') or e.get('webpage_url')
            title = e.get('title', 'Noma\'lum qo\'shiq')
            if url:
                results.append({'url': url, 'title': title})
            
    return results

# DRM VA STRIMLARNI MUKAMMAL MP3 GA AYLANTIRIB YUKLASH
def FAST_download_audio(audio_url, output_path):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f"{output_path}.%(ext)s",
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'nocheckcertificate': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'prefer_ffmpeg': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([audio_url])

# GOLOS / AUDIO ORQALI ZUDLIK BILAN TOPISH
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_subscription(user_id, context):
        await send_sub_request(update)
        return

    msg = await update.message.reply_text("⚡️ AI Ovozni tahlil qilmoqda...")
    audio_file = await update.message.voice.get_file() if update.message.voice else await update.message.audio.get_file()
    file_path = f"temp_{user_id}.ogg"
    await audio_file.download_to_drive(file_path)

    try:
        out = await shazam.recognize(file_path)
        track = out.get('track')

        if track:
            title = track.get('title', 'Noma\'lum')
            artist = track.get('subtitle', 'Noma\'lum')
            search_query = f"{artist} - {title}"

            context.user_data[f"q_{user_id}"] = search_query

            keyboard = [
                [InlineKeyboardButton("⏬ MP3 variantlarini olish", callback_data=f"getmp3_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await msg.edit_text(
                f"🎵 **Qo'shiq AI tomonidan topildi!**\n\n"
                f"📌 **Nomi:** {title}\n"
                f"🎙 **Ijrochi:** {artist}", 
                reply_markup=reply_markup, 
                parse_mode='Markdown'
            )
        else:
            await msg.edit_text("❌ Afsuski, bu ovozdan qo'shiq topilmadi.")
    except Exception as e:
        logger.error(f"Audio error: {e}")
        await msg.edit_text("⚠️ Qidirishda xatolik yuz berdi.")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# NOM / MATN BO'YICHA TEZKOR MP3 QIDIRUV
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_subscription(user_id, context):
        await send_sub_request(update)
        return

    query = update.message.text
    msg = await update.message.reply_text("🔎 Qo'shiqlar izlanmoqda...")

    try:
        tracks = search_tracks(query, limit=5)
        if tracks:
            keyboard = []
            context.user_data[f"search_{user_id}"] = tracks
            for idx, tr in enumerate(tracks):
                keyboard.append([InlineKeyboardButton(f"🎶 {tr['title'][:38]}...", callback_data=f"dl_{idx}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await msg.edit_text("👇 Yuklab olish uchun birini tanlang:", reply_markup=reply_markup)
        else:
            await msg.edit_text("❌ Hech narsa topilmadi.")

    except Exception as e:
        logger.error(f"Matn qidiruv xatosi: {e}")
        await msg.edit_text("⚠️ Qidiruvda xatolik yuz berdi.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    user_id = query.from_user.id

    if data == "check_sub":
        SUB_CACHE.pop(user_id, None)
        if await check_subscription(user_id, context):
            await query.edit_message_text("✅ Rahmat! Endi botdan bemalol foydalanishingiz mumkin.")
        else:
            try:
                await query.answer("❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)
            except Exception:
                pass

    elif data.startswith("getmp3_"):
        uid = data.split("_")[1]
        search_query = context.user_data.get(f"q_{uid}", "")
        if search_query:
            msg = await query.message.reply_text("🔎 Qo'shiqlar izlanmoqda...")
            tracks = search_tracks(search_query, limit=5)
            if tracks:
                keyboard = []
                context.user_data[f"search_{user_id}"] = tracks
                for idx, tr in enumerate(tracks):
                    keyboard.append([InlineKeyboardButton(f"🎶 {tr['title'][:38]}...", callback_data=f"dl_{idx}")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await msg.edit_text("👇 Yuklab olish uchun birini tanlang:", reply_markup=reply_markup)
            else:
                await msg.edit_text("❌ MP3 variantlari topilmadi.")

    elif data.startswith("dl_"):
        idx = int(data.replace("dl_", ""))
        tracks = context.user_data.get(f"search_{user_id}", [])
        
        if not tracks or idx >= len(tracks):
            await query.message.reply_text("⚠️ Qidiruv natijasi eskirgan. Qaytadan izlab ko'ring.")
            return

        target_track = tracks[idx]
        msg = await query.message.reply_text("⚡️ Yuklanmoqda...")

        output_base = f"track_{user_id}"
        try:
            FAST_download_audio(target_track['url'], output_base)
            
            # Faylni topish va o'chirishdan himoyalash
            downloaded_file = None
            for fname in os.listdir("."):
                if fname.startswith(output_base) and not fname.endswith(".ogg"):
                    downloaded_file = fname
                    break

            if downloaded_file and os.path.exists(downloaded_file):
                caption_text = f"🎧 {target_track['title']}\n\n🤖 @uzfrelanse orqali yuklab olindi!"
                with open(downloaded_file, 'rb') as audio:
                    await query.message.reply_audio(audio=audio, caption=caption_text, title=target_track['title'])
                await msg.delete()
            else:
                await msg.edit_text("⚠️ Ushbu trekni yuklab bo'lmadi. Boshqa variantini tanlab ko'ring.")
        except Exception as e:
            logger.error(f"Download error: {e}")
            await msg.edit_text("⚠️ Yuklab olishda xatolik bo'ldi.")
        finally:
            for fname in os.listdir("."):
                if fname.startswith(output_base) and not fname.endswith(".ogg"):
                    try:
                        os.remove(fname)
                    except Exception:
                        pass

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Application error:", exc_info=context.error)

if __name__ == '__main__':
    keep_alive()

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )
    app = ApplicationBuilder().token(TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)

    print("Ultra-tezkor AI Bot ishga tushdi...")
    app.run_polling(bootstrap_retries=5)
