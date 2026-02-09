
"""
Telegram Task Management Bot for Koyeb Free Tier
Deployed on Koyeb through GitHub
All times in IST (Indian Standard Time)
"""

from flask import Flask, request, jsonify, render_template_string
import telebot
import threading
import time
from datetime import datetime, timedelta
import os
import atexit
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
import requests
from pymongo import MongoClient
import logging
from bson.objectid import ObjectId
import json
import sys

# ============= CONFIGURATION =============
# SECURITY NOTE: It is best practice to set these in Koyeb Environment Variables.
# I have left your values here as defaults so the code works immediately.
BOT_TOKEN = os.getenv('BOT_TOKEN', "8388773187:AAGx4pCNM1EUXoBZhJpZJlL5Df5zv3BWv3A")
MONGO_URI = os.getenv('MONGO_URI', "mongodb+srv://sandip:9E9AISFqTfU3VI5i@cluster0.p8irtov.mongodb.net/?appName=Cluster0")
KOYEB_URL = os.getenv('KOYEB_APP_URL', 'https://excellent-carole-sandip232-8ee93947.koyeb.app')

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')

# ============= INITIALIZE =============
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN, threaded=False) # threaded=False is safer for Flask

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize MongoDB
# connect=False is crucial for running inside WSGI servers like Gunicorn
try:
    client = MongoClient(MONGO_URI, connect=False)
    db = client['task_bot_db']
    # Check connection immediately
    client.admin.command('ping')
    logger.info("✅ MongoDB Connected Successfully")
except Exception as e:
    logger.error(f"❌ MongoDB Connection Failed: {e}")
    sys.exit(1) # Exit if DB fails

# Collections
notes_collection = db['notes']
reminders_collection = db['reminders']
interval_collection = db['interval_reminders']
bot_stats = db['bot_stats']

# Scheduler for background tasks
scheduler = BackgroundScheduler(timezone=IST)

# User states for conversation
user_states = {}

# ============= MONGODB FUNCTIONS =============
def init_db():
    """Initialize database collections and indexes"""
    try:
        # Create indexes to speed up queries
        notes_collection.create_index([("chat_id", 1), ("created_at", -1)])
        reminders_collection.create_index([("chat_id", 1), ("target_time", 1)])
        reminders_collection.create_index([("is_active", 1)])
        # Auto delete completed/old reminders after 48h to keep DB clean
        reminders_collection.create_index([("target_time", 1)], expireAfterSeconds=172800) 
        interval_collection.create_index([("chat_id", 1)])
        
        # Initialize stats if not exists
        if bot_stats.count_documents({}) == 0:
            bot_stats.insert_one({
                "total_messages_sent": 0,
                "total_notes_saved": 0,
                "total_reminders_set": 0,
                "bot_start_time": datetime.now(IST)
            })
        
        logger.info("Database indexes initialized")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

def save_note(chat_id, note_text):
    """Save note to MongoDB"""
    note = {
        "chat_id": chat_id,
        "note": note_text,
        "created_at": datetime.now(IST),
        "updated_at": datetime.now(IST)
    }
    result = notes_collection.insert_one(note)
    bot_stats.update_one({}, {"$inc": {"total_notes_saved": 1}})
    return result.inserted_id

