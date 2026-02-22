import os
import asyncio
import time
import requests
from pyrogram import Client, filters
from yt_dlp import YoutubeDL

API_ID = 29169428
API_HASH = '55742b16a85aac494c7944568b5507e5'
BOT_TOKEN = '8006815965:AAEQ2wkjCr8iKm78SiPc03QzQY_t33CxOeo'

MAX_DURATION = 30 * 60

app = Client(
    "video_dl_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=20
)

YDL_OPTS_YOUTUBE = {
    'format': 'best',
    'outtmpl': 'video_%(id)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
    'noplaylist': True,
    'format_sort': ['res:720', 'ext:mp4:m4a'],
}

YDL_OPTS_DEFAULT = {
    'format': 'best',
    'outtmpl': 'video_%(id)s.%(ext)s',
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

def download_thumbnail(url, target_path):
    try:
        resp = requests.get(url, stream=True, timeout=15)
        if resp.status_code == 200:
            with open(target_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            if os.path.exists(target_path):
                return target_path
    except Exception:
        pass
    return None

def pick_opts(url):
    if "youtube.com" in url or "youtu.be" in url:
        return YDL_OPTS_YOUTUBE
    return YDL_OPTS_DEFAULT

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("Bot-ka waa diyaar. Soo dir Link-ga.", quote=True)

@app.on_message(filters.private & filters.text)
async def handler(client, message):
    url = message.text.strip()
    if not url.startswith(("http://", "https://")):
        return

    msg = await message.reply_text("⏳ Processing...", quote=True)

    try:
        loop = asyncio.get_event_loop()
        ydl_opts = pick_opts(url)

        with YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            filename = ydl.prepare_filename(info)

            if not os.path.exists(filename):
                base = os.path.splitext(filename)[0]
                for ext in ['mp4', 'mkv', 'webm', '3gp']:
                    if os.path.exists(f"{base}.{ext}"):
                        filename = f"{base}.{ext}"
                        break

        await msg.edit_text("📤 Uploading...")
        width, height, duration = extract_metadata_from_info(info)
        
        thumb_path = None
        thumb_url = info.get("thumbnail")
        if thumb_url:
            thumb_path = download_thumbnail(thumb_url, f"thumb_{info.get('id')}.jpg")

        await app.send_video(
            chat_id=message.chat.id,
            video=filename,
            caption=info.get('title', 'Video')[:1024],
            thumb=thumb_path,
            width=width or 0,
            height=height or 0,
            duration=int(duration) if duration else 0,
            reply_to_message_id=message.id
        )

        if os.path.exists(filename): os.remove(filename)
        if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
        await msg.delete()

    except Exception as e:
        await msg.edit(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    app.run()
