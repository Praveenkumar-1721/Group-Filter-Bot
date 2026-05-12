import telebot
from telebot import types
from pymongo import MongoClient
from flask import Flask
from threading import Thread
import time
import os

# --- SETTINGS ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URL = os.environ.get("MONGO_URL")

# Unnaoda Telegram ID inga set panniten 👇
ADMIN_ID = 5217849239  

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- MONGODB CONNECTION ---
client = MongoClient(MONGO_URL)
db = client['CinemxticDB']       
collection = db['movies']        

# Smart search-ku index create panrom
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
        movie_name = " ".join(parts[1:-1]).lower()
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
        movie_name = parts[1].lower()
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

# --- 5. SMART AUTO FILTER ---
@bot.message_handler(func=lambda message: True)
def filter_movies(message):
    if message.text.startswith('/'):
        return
    search_query = message.text.lower()
    # First exact match, then smart search
    movie = collection.find_one({"name": search_query})
    if not movie:
        movie = collection.find_one({"$text": {"$search": search_query}})
    
    if movie:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🍿 Download Movie", url=movie['link']))
        reply = f"🎬 **{movie['name'].title()}**\n\nHey {message.from_user.first_name}, unga movie ready! 👇\n\n_⚠️ Deleted in 5 mins._"
        sent = bot.reply_to(message, reply, reply_markup=markup, parse_mode="Markdown")
        Thread(target=delete_msg, args=(message.chat.id, sent.message_id)).start()

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
    
