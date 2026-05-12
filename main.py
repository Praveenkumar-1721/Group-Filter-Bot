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

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- MONGODB CONNECTION ---
client = MongoClient(MONGO_URL)
db = client['CinemxticDB']       # Database Name
collection = db['movies']        # Table Name

# --- WEB SERVER (For 24/7) ---
@app.route('/')
def home():
    return "Group Filter Bot is Running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    Thread(target=run_web).start()

# --- AUTO DELETE MESSAGE ---
def delete_msg(chat_id, msg_id):
    time.sleep(300) # 5 Minutes (300 seconds)
    try:
        bot.delete_message(chat_id, msg_id)
    except:
        pass

# --- 1. START COMMAND ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 Hi! Add me to your group. I will auto-reply with movie links!")

# --- 2. ADD MOVIE COMMAND (Admin Use) ---
@bot.message_handler(commands=['add'])
def add_movie(message):
    # Command Format: /add Kaalidas 2 https://t.me/bot?start=123
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "❌ Format Thappu!\nCorrect Format: `/add Movie Name Link`", parse_mode="Markdown")
            return
            
        link = parts[-1] # Last word dhaan link
        movie_name = " ".join(parts[1:-1]).lower() # Nadula irukradhu fulla movie name
        
        if not link.startswith("http"):
            bot.reply_to(message, "❌ Last word kandippa link-ah dhaan irukkanum!")
            return

        # DB la Save panrom
        collection.update_one(
            {"name": movie_name},
            {"$set": {"name": movie_name, "link": link}},
            upsert=True
        )
        bot.reply_to(message, f"✅ **Movie Added to DB!**\n\n🎬 Name: {movie_name.title()}\n🔗 Link: {link}", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, "❌ Error saving movie.")

# --- 3. MASTER UPDATE TOOL (Bot Ban aana use panradhu) ---
@bot.message_handler(commands=['update_bot'])
def update_bot_links(message):
    # Command Format: /update_bot old_bot_username new_bot_username
    try:
        parts = message.text.split()
        if len(parts) != 3:
            bot.reply_to(message, "❌ Format: `/update_bot old_username new_username`", parse_mode="Markdown")
            return
            
        old_bot = parts[1]
        new_bot = parts[2]
        
        # DB-la thedi replace panrom
        movies = collection.find({"link": {"$regex": old_bot}})
        count = 0
        for mov in movies:
            new_link = mov['link'].replace(old_bot, new_bot)
            collection.update_one({"_id": mov['_id']}, {"$set": {"link": new_link}})
            count += 1
            
        bot.reply_to(message, f"💥 **MAGIC DONE!**\n\nSuccessfully updated {count} movie links to the new bot!")
    except Exception as e:
        bot.reply_to(message, "❌ Error updating links.")

# --- 4. AUTO FILTER (Group-la reply panradhu) ---
@bot.message_handler(func=lambda message: True)
def filter_movies(message):
    # '/' vachu start aana adhu command, so ignore pannidalam
    if message.text.startswith('/'):
        return
        
    search_query = message.text.lower()
    
    # DB-la movie name irukka nu thedurom
    movie = collection.find_one({"name": search_query})
    
    if movie:
        movie_name = movie['name'].title()
        link = movie['link']
        
        # Link-a professional-a button la vaikkurom (looks very neat in groups)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🍿 Download Movie", url=link))
        
        reply_text = f"🎬 **{movie_name}**\n\nHey {message.from_user.first_name}, your movie is ready! Click the button below. 👇\n\n_⚠️ This message will be deleted in 5 minutes._"
        
        sent_msg = bot.reply_to(message, reply_text, reply_markup=markup, parse_mode="Markdown")
        
        # 5 mins-la auto delete start aagudhu
        Thread(target=delete_msg, args=(message.chat.id, sent_msg.message_id)).start()

if __name__ == "__main__":
    keep_alive()
    bot.infinity_polling()
  
