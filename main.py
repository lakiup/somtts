import os
import asyncio
import time
from pyrogram import Client, filters
from yt_dlp import YoutubeDL

API_ID = 29169428
API_HASH = '55742b16a85aac494c7944568b5507e5'
BOT_TOKEN = '8006815965:AAHFHHOCNnW5IRSy0LL0pnD3SZrz44UDYwU'

app = Client("video_dl_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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

async def progress(current, total, message, start_time):
    now = time.time()
    diff = now - start_time
    if diff < 1:
        return
    percentage = current * 100 / total
    speed = current / diff
    
    progress_str = "[{0}{1}] {2}%".format(
        ''.join(["▰" for i in range(int(percentage / 10))]),
        ''.join(["▱" for i in range(10 - int(percentage / 10))]),
        round(percentage, 2)
    )
    
    tmp = f"{progress_str}\n\n🚀 Speed: {round(speed / 1024 / 1024, 2)} MB/s\n✅ Done: {round(current / 1024 / 1024, 2)} MB\n📦 Total: {round(total / 1024 / 1024, 2)} MB"
    
    try:
        await message.edit_text(f"😎 **Uploading...**\n\n{tmp}")
    except:
        pass

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("**Haye Laki!** Iisoo dir link kasta oo muuqaal ah si aan kuugu soo dejiyo.", quote=True)

@app.on_message(filters.private & filters.text)
async def handler(client, message):
    url = message.text
    if not url.startswith(("http://", "https://")):
        return

    msg = await message.reply_text("😜 **Downloading...**", quote=True)

    ydl_opts = {
        'format': 'best',
        'outtmpl': 'video_%(id)s.%(ext)s',
        'writethumbnail': True,
        'quiet': True,
        'no_warnings': True,
        'cookiefile': 'cookies.txt',
        'noplaylist': True
    }

    try:
        loop = asyncio.get_event_loop()
        
        with YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            filename = ydl.prepare_filename(info)
        
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

        start_time = time.time()
        await app.send_video(
            chat_id=message.chat.id,
            video=filename,
            caption=caption,
            thumb=thumb_path,
            width=width if width else 0,
            height=height if height else 0,
            duration=int(duration) if duration else 0,
            reply_to_message_id=message.id,
            progress=progress,
            progress_args=(msg, start_time)
        )

        if os.path.exists(filename):
            os.remove(filename)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
            
        await msg.delete()

    except Exception as e:
        await msg.edit(f"❌ Khalad: Linkigan lama soo dejin karo xilligan.")

if __name__ == "__main__":
    app.run()
