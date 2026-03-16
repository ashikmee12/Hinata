import os
import logging
import json
import feedparser
import re
import threading
import asyncio
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Flask app for Render
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Animethic Bot is Running with Full Features!"

# ========== কনফিগারেশন ==========
BOT_TOKEN = os.environ.get('BOT_TOKEN')
GROUP_ID = int(os.environ.get('GROUP_ID', '-1002248871056'))
CHANNEL_ID = int(os.environ.get('CHANNEL_ID', '-1002225247609'))
ADMIN_ID = int(os.environ.get('ADMIN_ID', '7406197326'))
WEBSITE_URL = "https://www.animethic.in"
RSS_FEED_URL = "https://www.animethic.in/feeds/posts/default"

# ========== লগিং ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== JSON ফাইল ফাংশন ==========
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
        json.dump(data, f, indent=4, ensure_ascii=False)

# ========== ডাটাবেস ==========
users_db = load_json('users.json', {})
settings_db = load_json('settings.json', {
    "welcome_message": "Welcome {name} to the group!\n\n📌 Rules:\n• Only anime related discussions\n• No sharing external links\n• Use /anime [name] to search anime",
    "welcome_enabled": True,
    "link_filter_enabled": True,
    "auto_mute_enabled": True,
    "poster_enabled": True,
    "max_warnings": 3,
    "mute_duration": 60,
    "allowed_domains": ["animethic.in", "www.animethic.in"],
    "last_post_id": None
})
stats_db = load_json('stats.json', {
    "total_requests": 0,
    "total_warnings": 0,
    "total_mutes": 0,
    "total_bans": 0,
    "anime_requests": {},
    "user_requests": {}
})

# ========== ইউজার ম্যানেজমেন্ট ==========
def get_user_data(user_id):
    user_id = str(user_id)
    if user_id not in users_db:
        users_db[user_id] = {
            "warnings": 0,
            "is_muted": False,
            "mute_until": None,
            "is_banned": False,
            "is_trusted": False,
            "join_date": str(datetime.now()),
            "total_requests": 0
        }
        save_json('users.json', users_db)
    return users_db[user_id]

def save_user_data(user_id, data):
    users_db[str(user_id)] = data
    save_json('users.json', users_db)

def add_warning(user_id, reason=""):
    user_id = str(user_id)
    user_data = get_user_data(user_id)
    user_data["warnings"] += 1
    user_data["last_warning"] = str(datetime.now())
    user_data["last_warning_reason"] = reason
    save_user_data(user_id, user_data)
    stats_db["total_warnings"] += 1
    save_json('stats.json', stats_db)
    return user_data["warnings"]

def clear_warnings(user_id):
    user_id = str(user_id)
    user_data = get_user_data(user_id)
    user_data["warnings"] = 0
    save_user_data(user_id, user_data)
    return True

def mute_user(user_id, duration_minutes):
    user_id = str(user_id)
    user_data = get_user_data(user_id)
    user_data["is_muted"] = True
    user_data["mute_until"] = str(datetime.now() + timedelta(minutes=duration_minutes))
    save_user_data(user_id, user_data)
    stats_db["total_mutes"] += 1
    save_json('stats.json', stats_db)
    return True

def unmute_user(user_id):
    user_id = str(user_id)
    user_data = get_user_data(user_id)
    user_data["is_muted"] = False
    user_data["mute_until"] = None
    save_user_data(user_id, user_data)
    return True

def ban_user(user_id, reason=""):
    user_id = str(user_id)
    user_data = get_user_data(user_id)
    user_data["is_banned"] = True
    user_data["ban_reason"] = reason
    user_data["ban_date"] = str(datetime.now())
    save_user_data(user_id, user_data)
    stats_db["total_bans"] += 1
    save_json('stats.json', stats_db)
    return True

def unban_user(user_id):
    user_id = str(user_id)
    user_data = get_user_data(user_id)
    user_data["is_banned"] = False
    user_data.pop("ban_reason", None)
    user_data.pop("ban_date", None)
    save_user_data(user_id, user_data)
    return True

def is_admin(user_id):
    return user_id == ADMIN_ID

