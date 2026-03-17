#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
অ্যানিমেথিক আলট্রা বট v5.0 - Blogger API v3 সহ
"""

import os
import logging
import json
import requests  # API কলের জন্য
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

# ========== কনফিগারেশন ==========
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '7406197326'))
GROUP_ID = int(os.environ.get('GROUP_ID', '-1002248871056'))
CHANNEL_ID = int(os.environ.get('CHANNEL_ID', '-1002225247609'))
WEBSITE_URL = "https://www.animethic.in"

# Blogger API v3 কনফিগ
BLOG_ID = os.environ.get('BLOG_ID', '6445429841925204092')  # আপনার Blog ID
API_KEY = os.environ.get('API_KEY', 'AIzaSyBd-2MBVvEpJMH1J8xfhT8uzDbxARaDc6Q')  # আপনার API Key

# Flask app for Render
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Animethic Ultra Bot v5.0 with Blogger API is Running!"

# ========== লগিং ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== JSON ফাইল ফাংশন ==========
def load_json(filename, default_data):
    """JSON ফাইল লোড করে"""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
            return default_data
    return default_data

def save_json(filename, data):
    """JSON ফাইল সেভ করে"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")

# ========== ডাটাবেস ইনিশিয়ালাইজ ==========
users_db = load_json('users.json', {})
stats_db = load_json('stats.json', {
    "total_requests": 0,
    "total_warnings": 0,
    "total_mutes": 0,
    "total_bans": 0,
    "anime_requests": {},
    "user_requests": {},
    "daily_requests": 0,
    "daily_users": 0
})

# ========== সেটিংস ডাটাবেস ==========
settings_db = load_json('settings.json', {
    # মাস্টার সুইচ
    "bot_enabled": True,
    
    # বেসিক সেটিংস
    "welcome_message": "👋 স্বাগতম {name} গ্রুপে!\n\n📌 নিয়মাবলী:\n• শুধু অ্যানিমে নিয়ে কথা বলুন\n• বাহিরের লিংক শেয়ার করবেন না\n• অ্যানিমে খুঁজতে নাম লিখুন",
    "welcome_enabled": True,
    "link_filter_enabled": True,
    "poster_enabled": True,
    
    # অ্যালাউড ডোমেইন
    "allowed_domains": ["animethic.in", "www.animethic.in"],
    
    # ওয়ার্নিং সেটিংস
    "max_warnings": 3,
    "mute_duration": 60,
    "auto_mute_enabled": True,
    
    # অটো পোস্টার
    "last_post_id": None,
    "post_interval": 10,
    
    # সার্চ সেটিংস
    "use_api": True,  # API ব্যবহার করবে কিনা
    "use_rss": True,  # RSS ব্যবহার করবে কিনা
    "fuzzy_threshold": 0.6,  # ফাজি ম্যাচিং থ্রেশহোল্ড
    
    # সিকিউরিটি সেটিংস
    "security": {
        "two_factor_auth": False,
        "admin_login_alert": True,
        "moderator_access": True
    },
    
    # ফিচার কন্ট্রোল
    "features": {
        "user_system": True,
        "ai_features": True,
        "moderation": True,
        "calendar": True,
        "daily_release": True,
        "analytics": True
    }
})

# ========== ক্যালেন্ডার ডাটাবেস ==========
calendar_db = load_json('calendar.json', {
    "sunday": [],
    "monday": [],
    "tuesday": [],
    "wednesday": [],
    "thursday": [],
    "friday": [],
    "saturday": []
})

# ========== ডেইলি রিলিজ ডাটাবেস ==========
daily_release_db = load_json('daily_release.json', {
    "entries": [],
    "assignments": {},
    "notes": {}
})

# ========== টিম ডাটাবেস ==========
team_db = load_json('team.json', {
    "admins": {},
    "moderators": {},
    "departments": {
        "security": {"head": None, "members": []},
        "community": {"head": None, "members": []},
        "content": {"head": None, "members": []},
        "tech": {"head": None, "members": []},
        "investigation": {"head": None, "members": []}
    },
    "tasks": [],
    "performance": {}
})

# ========== সিকিউরিটি ডাটাবেস ==========
security_db = load_json('security.json', {
    "two_factor": {},
    "login_history": [],
    "blocked_attempts": [],
    "trusted_devices": {}
})

# ========== Blogger API v3 ফাংশন ==========
def get_all_posts_from_api(max_results=50):
    """Blogger API v3 থেকে পোস্ট আনে"""
    if not API_KEY or not BLOG_ID or not settings_db.get("use_api", True):
        return []
    
    try:
        url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts"
        params = {
            'key': API_KEY,
            'maxResults': max_results,
            'fetchBodies': 'false',
            'fetchImages': 'false',
            'status': 'live'
        }
        
        logger.info(f"Calling Blogger API: {url}")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            posts = []
            for item in data.get('items', []):
                posts.append({
                    'title': item.get('title', ''),
                    'link': item.get('url', ''),
                    'published': item.get('published', ''),
                    'labels': item.get('labels', []),
                    'id': item.get('id', ''),
                    'source': 'api'
                })
            logger.info(f"API returned {len(posts)} posts")
            return posts
        else:
            logger.error(f"Blogger API error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logger.error(f"Blogger API exception: {e}")
        return []

def search_anime_with_api(query, max_results=10):
    """API ব্যবহার করে অ্যানিমে সার্চ করে"""
    if not API_KEY or not BLOG_ID or not settings_db.get("use_api", True):
        return []
    
    try:
        # URL এনকোডিং
        encoded_query = requests.utils.quote(query)
        url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOG_ID}/posts/search"
        params = {
            'key': API_KEY,
            'q': query,
            'maxResults': max_results,
            'fetchBodies': 'false',
            'fetchImages': 'false',
            'status': 'live'
        }
        
        logger.info(f"Searching API for: {query}")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = []
            for item in data.get('items', []):
                title = item.get('title', '')
                
                results.append({
                    'title': title,
                    'link': item.get('url', ''),
                    'score': 1.0,  # API exact match
                    'published': item.get('published', ''),
                    'labels': item.get('labels', []),
                    'source': 'api'
                })
            
            logger.info(f"API search returned {len(results)} results")
            return results[:max_results]
        else:
            logger.error(f"Blogger API search error: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Blogger API search exception: {e}")
        return []

