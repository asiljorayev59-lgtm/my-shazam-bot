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

# YOUTUBE BLOKIROVKADAN UTUVCHI STANDART PARAMETRLAR
def get_yt_opts(extra_opts=None):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {
            'youtube': {
                'player_client': ['mweb', 'android', 'web'],
                'skip': ['hls', 'dash']
            }
        }
    }
    if extra_opts:
        opts.update(extra_opts)
    return opts

# YOUTUBE SUPER FAST SEARCH
def search_yt_tracks(query, limit=5):
    ydl_opts = get_yt_opts({
        'extract_flat': True,
        'skip_download': True,
    })
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        res = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        return [{'id': e.get('id'), 'title': e.get('title')} for e in res.get('entries', []) if e]

def download_mp3(video_id):
    filename = f"{video_id}.mp3"
    ydl_opts = get_yt_opts({
        'format': 'ba/b',
        'outtmpl': video_id,
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'}],
    })
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    return filename

# GOLOS / AUDIO ORQALI ZUDLIK BILAN TOPISH
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_subscription(user_id, context):
        await send_sub_request(update)
        return

    msg = await update.message.reply_text("⚡️ AI Ovozni tahlil qilmoqda...")
    audio_file = await update.message.voice.get_file() if update.message.voice else await update.message.audio.get_file()
    file_path = "temp_audio.ogg"
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
    msg = await update.message.reply_text("🔎 MP3 variantlari izlanmoqda...")

    try:
        tracks = search_yt_tracks(query, limit=5)
        if tracks:
            keyboard = []
            for tr in tracks:
                keyboard.append([InlineKeyboardButton(f"🎶 {tr['title'][:38]}...", callback_data=f"dl_{tr['id']}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await msg.edit_text("👇 Yuklab olish uchun birini tanlang:", reply_markup=reply_markup)
        else:
            await msg.edit_text("❌ Hech narsa topilmadi.")

    except Exception as e:
        logger.error(f"Matn qidiruv xatosi: {e}")
        await msg.edit_text("⚠️ Qidiruvda xatolik yuz berdi.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "check_sub":
        SUB_CACHE.pop(user_id, None)
        if await check_subscription(user_id, context):
            await query.edit_message_text("✅ Rahmat! Endi botdan bemalol foydalanishingiz mumkin.")
        else:
            await query.answer("❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)

    elif data.startswith("getmp3_"):
        uid = data.split("_")[1]
        search_query = context.user_data.get(f"q_{uid}", "")
        if search_query:
            msg = await query.message.reply_text("🔎 MP3 variantlari izlanmoqda...")
            tracks = search_yt_tracks(search_query, limit=5)
            keyboard = []
            for tr in tracks:
                keyboard.append([InlineKeyboardButton(f"🎶 {tr['title'][:38]}...", callback_data=f"dl_{tr['id']}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await msg.edit_text("👇 Yuklab olish uchun birini tanlang:", reply_markup=reply_markup)

    elif data.startswith("dl_"):
        video_id = data.replace("dl_", "")
        msg = await query.message.reply_text("📥 MP3 yuklanmoqda va tayyorlanmoqda...")

        mp3_file = None
        try:
            mp3_file = download_mp3(video_id)
            if os.path.exists(mp3_file):
                caption_text = "🎧 @uzfrelanse orqali yuklab olindi!"
                with open(mp3_file, 'rb') as audio:
                    await query.message.reply_audio(audio=audio, caption=caption_text)
                await msg.delete()
            else:
                await msg.edit_text("⚠️ MP3 tayyorlashda xatolik bo'ldi.")
        except Exception as e:
            logger.error(f"Download error: {e}")
            await msg.edit_text("⚠️ Yuklab olishda xatolik bo'ldi.")
        finally:
            if mp3_file and os.path.exists(mp3_file):
                os.remove(mp3_file)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Application error:", exc_info=context.error)

if __name__ == '__main__':
    # Flask serverini orqa fonda ishga tushirish (Render Port uchun)
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
