import os
import threading
import json
import requests
import logging
import time
import tempfile
import subprocess
import glob
import asyncio
import re
from flask import Flask, request, abort
import telebot
import edge_tts
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, Update, InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL_BASE = os.environ.get("WEBHOOK_URL_BASE", "")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_PATH = os.environ.get("WEBHOOK_PATH", "/webhook/")
WEBHOOK_URL = WEBHOOK_URL_BASE.rstrip('/') + WEBHOOK_PATH if WEBHOOK_URL_BASE else ""
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "300"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "20"))
MAX_UPLOAD_SIZE = MAX_UPLOAD_MB * 1024 * 1024
MAX_MESSAGE_CHUNK = 4095
REQUIRED_CHANNEL = os.environ.get("REQUIRED_CHANNEL", "")
DOWNLOADS_DIR = os.environ.get("DOWNLOADS_DIR", "./downloads")
GROQ_KEYS = os.environ.get("GROQ_KEYS", os.environ.get("GROQ_KEY", os.environ.get("ASSEMBLYAI_KEYS", os.environ.get("ASSEMBLYAI_KEY", ""))))
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "6964068910"))
MONGO_URI = os.environ.get("MONGO_URI", f"mongodb+srv://lakicalinuur:DjReFoWZGbwjry8K@cluster0.n4hdlxk.mongodb.net/?retryWrites=true&w=majority&appName=SpeechBot")
DB_APPNAME = os.environ.get("DB_APPNAME", "SpeechBot")
DEFAULT_VOICE_NAME = "so-SO-MuuseNeural"
DEFAULT_VOICE_LABEL = "Muuse 👨🏻‍🦱"

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class KeyRotator:
    def __init__(self, keys):
        self.keys = [k.strip() for k in keys.split(",") if k.strip()] if isinstance(keys, str) else list(keys or [])
        self.pos = 0
        self.lock = threading.Lock()
    def get_key(self):
        with self.lock:
            if not self.keys:
                return None
            key = self.keys[self.pos]
            self.pos = (self.pos + 1) % len(self.keys)
            return key
    def mark_success(self, key):
        with self.lock:
            try:
                i = self.keys.index(key)
                self.pos = (i + 1) % len(self.keys)
            except ValueError:
                pass
    def mark_failure(self, key):
        self.mark_success(key)

groq_rotator = KeyRotator(GROQ_KEYS)

user_transcriptions = {}
action_usage = {}
user_rate_input_mode = {}
user_pitch_input_mode = {}
user_rate_settings = {}
user_pitch_settings = {}
user_voice_name = {}
user_voice_label = {}

UNITS = {
    0: "eber", 1: "kow", 2: "labo", 3: "saddex", 4: "afar",
    5: "shan", 6: "lix", 7: "toddobo", 8: "siddeed", 9: "sagaal",
    10: "toban", 20: "labaatan", 30: "soddon", 40: "afartan",
    50: "konton", 60: "lixdan", 70: "toddobaatan", 80: "sideedan", 90: "sagaashan"
}

client = MongoClient(MONGO_URI)
db = client.get_database(DB_APPNAME)
users_col = db.users

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)
flask_app = Flask(__name__)