def get_notes(chat_id, limit=20):
    """Get notes for a chat"""
    return list(notes_collection.find(
        {"chat_id": chat_id},
        {"_id": 0, "note": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit))

def save_reminder(chat_id, target_time_str, messages_count=10):
    """Save reminder to database"""
    try:
        hour, minute = map(int, target_time_str.split(':'))
        now = datetime.now(IST)
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if target_time <= now:
            target_time += timedelta(days=1)
        
        notification_start = target_time - timedelta(minutes=10)
        
        reminder = {
            "chat_id": chat_id,
            "target_time_str": target_time_str,
            "target_time": target_time,
            "notification_start": notification_start,
            "messages_count": messages_count,
            "messages_sent": 0,
            "is_active": True,
            "created_at": datetime.now(IST)
        }
        
        result = reminders_collection.insert_one(reminder)
        
        # We must add the ID to the dict to schedule it
        reminder['_id'] = result.inserted_id
        schedule_reminder_job(reminder)
        
        bot_stats.update_one({}, {"$inc": {"total_reminders_set": 1}})
        return result.inserted_id
    except Exception as e:
        logger.error(f"Error saving reminder: {e}")
        return None

def save_interval_reminder(chat_id, interval_minutes, total_times):
    """Save interval reminder to database"""
    interval_data = {
        "chat_id": chat_id,
        "interval_minutes": interval_minutes,
        "total_times": total_times,
        "times_sent": 0,
        "is_active": True,
        "next_send_time": datetime.now(IST) + timedelta(minutes=interval_minutes),
        "created_at": datetime.now(IST)
    }
    
    result = interval_collection.insert_one(interval_data)
    interval_data['_id'] = result.inserted_id
    
    schedule_interval_job(interval_data)
    return result.inserted_id

# ============= SCHEDULER LOGIC =============
def schedule_reminder_job(reminder):
    """Schedule the START of the reminder sequence"""
    job_id = f"reminder_{str(reminder['_id'])}"
    
    # Check if start time is in the future
    if reminder['notification_start'] > datetime.now(IST):
        trigger = DateTrigger(run_date=reminder['notification_start'], timezone=IST)
        scheduler.add_job(
            start_reminder_notifications,
            trigger,
            id=job_id,
            args=[str(reminder['_id']), reminder['chat_id']],
            replace_existing=True
        )
        logger.info(f"Scheduled reminder {job_id} for {reminder['notification_start']}")
    else:
        # If we missed the start time but it's still active, start immediately!
        logger.info(f"Reminder {job_id} start time passed, starting immediately.")
        start_reminder_notifications(str(reminder['_id']), reminder['chat_id'])

def schedule_interval_job(interval_data):
    """Schedule the next interval message"""
    job_id = f"interval_{str(interval_data['_id'])}"
    
    # Ensure next_send_time is time-zone aware
    run_date = interval_data['next_send_time']
    if run_date.tzinfo is None:
        run_date = IST.localize(run_date)

    scheduler.add_job(
        send_interval_message,
        DateTrigger(run_date=run_date, timezone=IST),
        id=job_id,
        args=[str(interval_data['_id'])],
        replace_existing=True
    )
    logger.info(f"Scheduled interval {job_id} for {run_date}")

def restore_scheduler_jobs():
    """
    CRITICAL: Restore jobs from MongoDB on app restart.
    This fixes the issue where restarts kill active reminders.
    """
    logger.info("🔄 Restoring jobs from database...")
    count = 0
    
    # 1. Restore Standard Reminders
    # Find reminders that are active
    active_reminders = reminders_collection.find({"is_active": True})
    for reminder in active_reminders:
        # If notification_start is in future, schedule it
        if reminder['notification_start'] > datetime.now(IST):
            schedule_reminder_job(reminder)
            count += 1
    
    # 2. Restore Interval Reminders
    active_intervals = interval_collection.find({"is_active": True})
    for interval in active_intervals:
        schedule_interval_job(interval)
        count += 1
        
    logger.info(f"✅ Restored {count} active jobs from database")

# ============= NOTIFICATION LOGIC =============
def start_reminder_notifications(reminder_id, chat_id):
    """Start the sequence of 10 notifications"""
    # Convert string ID back to ObjectId if necessary
    if isinstance(reminder_id, str):
        oid = ObjectId(reminder_id)
    else:
        oid = reminder_id
        
    reminder = reminders_collection.find_one({"_id": oid})
    
    if not reminder or not reminder.get('is_active', True):
        return
    
    logger.info(f"Starting notification sequence for {reminder_id}")
    
    # We use a recursive function with threading.Timer for the sequence
    # Note: If app restarts DURING the 10-min sequence, the remaining msgs are lost.
    # This is an acceptable trade-off for simplicity vs a complex job queue.
    send_notification_sequence(oid, chat_id, 0)

def send_notification_sequence(reminder_id, chat_id, count):
    """Send individual notifications recursively"""
    try:
        reminder = reminders_collection.find_one({"_id": reminder_id})
        
        # Safety check
        if not reminder or not reminder['is_active']:
            return

        if count >= reminder['messages_count']:
            reminders_collection.update_one(
                {"_id": reminder_id},
                {"$set": {"is_active": False, "messages_sent": count}}
            )
            bot.send_message(chat_id, f"✅ Reminder cycle completed for {reminder['target_time_str']}")
            return
        
        minutes_left = 10 - count
        current_time = datetime.now(IST).strftime("%H:%M:%S")
        
        message = f"⏰ *Reminder* ({count + 1}/10)\nTarget: {reminder['target_time_str']}\nLeft: {minutes_left} min\nTime: {current_time}"
        
        bot.send_message(chat_id, message, parse_mode='Markdown')
        
        # Update stats
        bot_stats.update_one({}, {"$inc": {"total_messages_sent": 1}})
        reminders_collection.update_one({"_id": reminder_id}, {"$inc": {"messages_sent": 1}})
        
        # Schedule next message in 60 seconds
        threading.Timer(60.0, send_notification_sequence, args=[reminder_id, chat_id, count + 1]).start()
        
    except Exception as e:
        logger.error(f"Error in notification sequence: {e}")

def send_interval_message(interval_id_str):
    """Send interval message and schedule next"""
    try:
        oid = ObjectId(interval_id_str)
        interval_data = interval_collection.find_one({"_id": oid})
        
        if not interval_data or not interval_data.get('is_active', True):
            return
        
        chat_id = interval_data['chat_id']
        times_sent = interval_data.get('times_sent', 0) + 1
        total_times = interval_data['total_times']
        
        message = f"⏱️ *Interval* {times_sent}/{total_times}\nEvery {interval_data['interval_minutes']} mins\nTime: {datetime.now(IST).strftime('%H:%M:%S')}"
        
        bot.send_message(chat_id, message, parse_mode='Markdown')
        bot_stats.update_one({}, {"$inc": {"total_messages_sent": 1}})
        
        if times_sent >= total_times:
            interval_collection.update_one(
                {"_id": oid},
                {"$set": {"is_active": False, "times_sent": times_sent}}
            )
            bot.send_message(chat_id, "✅ Interval reminders completed!")
        else:
            # Calculate next time
            next_send_time = datetime.now(IST) + timedelta(minutes=interval_data['interval_minutes'])
            
            interval_collection.update_one(
                {"_id": oid},
                {"$set": {"times_sent": times_sent, "next_send_time": next_send_time}}
            )
            
            # Update object for scheduler
            interval_data['next_send_time'] = next_send_time
            schedule_interval_job(interval_data)
            
    except Exception as e:
        logger.error(f"Error sending interval message: {e}")

# ============= TELEGRAM HANDLERS =============
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_msg = (
        "🤖 *Task Management Bot*\n\n"
        "⏰ /time HH:MM - Set reminder (e.g., /time 14:30)\n"
        "⏱️ /settime 5/10 - Interval reminder (e.g., 5 mins, 10 times)\n"
        "📝 /note [text] - Save a note\n"
        "📋 /mynotes - View notes\n"
        "🔄 /myreminders - View active reminders\n"
        "📊 /stats - Bot statistics\n"
        "🌐 /web - Web dashboard link"
    )
    bot.reply_to(message, welcome_msg, parse_mode='Markdown')

@bot.message_handler(commands=['time'])
def handle_time(message):
    chat_id = message.chat.id
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Usage: /time HH:MM\nExample: /time 14:30")
            return
        
        time_str = parts[1]
        if ':' not in time_str:
            raise ValueError
            
        save_reminder(chat_id, time_str)
        bot.reply_to(message, f"✅ Reminder set for {time_str}. Notification sequence starts 10 mins before.")
    except Exception:
        bot.reply_to(message, "❌ Invalid format. Use 24-hour HH:MM format.")

@bot.message_handler(commands=['settime'])
def handle_settime(message):
    chat_id = message.chat.id
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Usage: /settime interval/times\nExample: /settime 5/10 (5 mins, 10 times)")
            return
            
        interval_part, times_part = parts[1].split('/')
        interval = int(interval_part)
        times = int(times_part)
        
        save_interval_reminder(chat_id, interval, times)
        bot.reply_to(message, f"✅ Scheduled: Every {interval} mins, {times} times.")
    except Exception:
        bot.reply_to(message, "❌ Invalid format. Use: interval/times (e.g., 5/10)")

@bot.message_handler(commands=['note'])
def handle_note(message):
    chat_id = message.chat.id
    text = message.text[6:].strip() # Remove '/note '
    if not text:
        bot.reply_to(message, "⚠️ Please provide text. Example: /note Buy milk")
        return
    
    save_note(chat_id, text)
    bot.reply_to(message, "✅ Note saved!")

@bot.message_handler(commands=['mynotes'])
def handle_mynotes(message):
    notes = get_notes(message.chat.id)
    if not notes:
        bot.reply_to(message, "📭 No notes found.")
        return
    
    resp = "*Your Notes:*\n\n"
    for i, n in enumerate(notes, 1):
        resp += f"{i}. {n['note']} ({n['created_at'].strftime('%d/%m %H:%M')})\n"
    bot.reply_to(message, resp, parse_mode='Markdown')

@bot.message_handler(commands=['myreminders'])
def handle_myreminders(message):
    chat_id = message.chat.id
    active_rem = list(reminders_collection.find({"chat_id": chat_id, "is_active": True}))
    active_int = list(interval_collection.find({"chat_id": chat_id, "is_active": True}))
    
    if not active_rem and not active_int:
        bot.reply_to(message, "📭 No active reminders.")
        return
        
    resp = "*Active Reminders:*\n"
    for r in active_rem:
        resp += f"⏰ {r['target_time_str']} (Seq: {r.get('messages_sent', 0)}/10)\n"
    for i in active_int:
        resp += f"⏱️ Every {i['interval_minutes']}m ({i.get('times_sent', 0)}/{i['total_times']})\n"
        
    bot.reply_to(message, resp, parse_mode='Markdown')

@bot.message_handler(commands=['stats'])
def handle_stats(message):
    stats = bot_stats.find_one({}) or {}
    uptime = datetime.now(IST) - stats.get('bot_start_time', datetime.now(IST))
    msg = (
        f"📊 *Stats*\n"
        f"Users: {len(notes_collection.distinct('chat_id'))}\n"
        f"Msgs Sent: {stats.get('total_messages_sent', 0)}\n"
        f"Uptime: {str(uptime).split('.')[0]}"
    )
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['web'])
def handle_web(message):
    bot.reply_to(message, f"🌐 Dashboard: {KOYEB_URL}")

