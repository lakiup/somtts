

import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo
from yt_dlp import YoutubeDL

API_ID = 29169428
API_HASH = '55742b16a85aac494c7944568b5507e5'
BOT_TOKEN = '8006815965:AAHwuEBvTCObdXKWVqvYhczdfPBG36ugJEg'

bot = TelegramClient('video_dl_bot', API_ID, API_HASH)

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

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("**Haye!** Iisoo dir linkiga Muuqaal TikTok, Instagram ama Pinterest si aan kuugu soo dejiyo.")

@bot.on(events.NewMessage)
async def handler(event):
    if event.text.startswith('/start'):
        return
        
    url = event.text
    if not url.startswith(("http://", "https://")):
        return

    allowed_domains = ["tiktok.com", "instagram.com", "pinterest.com", "pin.it"]
    if not any(domain in url for domain in allowed_domains):
        await event.reply("❌ Bot-kani wuxuu u gaar yahay kaliya TikTok, Instagram, iyo Pinterest.")
        return

    msg = await event.reply("⏳ **Waan ku guda jiraa, fadlan sug...**")

    ydl_opts = {
        'format': 'best',
        'outtmpl': 'video_%(id)s.%(ext)s',
        'writethumbnail': True,
        'quiet': True,
    }

    if "pinterest.com" in url or "pin.it" in url:
        ydl_opts.update({
            'format': 'bestvideo+bestaudio/best',
            'check_formats': True,
            'ignoreerrors': True
        })

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
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

            attr = []
            if width and height and duration:
                attr.append(DocumentAttributeVideo(
                    duration=int(duration),
                    w=int(width),
                    h=int(height),
                    supports_streaming=True
                ))

            await bot.send_file(
                event.chat_id, 
                filename, 
                caption=caption,
                thumb=thumb_path,
                supports_streaming=True,
                attributes=attr,
                reply_to=event.id
            )

        if os.path.exists(filename):
            os.remove(filename)
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
            
        await msg.delete()

    except Exception:
        await msg.edit("❌ Khalad ayaa dhacay: Linkigaas lama soo dejin karo xilligan.")

def main():
    bot.start(bot_token=BOT_TOKEN)
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()