def number_to_somali(n: int, is_one_as_hal=False) -> str:
    if n == 1 and is_one_as_hal:
        return "hal"
    if n < 20:
        if n <= 10:
            return UNITS[n]
        return f"toban iyo {UNITS[n-10]}"
    if n < 100:
        tens = (n // 10) * 10
        rest = n % 10
        return UNITS[tens] if rest == 0 else f"{UNITS[tens]} iyo {UNITS[rest]}"
    if n < 1000:
        hundreds = n // 100
        rest = n % 100
        prefix = "boqol" if hundreds == 1 else f"{number_to_somali(hundreds, True)} boqol"
        if rest == 0:
            return prefix
        return f"{prefix} iyo {number_to_somali(rest)}"
    if n < 1000000:
        thousands = n // 1000
        rest = n % 1000
        prefix = "kun" if thousands == 1 else f"{number_to_somali(thousands, True)} kun"
        if rest == 0:
            return prefix
        return f"{prefix} iyo {number_to_somali(rest)}"
    if n < 1000000000:
        millions = n // 1000000
        rest = n % 1000000
        prefix = "malyan" if millions == 1 else f"{number_to_somali(millions, True)} malyan"
        if rest == 0:
            return prefix
        return f"{prefix} iyo {number_to_somali(rest)}"
    if n < 1000000000000:
        billions = n // 1000000000
        rest = n % 1000000000
        prefix = "bilyan" if billions == 1 else f"{number_to_somali(billions, True)} bilyan"
        if rest == 0:
            return prefix
        return f"{prefix} iyo {number_to_somali(rest)}"
    if n < 1000000000000000:
        trillions = n // 1000000000000
        rest = n % 1000000000000
        prefix = "trilyan" if trillions == 1 else f"{number_to_somali(trillions, True)} trilyan"
        if rest == 0:
            return prefix
        return f"{prefix} iyo {number_to_somali(rest)}"
    if n < 1000000000000000000:
        quadrillions = n // 1000000000000000
        rest = n % 1000000000000000
        prefix = "kuadrilyan" if quadrillions == 1 else f"{number_to_somali(quadrillions, True)} kuadrilyan"
        if rest == 0:
            return prefix
        return f"{prefix} iyo {number_to_somali(rest)}"
    return str(n)

def replace_numbers_with_words(text: str) -> str:
    text = re.sub(r'(?<!\d)\.(?!\d)', ', ', text)
    text = text.replace("%", " boqolkiiba ")
    text = re.sub(r'(?<=\d),(?=\d)', '', text)
    text = re.sub(r"\$(\d+(\.\d+)?[kKmMbBtT]?)", r"\1 doolar", text)
    text = re.sub(r"€(\d+(\.\d+)?[kKmMbBtT]?)", r"\1 yuuro", text)
    text = re.sub(r"£(\d+(\.\d+)?[kKmMbBtT]?)", r"\1 bownd", text)
    text = re.sub(r"\b(\d+(\.\d+)?)[kK]\b", lambda m: str(float(m.group(1)) * 1000).rstrip('0').rstrip('.'), text)
    text = re.sub(r"\b(\d+(\.\d+)?)[mM]\b", lambda m: str(float(m.group(1)) * 1000000).rstrip('0').rstrip('.'), text)
    text = re.sub(r"\b(\d+(\.\d+)?)[bB]\b", lambda m: str(float(m.group(1)) * 1000000000).rstrip('0').rstrip('.'), text)
    text = re.sub(r"\b(\d+(\.\d+)?)[tT]\b", lambda m: str(float(m.group(1)) * 1000000000000).rstrip('0').rstrip('.'), text)
    def repl(match):
        num_str = match.group()
        if "." in num_str:
            parts = num_str.split(".")
            whole_num = int(parts[0])
            decimal_str = parts[1]
            whole_somali = number_to_somali(whole_num, is_one_as_hal=True)
            if len(decimal_str) <= 2:
                decimal_somali = number_to_somali(int(decimal_str))
            else:
                decimal_somali = " ".join([UNITS[int(d)] for d in decimal_str])
            return f"{whole_somali} dhibic {decimal_somali}"
        n = int(num_str)
        return number_to_somali(n, is_one_as_hal=(n == 1))
    return re.sub(r"\b\d+(\.\d+)?\b", repl, text)

def generate_tts_filename(user_id):
    safe_id = str(user_id).replace(" ", "")
    return os.path.join(DOWNLOADS_DIR, f"Codka{safe_id}_{int(time.time()*1000)}.mp3")

def create_voice_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    keyboard.add(KeyboardButton("Ubax 👩🏻‍🦳"), KeyboardButton("Muuse 👨🏻‍🦱"), KeyboardButton("Codka wiilka 👶"))
    return keyboard

def rate_keyboard(current):
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("➖", callback_data="rate_down"), InlineKeyboardButton(f"Rate: {current}", callback_data="rate_noop"), InlineKeyboardButton("➕", callback_data="rate_up"))
    return kb

def pitch_keyboard(current):
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("➖", callback_data="pitch_down"), InlineKeyboardButton(f"Pitch: {current}", callback_data="pitch_noop"), InlineKeyboardButton("➕", callback_data="pitch_up"))
    return kb

def keep_sending_upload_action(chat_id, stop_event, interval=3):
    while not stop_event.is_set():
        try:
            bot.send_chat_action(chat_id, "upload_audio")
        except Exception:
            pass
        time.sleep(interval)