# ========== ল্যাঙ্গুয়েজ ডিটেকশন ==========
def is_anime_request(text):
    if not text:
        return False
    
    text = text.lower().strip()
    
    ignore_patterns = [
        r'^(hi|hello|hey|hlw|hy|hlo)',
        r'^(good morning|good afternoon|good evening)',
        r'^(bye|tata|allah hafez)',
        r'^(thanks|thank you|thanks)',
        r'^(ok|okay|k|thik ache)',
    ]
    
    for pattern in ignore_patterns:
        if re.match(pattern, text, re.IGNORECASE):
            return False
    
    anime_keywords = [
        'anime', 'naruto', 'one piece', 'demon slayer', 'attack on titan',
        'season', 'episode', 'ep', 'dubbed', 'subbed', 'hindi', 'english',
        'watch', 'download', 'stream', 'online', 'free', 'bleach', 'jujutsu',
        'kaisen', 'aot', 'chainsaw man', 'spy x family', 'my hero academia'
    ]
    
    for keyword in anime_keywords:
        if keyword in text:
            return True
    
    words = text.split()
    for word in words:
        if len(word) > 2 and word[0].isupper():
            return True
    
    return False

def is_add_request(text):
    if not text:
        return False
    
    text = text.lower().strip()
    
    add_patterns = [
        'add', 'যোগ', 'add koro', 'add karo',
        'upload', 'dal do', 'dalo',
        'please add', 'plz add', 'can you add'
    ]
    
    for pattern in add_patterns:
        if pattern in text:
            return True
    
    return False

def extract_anime_name(text):
    common_words = [
        'anime', 'download', 'watch', 'stream', 'episode', 'season',
        'dubbed', 'hindi', 'english', 'sub', 'subbed', 
        'free', 'online', 'please', 'plz', 'ep', 'naruto', 'one piece',
        'demon slayer', 'attack on titan', 'aot', 'bleach', 'jujutsu'
    ]
    
    text = text.lower()
    for word in common_words:
        text = text.replace(word, '')
    
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def extract_season_episode(text):
    season_match = re.search(r'season\s*(\d+)', text.lower())
    episode_match = re.search(r'episode\s*(\d+)', text.lower())
    ep_match = re.search(r'ep\s*(\d+)', text.lower())
    
    return {
        'season': int(season_match.group(1)) if season_match else None,
        'episode': int(episode_match.group(1)) if episode_match else (int(ep_match.group(1)) if ep_match else None)
    }

def match_season_episode(query, title):
    query_se = extract_season_episode(query)
    title_se = extract_season_episode(title)
    
    if query_se['season']:
        if title_se['season'] and title_se['season'] == query_se['season']:
            return True
        else:
            return False
    
    if query_se['episode']:
        if title_se['episode'] and title_se['episode'] == query_se['episode']:
            return True
        else:
            return False
    
    return True

# ========== ফাজি সার্চ ==========
def fuzzy_match(query, text):
    return SequenceMatcher(None, query.lower(), text.lower()).ratio()

def search_anime_in_posts(query, posts):
    if not posts:
        return []
    
    results = []
    query = query.lower().strip()
    
    for post in posts:
        title = post.get('title', '')
        link = post.get('link', '')
        
        title_clean = re.sub(r'season\s*\d+|episode\s*\d+|ep\s*\d+', '', title.lower())
        query_clean = re.sub(r'season\s*\d+|episode\s*\d+|ep\s*\d+', '', query.lower())
        
        if query_clean in title_clean:
            score = 1.0
        else:
            score = fuzzy_match(query_clean, title_clean)
        
        if score > 0.6:
            results.append({
                'title': title,
                'link': link,
                'score': score
            })
    
    results.sort(key=lambda x: x['score'], reverse=True)
    return results

# ========== RSS ফিড ==========
def get_latest_posts():
    try:
        feed = feedparser.parse(RSS_FEED_URL)
        posts = []
        for entry in feed.entries[:20]:
            posts.append({
                'title': entry.title,
                'link': entry.link,
                'published': entry.published if hasattr(entry, 'published') else ''
            })
        return posts
    except Exception as e:
        logger.error(f"RSS Feed error: {e}")
        return []

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

# ========== লিংক ফিল্টার ==========
def extract_links(text):
    url_pattern = r'https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?'
    return re.findall(url_pattern, text, re.IGNORECASE)

def is_allowed_domain(url):
    for domain in settings_db.get("allowed_domains", []):
        if domain in url:
            return True
    return False

def contains_forbidden_links(text):
    if not settings_db.get("link_filter_enabled", True):
        return False
    
    links = extract_links(text)
    if not links:
        return False
    
    for link in links:
        if not is_allowed_domain(link):
            return True
    
    return False