def get_latest_posts_from_rss():
    """RSS ফিড থেকে পোস্ট আনে (ফলব্যাক)"""
    if not settings_db.get("use_rss", True):
        return []
    
    try:
        feed = feedparser.parse(RSS_FEED_URL)
        posts = []
        for entry in feed.entries[:20]:
            posts.append({
                'title': entry.title,
                'link': entry.link,
                'published': entry.published if hasattr(entry, 'published') else '',
                'source': 'rss'
            })
        return posts
    except Exception as e:
        logger.error(f"RSS error: {e}")
        return []

# ========== এনহ্যান্সড সার্চ ফাংশন ==========
def enhanced_search_anime(query):
    """এনহ্যান্সড সার্চ - API + RSS + ফাজি"""
    results = []
    seen_links = set()
    
    query_lower = query.lower().strip()
    
    # প্রথমে API তে সার্চ (সবচেয়ে নির্ভুল)
    if settings_db.get("use_api", True):
        api_results = search_anime_with_api(query_lower, max_results=10)
        for res in api_results:
            if res['link'] not in seen_links:
                seen_links.add(res['link'])
                results.append(res)
    
    # তারপর RSS ফিডে সার্চ (ফলব্যাক)
    if settings_db.get("use_rss", True) and len(results) < 5:
        rss_posts = get_latest_posts_from_rss()
        for post in rss_posts:
            if post['link'] in seen_links:
                continue
            
            title = post.get('title', '').lower()
            
            # Exact match
            if query_lower in title:
                score = 1.0
            else:
                # Fuzzy match
                score = fuzzy_match(query_lower, title)
            
            threshold = settings_db.get("fuzzy_threshold", 0.6)
            if score > threshold:
                seen_links.add(post['link'])
                results.append({
                    'title': post.get('title', ''),
                    'link': post.get('link', ''),
                    'score': score,
                    'source': 'rss'
                })
    
    # স্কোর অনুযায়ী সাজানো
    results.sort(key=lambda x: x.get('score', 0), reverse=True)
    return results[:5]  # সর্বোচ্চ ৫টি রেজাল্ট

# ========== ইউজার ফাংশন ==========
def get_user_data(user_id):
    """ইউজার ডাটা রিটার্ন করে"""
    user_id = str(user_id)
    if user_id not in users_db:
        users_db[user_id] = {
            "warnings": 0,
            "is_muted": False,
            "mute_until": None,
            "is_banned": False,
            "is_moderator": False,
            "mod_level": 0,
            "department": None,
            "join_date": str(datetime.now()),
            "total_requests": 0,
            "last_active": str(datetime.now()),
            "trust_score": 100,
            "rank": "🔰 Newbie",
            "points": 0,
            "achievements": []
        }
        save_json('users.json', users_db)
    return users_db[user_id]

def save_user_data(user_id, data):
    """ইউজার ডাটা সেভ করে"""
    users_db[str(user_id)] = data
    save_json('users.json', users_db)

def is_admin(user_id):
    """চেক করে ইউজার অ্যাডমিন কিনা"""
    return str(user_id) == str(ADMIN_ID)

def is_moderator(user_id):
    """চেক করে ইউজার মডারেটর কিনা"""
    if is_admin(user_id):
        return True
    user_data = get_user_data(user_id)
    return user_data.get("is_moderator", False)

def get_user_role(user_id):
    """ইউজারের রোল রিটার্ন করে"""
    if is_admin(user_id):
        return "👑 Owner"
    user_data = get_user_data(user_id)
    if user_data.get("is_moderator"):
        levels = ["", "🔰 Trainee", "🎓 Junior", "📋 Senior", "⚔️ Head", "🛡️ Co-owner"]
        return levels[user_data.get("mod_level", 1)]
    return "👤 User"

# ========== ল্যাঙ্গুয়েজ ফাংশন ==========
def fuzzy_match(query, text):
    """ফাজি ম্যাচিং (0-1 স্কেল)"""
    return SequenceMatcher(None, query.lower(), text.lower()).ratio()

def is_anime_request(text):
    """চেক করে টেক্সট অ্যানিমে রিকোয়েস্ট কিনা"""
    if not text:
        return False
    
    text = text.lower().strip()
    
    # ইগনোর প্যাটার্ন
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
    
    # অ্যানিমে কিওয়ার্ড
    anime_keywords = [
        'anime', 'naruto', 'one piece', 'demon slayer', 'attack on titan',
        'season', 'episode', 'ep', 'dubbed', 'subbed', 'hindi', 'english',
        'watch', 'download', 'stream', 'online', 'free'
    ]
    
    for keyword in anime_keywords:
        if keyword in text:
            return True
    
    return False

def is_add_request(text):
    """চেক করে এটা add request কিনা"""
    if not text:
        return False
    
    text = text.lower().strip()
    add_patterns = ['add', 'যোগ', 'add koro', 'upload', 'dal do', 'please add']
    
    for pattern in add_patterns:
        if pattern in text:
            return True
    
    return False

def extract_anime_name(text):
    """টেক্সট থেকে অ্যানিমে নাম বের করে"""
    common_words = [
        'anime', 'download', 'watch', 'stream', 'episode', 'season',
        'dubbed', 'hindi', 'english', 'sub', 'subbed', 'free'
    ]
    
    text = text.lower()
    for word in common_words:
        text = text.replace(word, '')
    
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

# ========== লিংক ফিল্টার ==========
def extract_links(text):
    """টেক্সট থেকে লিংক বের করে"""
    url_pattern = r'https?://[^\s]+|www\.[^\s]+'
    return re.findall(url_pattern, text, re.IGNORECASE)

def is_allowed_domain(url):
    """চেক করে লিংক অ্যালাউড ডোমেইনের কিনা"""
    for domain in settings_db.get("allowed_domains", []):
        if domain in url:
            return True
    return False

def contains_forbidden_links(text):
    """চেক করে টেক্সটে নিষিদ্ধ লিংক আছে কিনা"""
    if not settings_db.get("link_filter_enabled", True):
        return False
    
    links = extract_links(text)
    if not links:
        return False
    
    for link in links:
        if not is_allowed_domain(link):
            return True
    
    return False