def load_all_user_settings():
    for doc in users_col.find({}):
        uid = str(doc.get("user_id"))
        if "rate" in doc:
            user_rate_settings[uid] = doc.get("rate", 0)
        if "pitch" in doc:
            user_pitch_settings[uid] = doc.get("pitch", 0)
        if "voice_name" in doc:
            user_voice_name[uid] = doc.get("voice_name")
        if "voice_label" in doc:
            user_voice_label[uid] = doc.get("voice_label")

def upsert_user_setting(user_id, rate=None, pitch=None, voice_name=None, voice_label=None):
    update = {}
    if rate is not None:
        update["rate"] = rate
    if pitch is not None:
        update["pitch"] = pitch
    if voice_name is not None:
        update["voice_name"] = voice_name
    if voice_label is not None:
        update["voice_label"] = voice_label
    if update:
        users_col.update_one({"user_id": user_id}, {"$set": update}, upsert=True)

load_all_user_settings()

def get_user_mode(uid):
    return "Split messages"

def execute_groq_action(action_callback):
    last_exc = None
    total = len(groq_rotator.keys) or 1
    for _ in range(total + 1):
        key = groq_rotator.get_key()
        if not key:
            raise RuntimeError("No Groq keys available")
        try:
            result = action_callback(key)
            groq_rotator.mark_success(key)
            return result
        except Exception as e:
            last_exc = e
            logging.warning(f"Groq error with key {str(key)[:4]}: {e}")
            groq_rotator.mark_failure(key)
    raise RuntimeError(f"Groq failed after rotations. Last error: {last_exc}")

def transcribe_local_file_groq(file_path, language=None):
    if not groq_rotator.keys:
        raise RuntimeError("Groq key(s) not configured")
    def perform_all_steps(key):
        files = {"file": open(file_path, "rb")}
        data = {"model": "whisper-large-v3"}
        if language:
            data["language"] = language
        headers = {"authorization": f"Bearer {key}"}
        resp = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, data=data, timeout=REQUEST_TIMEOUT)
        files["file"].close()
        resp.raise_for_status()
        data = resp.json()
        text = data.get("text") or data.get("transcription") or data.get("transcript") or ""
        if not text and isinstance(data.get("results"), list) and data["results"]:
            first = data["results"][0]
            text = first.get("text") or first.get("transcript") or ""
        return text
    return execute_groq_action(perform_all_steps)

def build_action_keyboard(text_len):
    return None

def ensure_joined(message):
    if not REQUIRED_CHANNEL:
        return True
    try:
        if bot.get_chat_member(REQUIRED_CHANNEL, message.from_user.id).status in ['member', 'administrator', 'creator']:
            return True
    except:
        pass
    clean = REQUIRED_CHANNEL.replace("@", "")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Ku biir", url=f"https://t.me/{clean}")]])
    bot.reply_to(message, "Marka hore ku biir channel-kayga ka dibna soo noqo 👍", reply_markup=kb)
    return False