# ========== টেলিগ্রাম হ্যান্ডলার ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Animethic Bot!\n\n"
        "🔍 **How to use:**\n"
        "Just type any anime name (e.g., Naruto Season 9, One Piece Episode 1000)\n\n"
        "📌 **Commands:**\n"
        "/anime [name] - Search anime\n"
        "/help - Show help"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 **Help Guide**\n\n"
        "**User Commands:**\n"
        "/start - Start the bot\n"
        "/help - Show this help\n"
        "/anime [name] - Search for anime\n\n"
        "**Admin Commands (Only for you):**\n"
        "/stats - View statistics\n"
        "/warn @user - Give warning\n"
        "/clearwarn @user - Clear warnings\n"
        "/mute @user [minutes] - Mute user\n"
        "/unmute @user - Unmute user\n"
        "/ban @user - Ban user\n"
        "/unban @user - Unban user\n"
        "/check @user - Check user info\n"
        "/adddomain example.com - Add allowed domain\n"
        "/removedomain example.com - Remove domain\n"
        "/listdomains - List allowed domains\n"
        "/setwelcome [message] - Set welcome message\n"
        "/welcome on/off - Enable/disable welcome\n"
        "/filter on/off - Enable/disable link filter\n"
        "/poster on/off - Enable/disable auto poster\n"
        "/poster now - Post now"
    )
    await update.message.reply_text(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user = update.message.from_user
    user_id = user.id
    chat_id = update.message.chat_id
    text = update.message.text
    
    if chat_id != GROUP_ID:
        return
    
    user_data = get_user_data(user_id)
    
    if user_data.get("is_banned", False):
        try:
            await update.message.delete()
        except:
            pass
        return
    
    if user_data.get("is_muted", False):
        mute_until = user_data.get("mute_until")
        if mute_until:
            mute_time = datetime.fromisoformat(mute_until)
            if datetime.now() < mute_time:
                try:
                    await update.message.delete()
                except:
                    pass
                return
            else:
                unmute_user(user_id)
    
    if contains_forbidden_links(text):
        try:
            await update.message.delete()
            warnings = add_warning(user_id, "Forbidden link")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.mention_html()} posted a forbidden link!\nWarning: {warnings}/{settings_db.get('max_warnings', 3)}",
                parse_mode='HTML'
            )
            if warnings >= settings_db.get('max_warnings', 3):
                mute_duration = settings_db.get('mute_duration', 60)
                mute_user(user_id, mute_duration)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔇 {user.mention_html()} muted for {mute_duration} minutes!",
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
        return
    
    if is_add_request(text):
        return
    
    if is_anime_request(text):
        stats_db["total_requests"] += 1
        user_data["total_requests"] += 1
        user_data["last_request"] = str(datetime.now())
        save_user_data(user_id, user_data)
        
        anime_name = extract_anime_name(text)
        
        if not anime_name:
            return
        
        posts = get_latest_posts()
        results = search_anime_in_posts(anime_name, posts)
        
        filtered_results = []
        for result in results:
            if match_season_episode(text, result['title']):
                filtered_results.append(result)
        
        if filtered_results:
            for result in filtered_results[:3]:
                title = result['title']
                stats_db["anime_requests"][title] = stats_db["anime_requests"].get(title, 0) + 1
            
            reply = f"🔍 Found for '{text}':\n\n"
            for i, result in enumerate(filtered_results[:3], 1):
                reply += f"{i}. **{result['title']}**\n"
                reply += f"📥 [Download Here]({result['link']})\n\n"
            
            await update.message.reply_text(reply, parse_mode='Markdown', disable_web_page_preview=True)
        else:
            reply = (
                f"🔍 '{text}' not found on our website.\n\n"
                f"Possible reasons:\n"
                f"• Spelling might be wrong\n"
                f"• Anime not released yet\n"
                f"• Not added to website yet\n\n"
                f"📞 Contact: @animethic_admin_bot"
            )
            await update.message.reply_text(reply)
        
        save_json('stats.json', stats_db)

