import os
import logging
import json
import feedparser
import re
import threading
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Flask app for Render
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Animethic Bot is Running!"

# Telegram Bot Configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN')
GROUP_ID = int(os.environ.get('GROUP_ID', '-1002248871056'))
CHANNEL_ID = int(os.environ.get('CHANNEL_ID', '-1002225247609'))
ADMIN_ID = int(os.environ.get('ADMIN_ID', '7406197326'))
WEBSITE_URL = "https://www.animethic.in"
RSS_FEED_URL = "https://www.animethic.in/feeds/posts/default"

# Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# JSON functions
def load_json(filename, default_data):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default_data
    return default_data

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# Settings
settings_db = load_json('settings.json', {
    "last_post_id": None,
    "allowed_domains": ["animethic.in", "www.animethic.in"]
})

# Get latest posts from RSS
def get_latest_posts():
    try:
        feed = feedparser.parse(RSS_FEED_URL)
        posts = []
        for entry in feed.entries[:10]:
            posts.append({
                'title': entry.title,
                'link': entry.link
            })
        return posts
    except Exception as e:
        logger.error(f"RSS error: {e}")
        return []

# Check for new posts
def check_new_posts():
    posts = get_latest_posts()
    if not posts:
        return []
    
    new_posts = []
    last_id = settings_db.get("last_post_id")
    
    for post in posts:
        if post['link'] != last_id:
            new_posts.append(post)
        else:
            break
    
    if new_posts:
        settings_db["last_post_id"] = new_posts[0]['link']
        save_json('settings.json', settings_db)
    
    return new_posts[::-1]

# Fuzzy search
def search_anime(query, posts):
    results = []
    query = query.lower()
    
    for post in posts:
        title = post['title'].lower()
        if query in title:
            results.append(post)
        else:
            ratio = SequenceMatcher(None, query, title).ratio()
            if ratio > 0.6:
                results.append(post)
    
    return results[:3]

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Animethic Bot!\n\n"
        "Just type anime name (e.g., Naruto Season 9)\n"
        "I'll search and give you download link."
    )

# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    # Only work in group
    if update.message.chat_id != GROUP_ID:
        return
    
    text = update.message.text
    
    # Ignore add requests
    if 'add' in text.lower() or 'যোগ' in text.lower():
        return
    
    # Check if anime request
    anime_keywords = ['anime', 'naruto', 'one piece', 'season', 'episode', 'demon slayer']
    is_anime = any(keyword in text.lower() for keyword in anime_keywords)
    
    if is_anime:
        posts = get_latest_posts()
        results = search_anime(text, posts)
        
        if results:
            reply = f"🔍 Found for '{text}':\n\n"
            for i, post in enumerate(results, 1):
                reply += f"{i}. **{post['title']}**\n"
                reply += f"📥 [Download Here]({post['link']})\n\n"
            await update.message.reply_text(reply, parse_mode='Markdown')
        else:
            reply = f"🔍 '{text}' not found.\n\n📞 Contact: @animethic_admin_bot"
            await update.message.reply_text(reply)

# Auto poster
async def auto_poster(context: ContextTypes.DEFAULT_TYPE):
    new_posts = check_new_posts()
    for post in new_posts:
        try:
            message = f"📢 **New Post!**\n\n**{post['title']}**\n\n📥 [Download Here]({post['link']})"
            await context.bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='Markdown')
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Post error: {e}")

# Main function
def main():
    # Start Flask in thread
    threading.Thread(target=lambda: app_flask.run(host='0.0.0.0', port=8080)).start()
    
    # Start bot
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.job_queue.run_repeating(auto_poster, interval=600, first=10)
    app.run_polling()

if __name__ == "__main__":
    main()