# ========== ইউজার ম্যানেজমেন্ট ফাংশন ==========
def add_warning(user_id, reason=""):
    """ইউজারকে ওয়ার্নিং যোগ করে"""
    user_data = get_user_data(user_id)
    user_data["warnings"] = user_data.get("warnings", 0) + 1
    user_data["last_warning"] = str(datetime.now())
    user_data["trust_score"] = max(0, user_data.get("trust_score", 100) - 10)
    save_user_data(user_id, user_data)
    
    stats_db["total_warnings"] = stats_db.get("total_warnings", 0) + 1
    save_json('stats.json', stats_db)
    
    return user_data["warnings"]

def clear_warnings(user_id):
    """ইউজারের ওয়ার্নিং রিসেট করে"""
    user_data = get_user_data(user_id)
    user_data["warnings"] = 0
    user_data["trust_score"] = min(100, user_data.get("trust_score", 100) + 20)
    save_user_data(user_id, user_data)
    return True

def mute_user(user_id, duration_minutes):
    """ইউজারকে মিউট করে"""
    user_data = get_user_data(user_id)
    user_data["is_muted"] = True
    user_data["mute_until"] = str(datetime.now() + timedelta(minutes=duration_minutes))
    save_user_data(user_id, user_data)
    
    stats_db["total_mutes"] = stats_db.get("total_mutes", 0) + 1
    save_json('stats.json', stats_db)
    return True

def unmute_user(user_id):
    """ইউজারের মিউট উঠায়"""
    user_data = get_user_data(user_id)
    user_data["is_muted"] = False
    user_data["mute_until"] = None
    save_user_data(user_id, user_data)
    return True

def ban_user(user_id, reason=""):
    """ইউজারকে ব্যান করে"""
    user_data = get_user_data(user_id)
    user_data["is_banned"] = True
    user_data["ban_reason"] = reason
    user_data["ban_date"] = str(datetime.now())
    save_user_data(user_id, user_data)
    
    stats_db["total_bans"] = stats_db.get("total_bans", 0) + 1
    save_json('stats.json', stats_db)
    return True

def unban_user(user_id):
    """ইউজারের ব্যান উঠায়"""
    user_data = get_user_data(user_id)
    user_data["is_banned"] = False
    save_user_data(user_id, user_data)
    return True

def add_points(user_id, points):
    """ইউজারকে পয়েন্ট যোগ করে"""
    user_data = get_user_data(user_id)
    user_data["points"] = user_data.get("points", 0) + points
    user_data["trust_score"] = min(100, user_data.get("trust_score", 100) + 1)
    
    # র‌্যাঙ্ক আপডেট
    points = user_data["points"]
    if points < 100:
        user_data["rank"] = "🔰 Newbie"
    elif points < 500:
        user_data["rank"] = "🥉 Bronze"
    elif points < 2000:
        user_data["rank"] = "🥈 Silver"
    elif points < 5000:
        user_data["rank"] = "🥇 Gold"
    elif points < 10000:
        user_data["rank"] = "💎 Platinum"
    elif points < 20000:
        user_data["rank"] = "🔮 Diamond"
    elif points < 50000:
        user_data["rank"] = "⚡ Master"
    elif points < 100000:
        user_data["rank"] = "👑 Grandmaster"
    elif points < 500000:
        user_data["rank"] = "🌟 Legend"
    else:
        user_data["rank"] = "🏆 Mythical"
    
    save_user_data(user_id, user_data)
    return user_data["rank"]

# ========== ক্যালেন্ডার ফাংশন ==========
def get_calendar_for_day(day):
    """নির্দিষ্ট দিনের ক্যালেন্ডার এন্ট্রি রিটার্ন করে"""
    day = day.lower()
    return calendar_db.get(day, [])

def add_to_calendar(day, anime_name):
    """ক্যালেন্ডারে নতুন এন্ট্রি যোগ করে"""
    day = day.lower()
    if day not in calendar_db:
        calendar_db[day] = []
    
    if anime_name not in calendar_db[day]:
        calendar_db[day].append(anime_name)
        save_json('calendar.json', calendar_db)
        return True
    return False

def remove_from_calendar(day, anime_name):
    """ক্যালেন্ডার থেকে এন্ট্রি রিমুভ করে"""
    day = day.lower()
    if day in calendar_db and anime_name in calendar_db[day]:
        calendar_db[day].remove(anime_name)
        save_json('calendar.json', calendar_db)
        return True
    return False

# ========== ডেইলি রিলিজ ফাংশন ==========
def add_daily_release(anime_name, day, assigned_to=None, notes=""):
    """ডেইলি রিলিজে নতুন এন্ট্রি যোগ করে"""
    entry = {
        "id": len(daily_release_db["entries"]) + 1,
        "anime": anime_name,
        "day": day,
        "assigned_to": assigned_to,
        "notes": notes,
        "status": "pending",
        "created_at": str(datetime.now())
    }
    daily_release_db["entries"].append(entry)
    
    if assigned_to:
        if assigned_to not in daily_release_db["assignments"]:
            daily_release_db["assignments"][assigned_to] = []
        daily_release_db["assignments"][assigned_to].append(entry["id"])
    
    if notes:
        daily_release_db["notes"][str(entry["id"])] = notes
    
    save_json('daily_release.json', daily_release_db)
    return entry