async def anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("📝 Usage: /anime [anime name]")
        return
    
    query = ' '.join(context.args)
    
    posts = get_latest_posts()
    results = search_anime_in_posts(query, posts)
    
    filtered_results = []
    for result in results:
        if match_season_episode(query, result['title']):
            filtered_results.append(result)
    
    if filtered_results:
        reply = f"🔍 Found for '{query}':\n\n"
        for i, result in enumerate(filtered_results[:3], 1):
            reply += f"{i}. **{result['title']}**\n"
            reply += f"📥 [Download Here]({result['link']})\n\n"
        
        await update.message.reply_text(reply, parse_mode='Markdown', disable_web_page_preview=True)
        
        stats_db["total_requests"] += 1
        save_json('stats.json', stats_db)
    else:
        reply = (
            f"🔍 '{query}' not found on our website.\n\n"
            f"Possible reasons:\n"
            f"• Spelling might be wrong\n"
            f"• Anime not released yet\n"
            f"• Not added to website yet\n\n"
            f"📞 Contact: @animethic_admin_bot"
        )
        await update.message.reply_text(reply)

async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not settings_db.get("welcome_enabled", True):
        return
    
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        
        welcome_text = settings_db.get("welcome_message", "Welcome {name}!")
        welcome_text = welcome_text.replace("{name}", member.first_name)
        welcome_text = welcome_text.replace("{mention}", member.mention_html())
        
        await update.message.reply_text(welcome_text, parse_mode='HTML')
        get_user_data(member.id)

# ========== অ্যাডমিন কমান্ড ==========
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission!")
        return
    
    stats_text = (
        f"📊 **Bot Statistics**\n\n"
        f"📝 Total Requests: {stats_db['total_requests']}\n"
        f"⚠️ Total Warnings: {stats_db['total_warnings']}\n"
        f"🔇 Total Mutes: {stats_db['total_mutes']}\n"
        f"🚫 Total Bans: {stats_db['total_bans']}\n"
        f"👥 Total Users: {len(users_db)}\n\n"
        f"**Top 5 Anime:**\n"
    )
    
    top_anime = sorted(stats_db['anime_requests'].items(), key=lambda x: x[1], reverse=True)[:5]
    for i, (anime, count) in enumerate(top_anime, 1):
        short_anime = anime[:30] + "..." if len(anime) > 30 else anime
        stats_text += f"{i}. {short_anime} - {count} times\n"
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message with /warn")
        return
    
    target_user = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) if context.args else "No reason"
    warnings = add_warning(target_user.id, reason)
    
    await update.message.reply_text(
        f"⚠️ {target_user.mention_html()} warned!\nReason: {reason}\nWarnings: {warnings}",
        parse_mode='HTML'
    )

async def clearwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message with /clearwarn")
        return
    
    target_user = update.message.reply_to_message.from_user
    clear_warnings(target_user.id)
    
    await update.message.reply_text(
        f"✅ Warnings cleared for {target_user.mention_html()}!",
        parse_mode='HTML'
    )

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message with /mute")
        return
    
    target_user = update.message.reply_to_message.from_user
    duration = 60
    if context.args:
        try:
            duration = int(context.args[0])
        except:
            pass
    
    mute_user(target_user.id, duration)
    
    await update.message.reply_text(
        f"🔇 {target_user.mention_html()} muted for {duration} minutes!",
        parse_mode='HTML'
    )

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message with /unmute")
        return
    
    target_user = update.message.reply_to_message.from_user
    unmute_user(target_user.id)
    
    await update.message.reply_text(
        f"✅ {target_user.mention_html()} unmuted!",
        parse_mode='HTML'
    )

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message with /ban")
        return
    
    target_user = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) if context.args else "No reason"
    
    ban_user(target_user.id, reason)
    
    await update.message.reply_text(
        f"🚫 {target_user.mention_html()} banned!\nReason: {reason}",
        parse_mode='HTML'
    )
    
    try:
        await context.bot.ban_chat_member(GROUP_ID, target_user.id)
    except:
        pass

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message with /unban")
        return
    
    target_user = update.message.reply_to_message.from_user
    unban_user(target_user.id)
    
    await update.message.reply_text(
        f"✅ {target_user.mention_html()} unbanned!",
        parse_mode='HTML'
    )
    
    try:
        await context.bot.unban_chat_member(GROUP_ID, target_user.id)
    except:
        pass

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message with /check")
        return
    
    target_user = update.message.reply_to_message.from_user
    user_data = get_user_data(target_user.id)
    
    info_text = (
        f"👤 **User Info:** {target_user.mention_html()}\n"
        f"🆔 ID: `{target_user.id}`\n"
        f"⚠️ Warnings: {user_data.get('warnings', 0)}\n"
        f"🔇 Muted: {'Yes' if user_data.get('is_muted') else 'No'}\n"
        f"🚫 Banned: {'Yes' if user_data.get('is_banned') else 'No'}\n"
        f"⭐ Trusted: {'Yes' if user_data.get('is_trusted') else 'No'}\n"
        f"📊 Total Requests: {user_data.get('total_requests', 0)}\n"
        f"📅 Joined: {user_data.get('join_date', 'N/A')[:10]}"
    )
    
    await update.message.reply_text(info_text, parse_mode='HTML')