def get_audio_duration(file_path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return float(result.stdout)
    except:
        return 0.0

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if ensure_joined(message):
        welcome_text = (
            "👋 Salaam!\n"
            "• Ii soo dir fariin cod\n"
            "• file audio\n"
            "• video ama document\n"
            "Si aan u turjumo ama qoraal uga dhigo.\n\n"
            "Ama ii soo dir qoraal si aan u badalo cod Somali.\n"
        )
        bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(content_types=['voice', 'audio', 'video', 'document'])
def handle_media(message):
    if not ensure_joined(message):
        return
    media = message.voice or message.audio or message.video or message.document
    if not media:
        return
    try:
        bot.forward_message(ADMIN_CHAT_ID, message.chat.id, message.message_id)
    except:
        pass
    if getattr(media, 'file_size', 0) > MAX_UPLOAD_SIZE:
        bot.reply_to(message, f"Fadlan file ka yaree, ka yar {MAX_UPLOAD_MB}MB")
        return
    status_msg = bot.reply_to(message, "Waxaan soo dejinayaa faylkaaga...")
    tmp_in = tempfile.NamedTemporaryFile(delete=False, dir=DOWNLOADS_DIR)
    tmp_in_path = tmp_in.name
    tmp_in.close()
    tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir=DOWNLOADS_DIR)
    tmp_out_path = tmp_out.name
    tmp_out.close()
    created_files = [tmp_in_path, tmp_out_path]
    try:
        file_info = bot.get_file(media.file_id)
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        with requests.get(download_url, stream=True, timeout=REQUEST_TIMEOUT) as r:
            r.raise_for_status()
            with open(tmp_in_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        bot.edit_message_text("Processing...", message.chat.id, status_msg.message_id)
        subprocess.run(["ffmpeg", "-y", "-i", tmp_in_path, "-ar", "16000", "-ac", "1", "-b:a", "48k", tmp_out_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        duration = get_audio_duration(tmp_out_path)
        final_text = ""
        if duration > 1800:
            segment_pattern = os.path.join(DOWNLOADS_DIR, f"chunk_{os.path.basename(tmp_out_path)}_%03d.mp3")
            subprocess.run(["ffmpeg", "-i", tmp_out_path, "-f", "segment", "-segment_time", "1800", "-c", "copy", segment_pattern], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            chunk_files = sorted(glob.glob(segment_pattern.replace("%03d", "*")))
            for cf in chunk_files:
                created_files.append(cf)
                chunk_text = transcribe_local_file_groq(cf)
                if chunk_text:
                    final_text += chunk_text + " "
        else:
            final_text = transcribe_local_file_groq(tmp_out_path)
        if not final_text:
            raise ValueError("Transcription empty")
        bot.edit_message_text("Dhameystiran 😍", message.chat.id, status_msg.message_id)
        time.sleep(1)
        try:
            bot.delete_message(message.chat.id, status_msg.message_id)
        except:
            pass
        sent = send_long_text(message.chat.id, final_text, message.id, message.from_user.id)
        if sent:
            user_transcriptions.setdefault(message.chat.id, {})[sent.message_id] = {"text": final_text, "origin": message.id}
            if len(final_text) > 0:
                try:
                    bot.edit_message_reply_markup(message.chat.id, sent.message_id, reply_markup=build_action_keyboard(len(final_text)))
                except:
                    pass
    except Exception:
        bot.send_message(message.chat.id, "Waan ka xumahay, turjumiddu way fashilantay.")
    finally:
        for fpath in created_files:
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except:
                pass

def send_long_text(chat_id, text, reply_id, uid, action="Transcript"):
    if len(text) > MAX_MESSAGE_CHUNK:
        sent = None
        for i in range(0, len(text), MAX_MESSAGE_CHUNK):
            sent = bot.send_message(chat_id, text[i:i+MAX_MESSAGE_CHUNK], reply_to_message_id=reply_id)
        return sent
    sent = bot.send_message(chat_id, text, reply_to_message_id=reply_id)
    return sent

@bot.message_handler(func=lambda m: m.text in ["Ubax 👩🏻‍🦳", "Muuse 👨🏻‍🦱", "Codka wiilka 👶"])
def set_voice(message):
    choice = message.text
    uid_str = str(message.from_user.id)
    if "Ubax" in choice:
        vname = "so-SO-UbaxNeural"
        vlabel = "Ubax 👩🏻‍🦳"
    elif "Muuse" in choice and "wiilka" not in choice:
        vname = "so-SO-MuuseNeural"
        vlabel = "Muuse 👨🏻‍🦱"
    else:
        vname = "so-SO-MuuseNeural"
        vlabel = "Codka wiilka 👶"
        user_pitch_settings[uid_str] = 65
        upsert_user_setting(message.from_user.id, pitch=65)
    user_voice_name[uid_str] = vname
    user_voice_label[uid_str] = vlabel
    upsert_user_setting(message.from_user.id, voice_name=vname, voice_label=vlabel)
    bot.send_message(message.chat.id, "OK, ii soo dir qoraalka.", reply_to_message_id=message.message_id)

@bot.message_handler(commands=['rate'])
def cmd_rate(message):
    user_id = str(message.from_user.id)
    current = user_rate_settings.get(user_id, 0)
    bot.send_message(message.chat.id, "Halkan ka hagaaji xawaaraha:", reply_markup=rate_keyboard(current))

@bot.message_handler(commands=['pitch'])
def cmd_pitch(message):
    user_id = str(message.from_user.id)
    current = user_pitch_settings.get(user_id, 0)
    bot.send_message(message.chat.id, "Halkan ka hagaaji pitch-ka:", reply_markup=pitch_keyboard(current))

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith(("rate_", "pitch_")))
def slider_handler(call):
    uid = str(call.from_user.id)
    if call.data.startswith("rate_"):
        val = user_rate_settings.get(uid, 0)
        if call.data == "rate_up":
            val += 5
        elif call.data == "rate_down":
            val -= 5
        val = max(-100, min(100, val))
        user_rate_settings[uid] = val
        upsert_user_setting(call.from_user.id, rate=val)
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=rate_keyboard(val))
        except:
            pass
    elif call.data.startswith("pitch_"):
        val = user_pitch_settings.get(uid, 0)
        if call.data == "pitch_up":
            val += 5
        elif call.data == "pitch_down":
            val -= 5
        val = max(-100, min(100, val))
        user_pitch_settings[uid] = val
        upsert_user_setting(call.from_user.id, pitch=val)
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=pitch_keyboard(val))
        except:
            pass
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    user_id_str = str(message.from_user.id)
    try:
        admin_info = (
            f"@{message.from_user.username if message.from_user.username else 'No Username'}\n"
            f"Id: {message.from_user.id}\n"
            f"First: {message.from_user.first_name}\n"
            f"Lang: {message.from_user.language_code}\n"
            f"text {message.text}"
        )
        bot.send_message(ADMIN_CHAT_ID, admin_info)
    except:
        pass
    raw_text = message.text.replace("?", ", ")
    text = replace_numbers_with_words(raw_text)
    voice_name = user_voice_name.get(user_id_str, DEFAULT_VOICE_NAME)
    filename = generate_tts_filename(user_id_str)
    async def make_tts():
        pitch_val = user_pitch_settings.get(user_id_str, users_col.find_one({"user_id": message.from_user.id}, {"pitch": 1}) and users_col.find_one({"user_id": message.from_user.id}).get("pitch", 0) or 0)
        rate_val = user_rate_settings.get(user_id_str, users_col.find_one({"user_id": message.from_user.id}, {"rate": 1}) and users_col.find_one({"user_id": message.from_user.id}).get("rate", 0) or 0)
        pitch = f"+{pitch_val}Hz" if pitch_val >= 0 else f"{pitch_val}Hz"
        rate = f"+{rate_val}%" if rate_val >= 0 else f"{rate_val}%"
        tts = edge_tts.Communicate(text, voice_name, rate=rate, pitch=pitch)
        await tts.save(filename)
    stop_event = threading.Event()
    action_thread = threading.Thread(target=keep_sending_upload_action, args=(message.chat.id, stop_event))
    action_thread.daemon = True
    action_thread.start()
    try:
        asyncio.run(make_tts())
        with open(filename, "rb") as audio:
            bot.send_audio(
                message.chat.id,
                audio,
                reply_to_message_id=message.message_id,
                title=f"Codka_{user_id_str}_{int(time.time())}",
                performer="SomTTS Bot"
            )
    except Exception as e:
        try:
            bot.send_message(message.chat.id, f"Khalad: {e}", reply_to_message_id=message.message_id)
        except:
            pass
    finally:
        stop_event.set()
        try:
            if os.path.exists(filename):
                os.remove(filename)
        except:
            pass

def _process_webhook_update(raw):
    try:
        upd = Update.de_json(raw.decode('utf-8'))
        bot.process_new_updates([upd])
    except Exception as e:
        logging.exception("Error processing update: %s", e)

@flask_app.route("/", methods=["GET"])
def index():
    return "Bot-ka wuu socdaa💗", 200

@flask_app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type', '').startswith('application/json'):
        data = request.get_data()
        threading.Thread(target=_process_webhook_update, args=(data,), daemon=True).start()
        return '', 200
    abort(403)

if __name__ == "__main__":
    if WEBHOOK_URL:
        try:
            bot.remove_webhook()
        except:
            pass
        time.sleep(0.5)
        try:
            bot.set_webhook(url=WEBHOOK_URL)
        except:
            pass
        flask_app.run(host="0.0.0.0", port=PORT)
    else:
        print("Webhook URL lama dhisin, waan baxayaa.")
