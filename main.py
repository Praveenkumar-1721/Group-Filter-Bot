import telebot
from telebot import types
from pymongo import MongoClient
from flask import Flask
from threading import Thread
import time
import os
import re

# --- SETTINGS ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URL = os.environ.get("MONGO_URL")
ADMIN_ID = 5217849239  

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- MONGODB CONNECTION ---
client = MongoClient(MONGO_URL)
db = client['CinemxticDB']       
collection = db['movies']        

# Smart Search Index
collection.create_index([("name", "text")])

# --- WEB SERVER (For 24/7 Render) ---
@app.route('/')
def home():
    return "Group Filter Bot is Running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    Thread(target=run_web).start()

# --- AUTO DELETE MESSAGE ---
def delete_msg(chat_id, msg_id):
    time.sleep(300) # 5 Minutes
    try:
        bot.delete_message(chat_id, msg_id)
    except:
        pass

# --- HELPER: TEXT NORMALIZER ---
def normalize_text(text):
    text = text.lower().strip()
    # Punctuation / brackets remove panrom
    text = re.sub(r'[\(\)\[\]\{\}\-_,\.]', ' ', text)
    # "season 3" / "season 03" -> "s03" (standardize)
    text = re.sub(r'\bseason\s*0*(\d+)\b', lambda m: f"s{int(m.group(1)):02d}", text)
    # "s 3" or "s3" -> "s03"
    text = re.sub(r'\bs\s*0*(\d+)\b', lambda m: f"s{int(m.group(1)):02d}", text)
    # Extra spaces clean panrom
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# --- 1. START COMMAND ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 Hi! Add me to your group. I will auto-reply with movie links!")

# --- 2. ADD MOVIE COMMAND (Admin Only) ---
@bot.message_handler(commands=['add'])
def add_movie(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "❌ Format: `/add Movie Name Link`", parse_mode="Markdown")
            return
        link = parts[-1]
        movie_name = " ".join(parts[1:-1]).lower().strip()
        collection.update_one(
            {"name": movie_name},
            {"$set": {"name": movie_name, "link": link}},
            upsert=True
        )
        bot.reply_to(message, f"✅ **Added!**\n🎬 {movie_name.title()}\n🔗 {link}", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Error saving movie.")

# --- 3. DELETE MOVIE COMMAND (Admin Only) ---
@bot.message_handler(commands=['del', 'delete'])
def delete_movie(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "❌ Format: `/del Movie Name`", parse_mode="Markdown")
            return
        movie_name = parts[1].lower().strip()
        result = collection.delete_one({"name": movie_name})
        if result.deleted_count > 0:
            bot.reply_to(message, f"🗑️ **Deleted:** {movie_name.title()}", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Movie not found!")
    except:
        bot.reply_to(message, "❌ Error deleting movie.")

# --- 4. MASTER UPDATE TOOL (Bot Ban Recovery) ---
@bot.message_handler(commands=['update_bot'])
def update_bot_links(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "❌ Format: `/update_bot old_bot new_bot`", parse_mode="Markdown")
            return
        old_bot, new_bot = parts[1], parts[2]
        movies = collection.find({"link": {"$regex": old_bot}})
        count = 0
        for mov in movies:
            new_link = mov['link'].replace(old_bot, new_bot)
            collection.update_one({"_id": mov['_id']}, {"$set": {"link": new_link}})
            count += 1
        bot.reply_to(message, f"💥 **Updated {count} links successfully!**")
    except:
        bot.reply_to(message, "❌ Error updating links.")

# --- 5. SMART AUTO FILTER (Simple Core Match) ---
@bot.message_handler(func=lambda message: True)
def filter_movies(message):
    if message.text.startswith('/'):
        return
        
    user_msg = message.text.lower().strip()
    
    # Noise words-a thevaillaama compare panna koodadhu
    noise_words = {
        "movie", "film", "download", "link", "send", "please", "bro", 
        "da", "tamil", "telugu", "hindi", "english", "hd", "1080p", 
        "720p", "480p", "mp4", "mkv", "dubbed"
    }
    
    found_movies = []
    seen_links = set()
    all_movies = collection.find()
    
    for m in all_movies:
        db_title = m['name'].lower().strip()
        
        # 1. Direct match check (Full title user text-kulla irundha)
        if db_title in user_msg or user_msg in db_title:
            if m['link'] not in seen_links:
                found_movies.append(m)
                seen_links.add(m['link'])
            continue
            
        # 2. Main title words check (Session/Season/Numbers thavirthu mukkiyamana words)
        # DB title-la irukka words-a edukkurom
        raw_db_words = [w.strip("()[]{}.-_") for w in db_title.split()]
        core_db_words = [w for w in raw_db_words if w and w not in noise_words and not w.startswith('s0') and not w.startswith('s1') and not w.isdigit()]
        
        # Core words (Ex: ['stranger', 'things']) user message-kulla irundha match!
        if core_db_words:
            matched_words = [w for w in core_db_words if w in user_msg]
            # Core words ellame user text-la irundha send pannu
            if len(matched_words) == len(core_db_words):
                if m['link'] not in seen_links:
                    found_movies.append(m)
                    seen_links.add(m['link'])

    if found_movies:
        # 👍 Reaction to user msg
        try:
            bot.set_message_reaction(message.chat.id, message.message_id, [types.ReactionTypeEmoji('👍')], is_big=False)
        except:
            pass

        markup = types.InlineKeyboardMarkup()
        for movie in found_movies:
            btn_text = f"🍿 {movie['name'].title()}"
            markup.add(types.InlineKeyboardButton(btn_text, url=movie['link']))
        
        reply_text = f"🎬 **Found {len(found_movies)} results!**\n\nHey {message.from_user.first_name}, unga movies ready! 👇\n\n_⚠️ Deleted in 5 mins._"
        
        sent_msg = bot.reply_to(message, reply_text, reply_markup=markup, parse_mode="Markdown")
        
        # 5 mins-la auto delete
        Thread(target=delete_msg, args=(message.chat.id, sent_msg.message_id)).start()


if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