# ============= WEB ROUTES =============
@app.route('/')
def home():
    stats = bot_stats.find_one({}) or {}
    return render_template_string("""
    <html>
    <head><title>Bot Dashboard</title>
    <style>body{font-family:sans-serif;padding:20px;background:#f0f2f5;text-align:center}
    .card{background:white;padding:20px;border-radius:10px;box-shadow:0 2px 5px rgba(0,0,0,0.1);max-width:600px;margin:20px auto}
    h1{color:#333} .stat{font-size:1.2em;margin:10px}
    </style></head>
    <body>
        <div class="card">
            <h1>🤖 Bot Dashboard</h1>
            <p>Status: 🟢 Online</p>
            <div class="stat">Messages Sent: {{ sent }}</div>
            <div class="stat">Notes Saved: {{ notes }}</div>
            <div class="stat">Reminders Set: {{ reminders }}</div>
            <p><small>Timezone: IST | <a href="{{ url }}">Link</a></small></p>
        </div>
    </body></html>
    """, sent=stats.get('total_messages_sent', 0), 
         notes=stats.get('total_notes_saved', 0),
         reminders=stats.get('total_reminders_set', 0),
         url=KOYEB_URL)

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return 'Error', 500
    return 'Bad Request', 400

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now(IST).isoformat()})