# ========== টেলিগ্রাম হ্যান্ডলার ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """স্টার্ট কমান্ড"""
    user = update.effective_user
    add_points(user.id, 5)  # বোনাস পয়েন্ট
    
    await update.message.reply_text(
        f"🤖 **অ্যানিমেথিক আলট্রা বট v5.0**\n\n"
        f"👋 স্বাগতম {user.first_name}!\n\n"
        f"**আপনার স্ট্যাটাস:**\n"
        f"🏆 র‌্যাঙ্ক: {get_user_data(user.id)['rank']}\n"
        f"⭐ পয়েন্ট: {get_user_data(user.id).get('points', 0)}\n\n"
        f"**বিশেষ ফিচার:**\n"
        f"• Blogger API v3 ইন্টিগ্রেশন\n"
        f"• ১০০% নির্ভুল সার্চ\n"
        f"• পুরানো সব পোস্ট খুঁজে পাবে\n\n"
        f"**কমান্ড:**\n"
        f"/help - সাহায্য দেখুন\n"
        f"/calendar - ক্যালেন্ডার দেখুন\n"
        f"/rank - আপনার র‌্যাঙ্ক দেখুন\n\n"
        f"🔍 **অ্যানিমে খুঁজতে:**\n"
        f"শুধু নাম লিখুন (যেমন: Naruto Season 9)",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """হেল্প কমান্ড"""
    user_id = update.effective_user.id
    
    help_text = (
        "📚 **সাহায্য গাইড**\n\n"
        "**ইউজার কমান্ড:**\n"
        "/start - বট শুরু করুন\n"
        "/help - এই মেসেজ দেখুন\n"
        "/calendar - অ্যানিমে ক্যালেন্ডার দেখুন\n"
        "/rank - আপনার র‌্যাঙ্ক দেখুন\n\n"
    )
    
    if is_moderator(user_id):
        help_text += (
            "**🛡️ মডারেটর কমান্ড:**\n"
            "/warn @user - ওয়ার্ন দিন\n"
            "/mute @user [মিনিট] - মিউট করুন\n"
            "/unmute @user - মিউট উঠান\n"
            "/reports - রিপোর্ট দেখুন\n\n"
        )
    
    if is_admin(user_id):
        help_text += (
            "**👑 অ্যাডমিন কমান্ড:**\n"
            "/panel - অ্যাডমিন প্যানেল\n"
            "/stats - পরিসংখ্যান\n"
            "/settings - সেটিংস\n"
            "/backup - ব্যাকআপ নিন\n"
            "/addmod @user - মডারেটর যোগ করুন\n"
            "/removemod @user - মডারেটর রিমুভ করুন\n"
            "/api_status - API স্ট্যাটাস দেখুন\n"
        )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def api_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """API স্ট্যাটাস দেখায়"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ আপনার অনুমতি নেই!")
        return
    
    status_text = "🔌 **Blogger API v3 Status**\n\n"
    
    if API_KEY and BLOG_ID:
        status_text += "✅ API Key: Configured\n"
        status_text += f"✅ Blog ID: {BLOG_ID}\n\n"
        
        # টেস্ট API কল
        try:
            test_posts = get_all_posts_from_api(max_results=1)
            if test_posts:
                status_text += "✅ API Connection: Working\n"
                status_text += f"📊 Total posts available: {len(get_all_posts_from_api(max_results=50))}+"
            else:
                status_text += "❌ API Connection: Failed - No posts returned"
        except Exception as e:
            status_text += f"❌ API Connection: Error - {str(e)[:100]}"
    else:
        status_text += "❌ API Key: Not configured\n"
        status_text += "❌ Blog ID: Not configured"
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ক্যালেন্ডার কমান্ড"""
    text = "📅 **উইকলি অ্যানিমে ক্যালেন্ডার**\n\n"
    
    days = [
        ("সোমবার", calendar_db.get("monday", [])),
        ("মঙ্গলবার", calendar_db.get("tuesday", [])),
        ("বুধবার", calendar_db.get("wednesday", [])),
        ("বৃহস্পতিবার", calendar_db.get("thursday", [])),
        ("শুক্রবার", calendar_db.get("friday", [])),
        ("শনিবার", calendar_db.get("saturday", [])),
        ("রবিবার", calendar_db.get("sunday", []))
    ]
    
    for day_name, anime_list in days:
        text += f"**{day_name}**\n"
        if anime_list:
            for anime in anime_list:
                text += f"• {anime}\n"
        else:
            text += "• কোন অ্যানিমে নেই\n"
        text += "\n"
    
    keyboard = []
    if is_moderator(update.effective_user.id):
        keyboard.append([InlineKeyboardButton("📋 ম্যানেজ করুন", callback_data="cal_manage")])
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    else:
        reply_markup = None
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def rank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """র‌্যাঙ্ক কমান্ড"""
    user = update.effective_user
    user_data = get_user_data(user.id)
    
    # এক্সপি বার
    points = user_data.get('points', 0)
    next_level = 0
    if points < 100:
        next_level = 100
    elif points < 500:
        next_level = 500
    elif points < 2000:
        next_level = 2000
    elif points < 5000:
        next_level = 5000
    elif points < 10000:
        next_level = 10000
    elif points < 20000:
        next_level = 20000
    elif points < 50000:
        next_level = 50000
    elif points < 100000:
        next_level = 100000
    elif points < 500000:
        next_level = 500000
    
    if next_level:
        progress = (points / next_level) * 100
        bar = "█" * int(progress/10) + "░" * (10 - int(progress/10))
        progress_text = f"{bar} {progress:.1f}%"
    else:
        progress_text = "MAX LEVEL"
    
    text = (
        f"🏆 **{user.first_name} এর প্রোফাইল**\n\n"
        f"📊 র‌্যাঙ্ক: {user_data['rank']}\n"
        f"⭐ পয়েন্ট: {points:,}\n"
        f"📈 অগ্রগতি: {progress_text}\n"
        f"📝 মোট রিকোয়েস্ট: {user_data.get('total_requests', 0):,}\n"
        f"🤝 ট্রাস্ট স্কোর: {user_data.get('trust_score', 100)}%\n"
        f"📅 জয়েন: {user_data.get('join_date', 'N/A')[:10]}\n"
    )
    
    if user_data.get('achievements'):
        text += "\n**🏅 অ্যাচিভমেন্ট:**\n"
        for ach in user_data['achievements'][-3:]:
            text += f"• {ach}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """অ্যাডমিন প্যানেল"""
    user_id = update.effective_user.id
    
    if not is_moderator(user_id):
        await update.message.reply_text("⛔ আপনার অনুমতি নেই!")
        return
    
    role = get_user_role(user_id)
    
    keyboard = [
        [
            InlineKeyboardButton("📊 ড্যাশবোর্ড", callback_data="panel_dashboard"),
            InlineKeyboardButton("📅 ক্যালেন্ডার", callback_data="panel_calendar")
        ],
        [
            InlineKeyboardButton("📋 ডেইলি রিলিজ", callback_data="panel_daily"),
            InlineKeyboardButton("👥 ইউজার", callback_data="panel_users")
        ],
        [
            InlineKeyboardButton("🛡️ মডারেশন", callback_data="panel_mod"),
            InlineKeyboardButton("📈 অ্যানালিটিক্স", callback_data="panel_analytics")
        ]
    ]
    
    if is_admin(user_id):
        keyboard.extend([
            [
                InlineKeyboardButton("👑 টিম ম্যানেজ", callback_data="panel_team"),
                InlineKeyboardButton("🔐 সিকিউরিটি", callback_data="panel_security")
            ],
            [
                InlineKeyboardButton("⚙️ সেটিংস", callback_data="panel_settings"),
                InlineKeyboardButton("💾 ব্যাকআপ", callback_data="panel_backup")
            ],
            [
                InlineKeyboardButton("🔌 API স্ট্যাটাস", callback_data="panel_api"),
                InlineKeyboardButton("⚡ অ্যাডভান্সড", callback_data="panel_advanced")
            ]
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔐 **কন্ট্রোল প্যানেল**\n\n"
        f"আপনার রোল: {role}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """পরিসংখ্যান কমান্ড"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ আপনার অনুমতি নেই!")
        return
    
    # API ব্যবহার করে মোট পোস্টের সংখ্যা
    total_posts = len(get_all_posts_from_api(max_results=50)) if API_KEY and BLOG_ID else 0
    
    text = (
        f"📊 **বট পরিসংখ্যান**\n\n"
        f"📝 মোট রিকোয়েস্ট: {stats_db.get('total_requests', 0):,}\n"
        f"⚠️ মোট ওয়ার্নিং: {stats_db.get('total_warnings', 0):,}\n"
        f"🔇 মোট মিউট: {stats_db.get('total_mutes', 0):,}\n"
        f"🚫 মোট ব্যান: {stats_db.get('total_bans', 0):,}\n"
        f"👥 মোট ইউজার: {len(users_db):,}\n"
        f"🛡️ মোট মডারেটর: {sum(1 for u in users_db.values() if u.get('is_moderator'))}\n\n"
        f"**📊 API পরিসংখ্যান:**\n"
        f"• ব্লগ আইডি: {BLOG_ID[:8]}...\n"
        f"• API স্ট্যাটাস: {'✅ চালু' if API_KEY else '❌ বন্ধ'}\n"
        f"• মোট পোস্ট: {total_posts}+ (API থেকে)\n\n"
        f"**🔥 টপ ৫ অ্যানিমে:**\n"
    )
    
    top_anime = sorted(stats_db.get('anime_requests', {}).items(), 
                       key=lambda x: x[1], reverse=True)[:5]
    
    if top_anime:
        for i, (anime, count) in enumerate(top_anime, 1):
            text += f"{i}. {anime[:30]}... - {count:,} বার\n"
    else:
        text += "কোন ডাটা নেই\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def addmod_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """মডারেটর যোগ করার কমান্ড"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ আপনার অনুমতি নেই!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ কোন মেসেজের রিপ্লাই হিসেবে /addmod ব্যবহার করুন")
        return
    
    target_user = update.message.reply_to_message.from_user
    
    if is_moderator(target_user.id):
        await update.message.reply_text(f"⚠️ {target_user.first_name} ইতিমধ্যে মডারেটর!")
        return
    
    level = 1
    department = None
    
    if context.args:
        try:
            level = int(context.args[0])
            if len(context.args) > 1:
                department = context.args[1]
        except:
            pass
    
    # মডারেটর ডাটা আপডেট
    user_data = get_user_data(target_user.id)
    user_data["is_moderator"] = True
    user_data["mod_level"] = level
    user_data["department"] = department
    save_user_data(target_user.id, user_data)
    
    await update.message.reply_text(
        f"✅ {target_user.mention_html()} কে মডারেটর করা হয়েছে!\n"
        f"📊 লেভেল: {level}\n"
        f"🏢 ডিপার্টমেন্ট: {department or 'None'}",
        parse_mode='HTML'
    )

