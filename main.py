import os
import asyncio
import time
from pyrogram import Client, filters
from yt_dlp import YoutubeDL

API_ID = 29169428
API_HASH = '55742b16a85aac494c7944568b5507e5'
BOT_TOKEN = '8006815965:AAHFHHOCNnW5IRSy0LL0pnD3SZrz44UDYwU'

MAX_DURATION = 30 * 60

app = Client(
    "video_dl_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=20
)

YDL_OPTS_YOUTUBE = {
    'format': 'bestvideo+bestaudio/best',
    'merge_output_format': 'mp4',
    'outtmpl': 'video_%(id)s.%(ext)s',
    'writethumbnail': True,
    'quiet': True,
    'no_warnings': True,
    'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None
}

YDL_OPTS_PINTEREST = {
    'format': 'best',
    'outtmpl': 'video_%(id)s.%(ext)s',
    'writethumbnail': True,
    'quiet': True,
    'no_warnings': True
}

YDL_OPTS_DEFAULT = {
    'format': 'best',
    'outtmpl': 'video_%(id)s.%(ext)s',
    'writethumbnail': True,
    'quiet': True,
    'no_warnings': True,
    'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None
}

def extract_metadata_from_info(info):
    width = info.get("width")
    height = info.get("height")
    duration = info.get("duration")
    if not width or not height:
        formats = info.get("formats") or []
        for f in formats:
            if f.get("width") and f.get("height"):
                width = f.get("width")
                height = f.get("height")
                break
    return width, height, duration

def pick_opts(url):
    if "youtube.com" in url or "youtu.be" in url:
        return YDL_OPTS_YOUTUBE
    if "pinterest.com" in url:
        return YDL_OPTS_PINTEREST
    return YDL_OPTS_DEFAULT

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("""Soo dhawoow 👋
Waxaan ahay Shorts Dl Bot
Waxaa i sameeyay @laki3012

I soo dir link-ga muuqaalka aad rabto inaan kuu soo dejiyo""", quote=True)

@app.on_message(filters.private & filters.text)
async def handler(client, message):
    url = message.text.strip()
    if not url.startswith(("http://", "https://")):
        return

    msg = await message.reply_text("⏳ **Processing...**", quote=True)

    try:
        loop = asyncio.get_event_loop()
        ydl_opts = pick_opts(url)

        with YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))

            duration = info.get("duration")
            if duration and duration > MAX_DURATION:
                await msg.edit("Zxp masoo dajin kari Video ka dheer 30 daqiiqo  Beta ayaan ku jiraa marka ma awoodi midaas")
                return

            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            filename = ydl.prepare_filename(info)

        await msg.edit_text("📤 **Uploading...**")

        caption = info.get('title', 'Video')
        if info.get('description'):
            caption = info.get('description')[:1024]

        width, height, duration = extract_metadata_from_info(info)

        thumb_path = None
        base_name = os.path.splitext(filename)[0]
        for ext in ['jpg', 'png', 'webp', 'jpeg']:
            potential_thumb = f"{base_name}.{ext}"
            if os.path.exists(potential_thumb):
                thumb_path = potential_thumb
                break

        await app.send_video(
            chat_id=message.chat.id,
            video=filename,
            caption=caption,
            thumb=thumb_path,
            width=width if width else 0,
            height=height if height else 0,
            duration=int(duration) if duration else 0,
            reply_to_message_id=message.id
        )

        if os.path.exists(filename):
            os.remove(filename)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

        await msg.delete()

    except Exception as e:
        print(f"Error: {e}")
        await msg.edit(" Error ayaa dhacay Hubi linkiga ama isku day mar kale")

if __name__ == "__main__":
    app.run()