# ============= APP LIFECYCLE =============
def setup_webhook():
    """Set webhook securely"""
    try:
        # Only set webhook if we have a valid URL (not localhost)
        if 'koyeb.app' in KOYEB_URL or 'https' in KOYEB_URL:
            webhook_url = f"{KOYEB_URL}/webhook"
            bot.remove_webhook()
            time.sleep(0.5)
            bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook set to: {webhook_url}")
        else:
            logger.warning("⚠️ Skipping webhook setup (Invalid URL)")
    except Exception as e:
        logger.error(f"⚠️ Webhook setup failed: {e}")

def keep_alive():
    """Ping self to prevent sleeping on some free tiers"""
    try:
        requests.get(f"{KOYEB_URL}/health", timeout=5)
    except:
        pass

def initialize_app():
    """Main initialization logic"""
    print("=" * 50)
    print("🚀 STARTING TASK BOT")
    print("=" * 50)
    
    # 1. Init DB
    init_db()
    
    # 2. Start Scheduler
    if not scheduler.running:
        scheduler.start()
        logger.info("✅ Scheduler started")
    
    # 3. Restore Jobs (CRITICAL for Koyeb)
    restore_scheduler_jobs()
    
    # 4. Schedule Keep-alive
    scheduler.add_job(keep_alive, 'interval', minutes=10, id='keep_alive', replace_existing=True)
    
    # 5. Setup Webhook
    setup_webhook()

# ============= ENTRY POINT =============
# This block handles both Gunicorn and direct execution
# We call initialize_app() immediately so it runs on import/startup
initialize_app()

if __name__ == '__main__':
    # Local development
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