async def removemod_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """মডারেটর রিমুভ করার কমান্ড"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ আপনার অনুমতি নেই!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ কোন মেসেজের রিপ্লাই হিসেবে /removemod ব্যবহার করুন")
        return
    
    target_user = update.message.reply_to_message.from_user
    
    if not is_moderator(target_user.id) or is_admin(target_user.id):
        await update.message.reply_text(f"⚠️ {target_user.first_name} মডারেটর নয়!")
        return
    
    # মডারেটর ডাটা আপডেট
    user_data = get_user_data(target_user.id)
    user_data["is_moderator"] = False
    user_data["mod_level"] = 0
    user_data["department"] = None
    save_user_data(target_user.id, user_data)
    
    await update.message.reply_text(
        f"✅ {target_user.mention_html()} কে মডারেটর থেকে রিমুভ করা হয়েছে!",
        parse_mode='HTML'
    )

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ওয়ার্ন কমান্ড"""
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ আপনার অনুমতি নেই!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ কোন মেসেজের রিপ্লাই হিসেবে /warn ব্যবহার করুন")
        return
    
    target_user = update.message.reply_to_message.from_user
    reason = ' '.join(context.args) if context.args else "No reason"
    
    if is_moderator(target_user.id) and not is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ আপনি অন্য মডারেটরকে ওয়ার্ন দিতে পারবেন না!")
        return
    
    warnings = add_warning(target_user.id, reason)
    
    await update.message.reply_text(
        f"⚠️ {target_user.mention_html()} কে ওয়ার্ন দেওয়া হয়েছে!\n"
        f"কারণ: {reason}\n"
        f"মোট ওয়ার্নিং: {warnings}",
        parse_mode='HTML'
    )

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """মিউট কমান্ড"""
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ আপনার অনুমতি নেই!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ কোন মেসেজের রিপ্লাই হিসেবে /mute ব্যবহার করুন")
        return
    
    target_user = update.message.reply_to_message.from_user
    duration = 60
    
    if context.args:
        try:
            duration = int(context.args[0])
        except:
            pass
    
    if is_moderator(target_user.id) and not is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ আপনি অন্য মডারেটরকে মিউট করতে পারবেন না!")
        return
    
    mute_user(target_user.id, duration)
    
    await update.message.reply_text(
        f"🔇 {target_user.mention_html()} {duration} মিনিটের জন্য মিউট করা হয়েছে!",
        parse_mode='HTML'
    )

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """আনমিউট কমান্ড"""
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ আপনার অনুমতি নেই!")
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ কোন মেসেজের রিপ্লাই হিসেবে /unmute ব্যবহার করুন")
        return
    
    target_user = update.message.reply_to_message.from_user
    unmute_user(target_user.id)
    
    await update.message.reply_text(
        f"✅ {target_user.mention_html()} এর মিউট উঠানো হয়েছে!",
        parse_mode='HTML'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """মেসেজ হ্যান্ডলার"""
    if not update.message or not update.message.text:
        return
    
    user = update.message.from_user
    user_id = user.id
    chat_id = update.message.chat_id
    text = update.message.text
    
    # শুধু গ্রুপে কাজ করবে
    if chat_id != GROUP_ID:
        return
    
    # ইউজার ডাটা লোড
    user_data = get_user_data(user_id)
    user_data["last_active"] = str(datetime.now())
    save_user_data(user_id, user_data)
    
    # ব্যান চেক
    if user_data.get("is_banned", False):
        try:
            await update.message.delete()
        except:
            pass
        return
    
    # মিউট চেক
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
    
    # লিংক ফিল্টার চেক
    if contains_forbidden_links(text):
        try:
            await update.message.delete()
            warnings = add_warning(user_id, "Forbidden link")
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user.mention_html()} নিষিদ্ধ লিংক পোস্ট করেছেন!\n"
                     f"ওয়ার্নিং: {warnings}/{settings_db.get('max_warnings', 3)}",
                parse_mode='HTML'
            )
            
            if warnings >= settings_db.get('max_warnings', 3):
                mute_duration = settings_db.get('mute_duration', 60)
                mute_user(user_id, mute_duration)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔇 {user.mention_html()} {mute_duration} মিনিটের জন্য মিউট করা হয়েছে!",
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
        return
    
    # Add request ইগনোর
    if is_add_request(text):
        return
    
    # অ্যানিমে রিকোয়েস্ট চেক
    if is_anime_request(text):
        stats_db["total_requests"] = stats_db.get("total_requests", 0) + 1
        stats_db["daily_requests"] = stats_db.get("daily_requests", 0) + 1
        user_data["total_requests"] = user_data.get("total_requests", 0) + 1
        
        # পয়েন্ট যোগ করুন
        add_points(user_id, 5)
        
        save_user_data(user_id, user_data)
        
        anime_name = extract_anime_name(text)
        if not anime_name:
            return
        
        # এনহ্যান্সড সার্চ ব্যবহার করুন
        results = enhanced_search_anime(anime_name)
        
        if results:
            for result in results:
                title = result['title']
                stats_db["anime_requests"][title] = stats_db["anime_requests"].get(title, 0) + 1
            
            reply = f"🔍 **'{text}' এর জন্য পাওয়া গেছে:**\n\n"
            for i, result in enumerate(results, 1):
                source_icon = "🔵" if result.get('source') == 'api' else "🟢"
                reply += f"{i}. {source_icon} **{result['title']}**\n"
                reply += f"📥 [ডাউনলোড করুন]({result['link']})\n\n"
            
            await update.message.reply_text(reply, parse_mode='Markdown', disable_web_page_preview=True)
        else:
            reply = f"🔍 '{text}' পাওয়া যায়নি।\n\n📞 যোগাযোগ: @animethic_admin_bot"
            await update.message.reply_text(reply)
        
        save_json('stats.json', stats_db)