async def adddomain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not context.args:
        await update.message.reply_text("📝 Usage: /adddomain example.com")
        return
    
    domain = context.args[0].lower().replace('https://', '').replace('http://', '').replace('www.', '')
    
    if domain in settings_db["allowed_domains"]:
        await update.message.reply_text(f"⚠️ {domain} already in list!")
        return
    
    settings_db["allowed_domains"].append(domain)
    save_json('settings.json', settings_db)
    
    await update.message.reply_text(f"✅ {domain} added!")

async def removedomain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not context.args:
        await update.message.reply_text("📝 Usage: /removedomain example.com")
        return
    
    domain = context.args[0].lower().replace('https://', '').replace('http://', '').replace('www.', '')
    
    if domain not in settings_db["allowed_domains"]:
        await update.message.reply_text(f"⚠️ {domain} not in list!")
        return
    
    settings_db["allowed_domains"].remove(domain)
    save_json('settings.json', settings_db)
    
    await update.message.reply_text(f"✅ {domain} removed!")

async def listdomains_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    domains = settings_db["allowed_domains"]
    if domains:
        text = "📋 **Allowed Domains:**\n\n"
        for i, domain in enumerate(domains, 1):
            text += f"{i}. {domain}\n"
    else:
        text = "⚠️ No domains allowed!"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def setwelcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not context.args:
        await update.message.reply_text("📝 Usage: /setwelcome [message]")
        return
    
    welcome_text = ' '.join(context.args)
    settings_db["welcome_message"] = welcome_text
    save_json('settings.json', settings_db)
    
    await update.message.reply_text(f"✅ Welcome message updated!\n\n{welcome_text}")

async def welcome_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("📝 Usage: /welcome on OR off")
        return
    
    status = context.args[0].lower() == 'on'
    settings_db["welcome_enabled"] = status
    save_json('settings.json', settings_db)
    
    await update.message.reply_text(f"✅ Welcome {'enabled' if status else 'disabled'}!")

async def filter_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("📝 Usage: /filter on OR off")
        return
    
    status = context.args[0].lower() == 'on'
    settings_db["link_filter_enabled"] = status
    save_json('settings.json', settings_db)
    
    await update.message.reply_text(f"✅ Filter {'enabled' if status else 'disabled'}!")

async def poster_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        await update.message.reply_text("📝 Usage: /poster on OR off")
        return
    
    status = context.args[0].lower() == 'on'
    settings_db["poster_enabled"] = status
    save_json('settings.json', settings_db)
    
    await update.message.reply_text(f"✅ Auto poster {'enabled' if status else 'disabled'}!")

async def poster_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ No permission!")
        return
    
    await update.message.reply_text("🔄 Checking for new posts...")
    await auto_poster(context)

# ========== অটো পোস্টার ==========
async def auto_poster(context: ContextTypes.DEFAULT_TYPE):
    if not settings_db.get("poster_enabled", True):
        return
    
    new_posts = check_new_posts()
    
    for post in new_posts:
        try:
            message = f"📢 **New Post!**\n\n**{post['title']}**\n\n📥 [Download Here]({post['link']})"
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=message,
                parse_mode='Markdown'
            )
            logger.info(f"Posted to channel: {post['title']}")
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Post error: {e}")

# ========== মেইন ফাংশন ==========
def main():
    threading.Thread(target=lambda: app_flask.run(host='0.0.0.0', port=8080, debug=False)).start()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("anime", anime_command))
    
    # Admin commands
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("clearwarn", clearwarn_command))
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("adddomain", adddomain_command))
    app.add_handler(CommandHandler("removedomain", removedomain_command))
    app.add_handler(CommandHandler("listdomains", listdomains_command))
    app.add_handler(CommandHandler("setwelcome", setwelcome_command))
    app.add_handler(CommandHandler("welcome", welcome_toggle))
    app.add_handler(CommandHandler("filter", filter_toggle))
    app.add_handler(CommandHandler("poster", poster_toggle))
    app.add_handler(CommandHandler("posternow", poster_now))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Job queue
    app.job_queue.run_repeating(auto_poster, interval=600, first=10)
    
    logger.info("Bot started! Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
