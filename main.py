import os
import asyncio
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
    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    'merge_output_format': 'mp4',
    'outtmpl': 'video_%(id)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
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

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("Welcome 👋\nSend link to download or `/list link` to see formats.", quote=True)

@app.on_message(filters.private & filters.text)
async def handler(client, message):
    text = message.text.strip()
    
    if text.startswith("/list"):
        url = text.replace("/list", "").strip()
        if not url:
            await message.reply_text("Fadlan link raaci tusaale: `/list https://youtube.com/...` ")
            return
        
        msg = await message.reply_text("🔍 Checking formats...")
        try:
            with YoutubeDL({'quiet': True}) as ydl:
                info = await asyncio.get_event_loop().run_in_executor(None, lambda: ydl.extract_info(url, download=False))
                formats = info.get('formats', [])
                res = "Available Formats:\n\n"
                for f in formats:
                    res += f"ID: {f['format_id']} | Ext: {f['ext']} | Res: {f.get('resolution', 'N/A')}\n"
                
                await msg.edit_text(res[:4096])
            return
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")
            return

    if not text.startswith(("http://", "https://")):
        return

    msg = await message.reply_text("⏳ Processing...", quote=True)

    try:
        loop = asyncio.get_event_loop()
        with YoutubeDL(YDL_OPTS_YOUTUBE) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(text, download=False))
            
            duration = info.get("duration")
            if duration and duration > MAX_DURATION:
                await msg.edit("Video-gan waa ka dheer yahay 30 daqiiqo.")
                return

            info = await loop.run_in_executor(None, lambda: ydl.extract_info(text, download=True))
            filename = ydl.prepare_filename(info)

        await msg.edit_text("📤 Uploading...")
        
        width, height, duration = extract_metadata_from_info(info)
        thumb_url = info.get("thumbnail")
        thumb_path = download_thumbnail(thumb_url, f"thumb_{info.get('id')}.jpg") if thumb_url else None

        await app.send_video(
            chat_id=message.chat.id,
            video=filename,
            caption=info.get('title', 'Video'),
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
        await msg.edit(f"❌ Error: {str(e)}"[:4096])

if __name__ == "__main__":
    app.run()