async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """নতুন মেম্বার জয়েন করলে"""
    if not settings_db.get("welcome_enabled", True):
        return
    
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        
        # নতুন ইউজারের জন্য ডাটা তৈরি
        get_user_data(member.id)
        add_points(member.id, 10)  # ওয়েলকাম বোনাস
        stats_db["daily_users"] = stats_db.get("daily_users", 0) + 1
        save_json('stats.json', stats_db)
        
        welcome_text = settings_db.get("welcome_message", "👋 স্বাগতম {name}!")
        welcome_text = welcome_text.replace("{name}", member.first_name)
        
        await update.message.reply_text(welcome_text)

# ========== ইনলাইন বাটন হ্যান্ডলার ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বাটন ক্লিক হ্যান্ডলার"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if not is_moderator(user_id):
        await query.edit_message_text("⛔ আপনার অনুমতি নেই!")
        return
    
    data = query.data
    
    # প্যানেল ড্যাশবোর্ড
    if data == "panel_dashboard":
        text = (
            f"📊 **ড্যাশবোর্ড**\n\n"
            f"👥 মোট ইউজার: {len(users_db):,}\n"
            f"📝 মোট রিকোয়েস্ট: {stats_db.get('total_requests', 0):,}\n"
            f"⚠️ মোট ওয়ার্নিং: {stats_db.get('total_warnings', 0):,}\n"
            f"🔇 মোট মিউট: {stats_db.get('total_mutes', 0):,}\n"
            f"🚫 মোট ব্যান: {stats_db.get('total_bans', 0):,}\n"
            f"🛡️ মোট মডারেটর: {sum(1 for u in users_db.values() if u.get('is_moderator'))}\n\n"
            f"**📈 আজকের অ্যাক্টিভিটি:**\n"
            f"• রিকোয়েস্ট: {stats_db.get('daily_requests', 0)}\n"
            f"• নতুন ইউজার: {stats_db.get('daily_users', 0)}"
        )
        
        keyboard = [[InlineKeyboardButton("◀️ পিছনে", callback_data="panel_back")]]
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    # প্যানেল ক্যালেন্ডার
    elif data == "panel_calendar":
        text = "📅 **ক্যালেন্ডার ম্যানেজার**\n\n"
        
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        bangla_days = ["সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার", "শুক্রবার", "শনিবার", "রবিবার"]
        
        keyboard = []
        for day_en, day_bn in zip(days, bangla_days):
            count = len(calendar_db.get(day_en, []))
            keyboard.append([InlineKeyboardButton(
                f"{day_bn} ({count}টি)", 
                callback_data=f"cal_view_{day_en}"
            )])
        
        keyboard.append([InlineKeyboardButton("➕ নতুন যোগ করুন", callback_data="cal_add")])
        keyboard.append([InlineKeyboardButton("◀️ পিছনে", callback_data="panel_back")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    # ক্যালেন্ডার ভিউ
    elif data.startswith("cal_view_"):
        day = data.replace("cal_view_", "")
        bangla_day = {
            "monday": "সোমবার", "tuesday": "মঙ্গলবার", "wednesday": "বুধবার",
            "thursday": "বৃহস্পতিবার", "friday": "শুক্রবার", "saturday": "শনিবার",
            "sunday": "রবিবার"
        }.get(day, day)
        
        anime_list = calendar_db.get(day, [])
        
        text = f"📅 **{bangla_day}**\n\n"
        if anime_list:
            for i, anime in enumerate(anime_list, 1):
                text += f"{i}. {anime}\n"
        else:
            text += "কোন অ্যানিমে নেই।\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ যোগ করুন", callback_data=f"cal_add_{day}")],
            [InlineKeyboardButton("◀️ পিছনে", callback_data="panel_calendar")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    # ক্যালেন্ডার যোগ
    elif data == "cal_add" or data.startswith("cal_add_"):
        await query.edit_message_text(
            "➕ **ক্যালেন্ডারে অ্যানিমে যোগ করুন**\n\n"
            "📝 **ফরম্যাট:** `/addanime [দিন] [নাম]`\n\n"
            "**দিন:** monday, tuesday, wednesday, thursday, friday, saturday, sunday\n\n"
            "**উদাহরণ:**\n"
            "`/addanime monday Naruto S9 E24`\n"
            "`/addanime friday One Piece E1089`\n\n"
            "❌ ডিলিট করতে: `/removeanime [দিন] [নাম]`",
            parse_mode='Markdown'
        )
    
    # প্যানেল ডেইলি রিলিজ
    elif data == "panel_daily":
        text = "📋 **ডেইলি রিলিজ ট্র্যাকার**\n\n"
        
        pending = [e for e in daily_release_db["entries"] if e.get("status") == "pending"]
        completed = [e for e in daily_release_db["entries"] if e.get("status") == "completed"]
        
        text += f"⏳ **পেন্ডিং:** {len(pending)}\n"
        text += f"✅ **সম্পন্ন:** {len(completed)}\n\n"
        
        if pending:
            text += "**আজকের কাজ:**\n"
            for entry in pending[:5]:
                text += f"• {entry.get('anime')} ({entry.get('day')})\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ নতুন", callback_data="daily_add"),
             InlineKeyboardButton("📋 সব", callback_data="daily_all")],
            [InlineKeyboardButton("◀️ পিছনে", callback_data="panel_back")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    # প্যানেল ইউজার
    elif data == "panel_users":
        text = "👥 **ইউজার ম্যানেজমেন্ট**\n\n"
        
        total_users = len(users_db)
        active_today = sum(1 for u in users_db.values() 
                          if u.get('last_active', '').startswith(str(datetime.now().date())))
        banned = sum(1 for u in users_db.values() if u.get('is_banned'))
        muted = sum(1 for u in users_db.values() if u.get('is_muted'))
        
        text += f"📊 **পরিসংখ্যান:**\n"
        text += f"• মোট ইউজার: {total_users:,}\n"
        text += f"• আজকে একটিভ: {active_today}\n"
        text += f"• ব্যান করা: {banned}\n"
        text += f"• মিউট করা: {muted}\n\n"
        
        text += "**কমান্ড:**\n"
        text += "• `/warn @user` - ওয়ার্ন দিন\n"
        text += "• `/mute @user 60` - মিউট করুন\n"
        text += "• `/unmute @user` - মিউট উঠান\n"
        text += "• `/ban @user` - ব্যান করুন\n"
        text += "• `/unban @user` - আনব্যান করুন"
        
        keyboard = [[InlineKeyboardButton("◀️ পিছনে", callback_data="panel_back")]]
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    # প্যানেল মডারেশন
    elif data == "panel_mod":
        text = "🛡️ **মডারেশন কন্ট্রোল**\n\n"
        
        moderators = [(uid, u) for uid, u in users_db.items() if u.get('is_moderator')]
        
        text += f"**মোট মডারেটর:** {len(moderators)}\n\n"
        
        if moderators:
            text += "**মডারেটর লিস্ট:**\n"
            for uid, u in moderators[:5]:
                name = f"User {uid[:6]}..."
                level = u.get('mod_level', 1)
                dept = u.get('department', 'None')
                text += f"• {name} (Level {level}) - {dept}\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ মডারেটর যোগ", callback_data="mod_add"),
             InlineKeyboardButton("📊 পারফরম্যান্স", callback_data="mod_perf")],
            [InlineKeyboardButton("◀️ পিছনে", callback_data="panel_back")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    # প্যানেল অ্যানালিটিক্স
    elif data == "panel_analytics":
        text = "📈 **অ্যানালিটিক্স ড্যাশবোর্ড**\n\n"
        
        total_reqs = stats_db.get('total_requests', 0)
        
        # API ব্যবহার করে মোট পোস্ট
        total_posts = len(get_all_posts_from_api(max_results=50)) if API_KEY and BLOG_ID else 0
        
        text += f"📊 **মোট রিকোয়েস্ট:** {total_reqs:,}\n"
        text += f"🔌 **API পোস্ট:** {total_posts:,}\n\n"
        
        text += "**টপ অ্যানিমে:**\n"
        top_anime = sorted(stats_db.get('anime_requests', {}).items(), 
                          key=lambda x: x[1], reverse=True)[:3]
        
        for anime, count in top_anime:
            text += f"• {anime[:20]}... - {count:,} বার\n"
        
        keyboard = [[InlineKeyboardButton("◀️ পিছনে", callback_data="panel_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    # API স্ট্যাটাস
    elif data == "panel_api":
        text = "🔌 **Blogger API v3 Status**\n\n"
        
        if API_KEY and BLOG_ID:
            text += f"✅ API Key: Configured\n"
            text += f"✅ Blog ID: {BLOG_ID}\n\n"
            
            # টেস্ট API কল
            try:
                test_posts = get_all_posts_from_api(max_results=1)
                if test_posts:
                    text += "✅ **API Connection: Working**\n"
                    text += f"📊 মোট পোস্ট: {len(get_all_posts_from_api(max_results=50))}+"
                else:
                    text += "❌ **API Connection: Failed** - No posts returned"
            except Exception as e:
                text += f"❌ **API Connection: Error** - {str(e)[:100]}"
        else:
            text += "❌ API Key: Not configured\n"
            text += "❌ Blog ID: Not configured"
        
        keyboard = [[InlineKeyboardButton("◀️ পিছনে", callback_data="panel_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    # ব্যাক টু প্যানেল
    elif data == "panel_back":
        role = get_user_role(user_id)
        
        keyboard = [
            [
                InlineKeyboardButton("📊 ড্যাশবোর্ড", callback_data="panel_dashboard"),
                InlineKeyboardButton("📅 ক্যালেন্ডার", callback_data="panel_calendar")
            ],
            [
                InlineKeyboardButton("📋 ডেইলি রিলিজ", callback_data="panel_daily"),
                InlineKeyboardButton("👥 ইউজার", callback_data="panel_users")
            ],
            [
                InlineKeyboardButton("🛡️ মডারেশন", callback_data="panel_mod"),
                InlineKeyboardButton("📈 অ্যানালিটিক্স", callback_data="panel_analytics")
            ]
        ]
        
        if is_admin(user_id):
            keyboard.extend([
                [
                    InlineKeyboardButton("👑 টিম ম্যানেজ", callback_data="panel_team"),
                    InlineKeyboardButton("🔐 সিকিউরিটি", callback_data="panel_security")
                ],
                [
                    InlineKeyboardButton("⚙️ সেটিংস", callback_data="panel_settings"),
                    InlineKeyboardButton("💾 ব্যাকআপ", callback_data="panel_backup")
                ],
                [
                    InlineKeyboardButton("🔌 API স্ট্যাটাস", callback_data="panel_api"),
                    InlineKeyboardButton("⚡ অ্যাডভান্সড", callback_data="panel_advanced")
                ]
            ])
        
        await query.edit_message_text(
            f"🔐 **কন্ট্রোল প্যানেল**\n\n"
            f"আপনার রোল: {role}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

# ========== অ্যাডমিন কমান্ড ==========
async def addanime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ক্যালেন্ডারে অ্যানিমে যোগ করার কমান্ড"""
    if not is_moderator(update.effective_user.id):
        await update.message.reply_text("⛔ আপনার অনুমতি নেই!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "📝 **ব্যবহার:** `/addanime [দিন] [নাম]`\n\n"
            "**দিন:** monday, tuesday, wednesday, thursday, friday, saturday, sunday\n\n"
            "**উদাহরণ:**\n"
            "`/addanime monday Naruto S9 E24`\n"
            "`/addanime friday One Piece E1089`",
            parse_mode='Markdown'
        )
        return
    
    day = context.args[0].lower()
    name = ' '.join(context.args[1:])
    
    valid_days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    
    if day not in valid_days:
        await update.message.reply_text("❌ **ভুল দিন!**\n\nদিন হতে হবে: monday, tuesday, wednesday, thursday, friday, saturday, sunday", parse_mode='Markdown')
        return
    
    if add_to_calendar(day, name):
        await update.message.reply_text(f"✅ **'{name}'** {day} তে যোগ করা হয়েছে!")
        
        # ডেইলি রিলিজেও যোগ করুন
        add_daily_release(name, day, assigned_to=None, notes="ক্যালেন্ডার থেকে যোগ করা হয়েছে")
    else:
        await update.message.reply_text(f"⚠️ **'{name}'** ইতিমধ্যে {day} তে আছে!")

async def removeanime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ক্যালেন্ডার থেকে অ্যানিমে রিমুভ করার কমান্ড"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ আপনার অনুমতি নেই!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "📝 **ব্যবহার:** `/removeanime [দিন] [নাম]`\n\n"
            "**উদাহরণ:** `/removeanime monday Naruto S9 E24`",
            parse_mode='Markdown'
        )
        return
    
    day = context.args[0].lower()
    name = ' '.join(context.args[1:])
    
    if remove_from_calendar(day, name):
        await update.message.reply_text(f"✅ **'{name}'** {day} থেকে সরানো হয়েছে!")
    else:
        await update.message.reply_text(f"❌ **'{name}'** খুঁজে পাওয়া যায়নি!")

# ========== অটো পোস্টার ==========
async def auto_poster(context: ContextTypes.DEFAULT_TYPE):
    """অটো পোস্টার ফাংশন - API ব্যবহার করে"""
    if not settings_db.get("poster_enabled", True):
        return
    
    try:
        # API থেকে সর্বশেষ পোস্ট
        api_posts = get_all_posts_from_api(max_results=1)
        
        if api_posts:
            latest = api_posts[0]
            last_id = settings_db.get("last_post_id")
            
            if latest['id'] != last_id:
                message = f"📢 **নতুন পোস্ট!**\n\n**{latest['title']}**\n\n📥 [ডাউনলোড করুন]({latest['link']})"
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=message,
                    parse_mode='Markdown'
                )
                settings_db["last_post_id"] = latest['id']
                save_json('settings.json', settings_db)
                logger.info(f"Posted to channel: {latest['title']}")
    except Exception as e:
        logger.error(f"Auto poster error: {e}")

# ========== ডেইলি স্ট্যাটস আপডেট ==========
async def daily_stats_updater(context: ContextTypes.DEFAULT_TYPE):
    """প্রতিদিন স্ট্যাটস রিসেট করে"""
    stats_db["daily_requests"] = 0
    stats_db["daily_users"] = 0
    save_json('stats.json', stats_db)

# ========== মেইন ফাংশন ==========
def main():
    """মেইন ফাংশন"""
    
    # Flask চালু করুন (থ্রেডে)
    threading.Thread(target=lambda: app_flask.run(host='0.0.0.0', port=8080, debug=False)).start()
    
    # বট চালু করুন
    app = Application.builder().token(BOT_TOKEN).build()
    
    # ইউজার কমান্ড
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("calendar", calendar_command))
    app.add_handler(CommandHandler("rank", rank_command))
    
    # মডারেটর কমান্ড
    app.add_handler(CommandHandler("warn", warn_command))
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command))
    
    # অ্যাডমিন কমান্ড
    app.add_handler(CommandHandler("panel", panel_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("addmod", addmod_command))
    app.add_handler(CommandHandler("removemod", removemod_command))
    app.add_handler(CommandHandler("addanime", addanime_command))
    app.add_handler(CommandHandler("removeanime", removeanime_command))
    app.add_handler(CommandHandler("api_status", api_status_command))
    
    # মেসেজ হ্যান্ডলার
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # বাটন হ্যান্ডলার
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # জব কিউ
    app.job_queue.run_repeating(auto_poster, interval=600, first=10)
    app.job_queue.run_daily(daily_stats_updater, time=datetime.time(hour=0, minute=0))
    
    logger.info("🤖 অ্যানিমেথিক আলট্রা বট v5.0 (Blogger API v3) চালু হয়েছে!")
    app.run_polling()

if __name__ == "__main__":
    main()
