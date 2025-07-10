import os
import asyncio
import time
import requests
from math import ceil
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
import yt_dlp

BOT_TOKEN = "8036675668:AAHcff9v_DLBNg5luGADA_VsgfTuULmK2Zs"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

user_queries = {}  # chat_id: {"results": [...], "video_id": None}

def format_duration(seconds: int):
    m, s = divmod(seconds, 60)
    return f"{m}:{str(s).zfill(2)}"

def format_views(views: int):
    if views >= 1_000_000_000:
        return f"{round(views / 1_000_000_000, 1)}B"
    elif views >= 1_000_000:
        return f"{round(views / 1_000_000, 1)}M"
    elif views >= 1_000:
        return f"{round(views / 1_000, 1)}K"
    return str(views)

async def search_youtube(query, count=30):
    ydl_opts = {"quiet": True, "extract_flat": False, "skip_download": True}
    results = []
    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        data = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch{count}:{query}", download=False))
        for entry in data["entries"]:
            results.append({
                "title": entry.get("title"),
                "url": entry.get("id"),
                "duration": entry.get("duration", 0),
                "view_count": entry.get("view_count", 0)
            })
    return results

async def download_audio(video_id_or_url, quality="192"):
    output_template = "%(title)s.%(ext)s"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": quality,
        }],
    }
    try:
        loop = asyncio.get_event_loop()
        start_time = time.time()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id_or_url}" if len(video_id_or_url) == 11 else video_id_or_url))
            filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
            duration = time.time() - start_time

        thumbnail_url = info.get("thumbnail")
        thumbnail_path = None
        if thumbnail_url:
            thumb_data = requests.get(thumbnail_url).content
            thumbnail_path = f"thumb_{video_id_or_url}.jpg"
            with open(thumbnail_path, "wb") as f:
                f.write(thumb_data)

        return filename, info.get("title", "Audio"), info.get("uploader", ""), duration, thumbnail_path
    except Exception as e:
        print("Download error:", e)
        return None, None, None, 0, None

def get_paged_keyboard(results, page):
    buttons_per_page = 6
    start = page * buttons_per_page
    end = start + buttons_per_page
    keyboard = []
    row = []

    for i, res in enumerate(results[start:end], start=start + 1):
        row.append(InlineKeyboardButton(text=f"[{i}]", callback_data=f"yt_{res['url']}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    total_pages = ceil(len(results) / buttons_per_page)
    nav_buttons = []

    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⏪ Orqaga", callback_data=f"nav_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="⏩ Keyingi", callback_data=f"nav_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer("👋 Salom! Menga YouTube musiqaning nomini yoki linkini yuboring, men sizga MP3 faylini yuboraman.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    text = message.text.strip()
    chat_id = message.chat.id

    if "youtube.com/watch" in text or "youtu.be/" in text:
        await message.answer("🔽 Yuklab olinmoqda...")
        file_path, title, artist, duration, thumbnail_path = await download_audio(text)
        if file_path:
            await message.answer_audio(FSInputFile(file_path), title=title, performer=artist,
                                       thumbnail=FSInputFile(thumbnail_path) if thumbnail_path else None)
            os.remove(file_path)
            if thumbnail_path:
                os.remove(thumbnail_path)
        else:
            await message.answer("❌ Yuklab olishda xatolik yuz berdi.")
    else:
        await message.answer("🔍 Qidirilmoqda...")
        results = await search_youtube(text)
        if not results:
            return await message.answer("❌ Hech nima topilmadi.")

        user_queries[chat_id] = {"results": results, "video_id": None}
        page = 0
        start = page * 6
        end = start + 6

        text_result = "\n".join([
            f"{i+1}. {res['title']} ({format_duration(res['duration'])}) - {format_views(res['view_count'])} views"
            for i, res in enumerate(results[start:end], start=start)
        ])
        kb = get_paged_keyboard(results, page)
        await message.answer(f"🎵 Topilgan musiqalar:\n\n{text_result}\n\nIltimos, yuklab olish uchun trekni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("yt_"))
async def handle_track(callback: types.CallbackQuery):
    video_id = callback.data[3:]
    chat_id = callback.from_user.id

    user_queries[chat_id]["video_id"] = video_id

    quality_buttons = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="128 kbps", callback_data=f"quality_128"),
            InlineKeyboardButton(text="192 kbps", callback_data=f"quality_192"),
            InlineKeyboardButton(text="320 kbps", callback_data=f"quality_320"),
        ]
    ])
    await callback.message.edit_text("🎚️ Iltimos, sifatni tanlang:", reply_markup=quality_buttons)

@dp.callback_query(F.data.startswith("quality_"))
async def handle_quality(callback: types.CallbackQuery):
    chat_id = callback.from_user.id
    quality = callback.data.split("_")[1]

    if chat_id not in user_queries or not user_queries[chat_id].get("video_id"):
        return await callback.answer("❌ Trek topilmadi yoki oldin tanlanmagan.", show_alert=True)

    video_id = user_queries[chat_id]["video_id"]

    await callback.message.edit_text("⬇️ Yuklab olinmoqda...")

    file_path, title, artist, duration, thumbnail_path = await download_audio(video_id, quality=quality)
    if file_path:
        await callback.message.answer(
            f"✅ Yuklab olindi: <b>{title}</b>\n⏱️ Tezligi: {round(duration, 2)}s"
        )
        await callback.message.answer_audio(
            FSInputFile(file_path),
            title=title,
            performer=artist,
            thumbnail=FSInputFile(thumbnail_path) if thumbnail_path else None
        )
        os.remove(file_path)
        if thumbnail_path:
            os.remove(thumbnail_path)
        user_queries.pop(chat_id, None)
    else:
        await callback.message.answer("❌ Yuklab olishda xatolik yuz berdi.")

@dp.callback_query(F.data.startswith("nav_"))
async def handle_navigation(callback: types.CallbackQuery):
    page = int(callback.data[4:])
    chat_id = callback.message.chat.id

    if chat_id not in user_queries or not user_queries[chat_id].get("results"):
        return await callback.answer("❌ Qidiruv natijasi topilmadi")

    results = user_queries[chat_id]["results"]
    start = page * 6
    end = start + 6

    text_result = "\n".join([
        f"{i+1}. {res['title']} ({format_duration(res['duration'])}) - {format_views(res['view_count'])} views"
        for i, res in enumerate(results[start:end], start=start)
    ])
    kb = get_paged_keyboard(results, page)
    await callback.message.edit_text(f"🎵 Topilgan musiqalar (sahifa {page+1}):\n\n{text_result}\n\nIltimos, yuklab olish uchun trekni tanlang:", reply_markup=kb)

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
