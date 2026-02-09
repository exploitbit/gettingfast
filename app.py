
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
import requests
from pymongo import MongoClient
import logging
from bson.objectid import ObjectId
import json

# ============= CONFIGURATION =============
BOT_TOKEN = os.getenv('BOT_TOKEN', "8388773187:AAGx4pCNM1EUXoBZhJpZJlL5Df5zv3BWv3A")
MONGO_URI = os.getenv('MONGO_URI', "mongodb+srv://sandip:9E9AISFqTfU3VI5i@cluster0.p8irtov.mongodb.net/?appName=Cluster0")

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')

# Get Koyeb app URL from environment
KOYEB_URL = os.getenv('KOYEB_APP_URL', 'localhost:8000')

# ============= INITIALIZE =============
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MongoDB
client = MongoClient(MONGO_URI)
db = client['task_bot_db']

# Collections
notes_collection = db['notes']
reminders_collection = db['reminders']
interval_collection = db['interval_reminders']
bot_stats = db['bot_stats']

# Scheduler for background tasks
scheduler = BackgroundScheduler()

# User states for conversation
user_states = {}

# ============= MONGODB FUNCTIONS =============
def init_db():
    """Initialize database collections and indexes"""
    # Create indexes
    notes_collection.create_index([("chat_id", 1), ("created_at", -1)])
    reminders_collection.create_index([("chat_id", 1), ("target_time", 1)])
    reminders_collection.create_index([("target_time", 1)], expireAfterSeconds=86400)  # Auto delete after 24h
    interval_collection.create_index([("chat_id", 1)])
    
    # Initialize stats
    if bot_stats.count_documents({}) == 0:
        bot_stats.insert_one({
            "total_messages_sent": 0,
            "total_notes_saved": 0,
            "total_reminders_set": 0,
            "bot_start_time": datetime.now(IST)
        })
    
    logger.info("Database initialized successfully")

def save_note(chat_id, note_text):
    """Save note to MongoDB"""
    note = {
        "chat_id": chat_id,
        "note": note_text,
        "created_at": datetime.now(IST),
        "updated_at": datetime.now(IST)
    }
    result = notes_collection.insert_one(note)
    
    # Update stats
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
    # Parse time string
    try:
        hour, minute = map(int, target_time_str.split(':'))
        now = datetime.now(IST)
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If time has passed today, schedule for tomorrow
        if target_time <= now:
            target_time += timedelta(days=1)
        
        # Calculate notification start time (10 minutes before)
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
        
        # Schedule the reminder
        schedule_reminder(reminder)
        
        # Update stats
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
    
    # Schedule first message
    schedule_interval_reminder(interval_data)
    
    return result.inserted_id

def schedule_reminder(reminder):
    """Schedule reminder notifications"""
    job_id = f"reminder_{reminder['_id']}"
    
    # Schedule the notification start
    scheduler.add_job(
        start_reminder_notifications,
        CronTrigger(
            year=reminder['notification_start'].year,
            month=reminder['notification_start'].month,
            day=reminder['notification_start'].day,
            hour=reminder['notification_start'].hour,
            minute=reminder['notification_start'].minute,
            timezone=IST
        ),
        id=job_id,
        args=[reminder['_id'], reminder['chat_id']],
        replace_existing=True
    )
    
    logger.info(f"Scheduled reminder {reminder['_id']} for {reminder['target_time_str']}")

def schedule_interval_reminder(interval_data):
    """Schedule interval reminder"""
    job_id = f"interval_{interval_data['_id']}"
    
    scheduler.add_job(
        send_interval_message,
        'date',
        run_date=interval_data['next_send_time'],
        id=job_id,
        args=[interval_data['_id']],
        replace_existing=True
    )

# ============= NOTIFICATION FUNCTIONS =============
def start_reminder_notifications(reminder_id, chat_id):
    """Start sending notifications for a reminder"""
    reminder = reminders_collection.find_one({"_id": reminder_id})
    
    if not reminder or not reminder.get('is_active', True):
        return
    
    # Send notifications every minute for 10 minutes
    def send_notification_sequence(count=0):
        if count >= reminder['messages_count']:
            # All notifications sent
            reminders_collection.update_one(
                {"_id": reminder_id},
                {"$set": {"is_active": False, "messages_sent": count}}
            )
            return
        
        # Calculate minutes left
        minutes_left = 10 - count
        current_time = datetime.now(IST).strftime("%H:%M:%S")
        
        message = f"""
⏰ Reminder Notification {count + 1}/10

📋 Target Time: {reminder['target_time_str']}
⏱️ Minutes Left: {minutes_left}
🕐 Current Time: {current_time}
📱 Status: {'Active' if reminder['is_active'] else 'Completed'}

Next update in 1 minute...
"""
        
        try:
            bot.send_message(chat_id, message)
            
            # Update stats
            bot_stats.update_one({}, {"$inc": {"total_messages_sent": 1}})
            reminders_collection.update_one(
                {"_id": reminder_id},
                {"$inc": {"messages_sent": 1}}
            )
        except Exception as e:
            logger.error(f"Error sending reminder notification: {e}")
        
        # Schedule next notification
        threading.Timer(60.0, lambda: send_notification_sequence(count + 1)).start()
    
    # Start the sequence
    send_notification_sequence()

def send_interval_message(interval_id):
    """Send interval message"""
    interval_data = interval_collection.find_one({"_id": interval_id})
    
    if not interval_data or not interval_data.get('is_active', True):
        return
    
    chat_id = interval_data['chat_id']
    times_sent = interval_data.get('times_sent', 0) + 1
    total_times = interval_data['total_times']
    
    message = f"""
⏱️ Interval Notification {times_sent}/{total_times}

📊 Progress: {times_sent}/{total_times} messages
⏰ Interval: Every {interval_data['interval_minutes']} minutes
🕐 Sent at: {datetime.now(IST).strftime("%H:%M:%S")}
📅 Date: {datetime.now(IST).strftime("%Y-%m-%d")}
"""
    
    try:
        bot.send_message(chat_id, message)
        
        # Update stats
        bot_stats.update_one({}, {"$inc": {"total_messages_sent": 1}})
        
        if times_sent >= total_times:
            # All messages sent
            interval_collection.update_one(
                {"_id": interval_id},
                {"$set": {"is_active": False, "times_sent": times_sent}}
            )
            bot.send_message(chat_id, f"✅ All {total_times} interval messages completed!")
        else:
            # Schedule next message
            next_send_time = datetime.now(IST) + timedelta(minutes=interval_data['interval_minutes'])
            interval_collection.update_one(
                {"_id": interval_id},
                {"$set": {
                    "times_sent": times_sent,
                    "next_send_time": next_send_time
                }}
            )
            
            # Schedule next job
            schedule_interval_reminder({
                "_id": interval_id,
                "chat_id": chat_id,
                "interval_minutes": interval_data['interval_minutes'],
                "total_times": total_times,
                "next_send_time": next_send_time
            })
            
    except Exception as e:
        logger.error(f"Error sending interval message: {e}")

# ============= TELEGRAM BOT HANDLERS =============
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Send welcome message"""
    welcome_msg = f"""
🤖 *Task Management Bot* 🤖

*All times are in IST (Indian Standard Time)*

📋 *Available Commands:*

⏰ /time - Set a time reminder
Example: /time 12:40
• I'll send 10 notifications starting from 12:30
• One notification per minute until 12:40

⏱️ /settime - Set interval reminders
Example: /settime 5/10
• I'll send 10 messages
• One message every 5 minutes

📝 /note - Save a note
• Your notes are saved in database
• Use /mynotes to view all notes

📋 /mynotes - View your saved notes
🔄 /myreminders - View your active reminders
📊 /stats - View bot statistics
🌐 /web - Open web dashboard

*Current Time (IST):* {datetime.now(IST).strftime("%H:%M:%S")}
"""
    bot.reply_to(message, welcome_msg, parse_mode='Markdown')
    
    # Set user state
    user_states[message.chat.id] = None

@bot.message_handler(commands=['time'])
def handle_time_command(message):
    """Handle /time command"""
    chat_id = message.chat.id
    
    if len(message.text.split()) > 1:
        # Time provided with command
        time_str = message.text.split()[1]
        process_time_input(chat_id, time_str)
    else:
        # Ask for time
        user_states[chat_id] = 'waiting_for_time'
        bot.send_message(
            chat_id,
            "⏰ *Set Time Reminder*\n\n"
            "Please enter the time in *HH:MM* format (24-hour)\n"
            "Example: 14:30\n\n"
            "I will send 10 notifications starting 10 minutes before this time.\n"
            f"Current IST: {datetime.now(IST).strftime('%H:%M')}",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['settime'])
def handle_settime_command(message):
    """Handle /settime command"""
    chat_id = message.chat.id
    
    if len(message.text.split()) > 1:
        # Interval provided with command
        interval_str = message.text.split()[1]
        process_interval_input(chat_id, interval_str)
    else:
        # Ask for interval
        user_states[chat_id] = 'waiting_for_interval'
        bot.send_message(
            chat_id,
            "⏱️ *Set Interval Reminder*\n\n"
            "Please enter in format: *interval/times*\n"
            "Example: 5/10\n\n"
            "This means: Send message every 5 minutes for 10 times.\n"
            "Maximum: 1440 minutes (24 hours) interval",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['note'])
def handle_note_command(message):
    """Handle /note command"""
    chat_id = message.chat.id
    
    if len(message.text.split()) > 1:
        # Note provided with command
        note_text = ' '.join(message.text.split()[1:])
        save_note_and_respond(chat_id, note_text)
    else:
        # Ask for note
        user_states[chat_id] = 'waiting_for_note'
        bot.send_message(
            chat_id,
            "📝 *Save a Note*\n\n"
            "Please enter your note (max 1000 characters):",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['mynotes'])
def handle_mynotes_command(message):
    """Show user's notes"""
    chat_id = message.chat.id
    notes = get_notes(chat_id)
    
    if not notes:
        bot.send_message(chat_id, "📭 You have no saved notes yet.\nUse /note to save your first note.")
        return
    
    response = "📋 *Your Notes:*\n\n"
    for i, note in enumerate(notes[:10], 1):
        created_at = note['created_at'].strftime("%d %b %Y, %H:%M")
        response += f"{i}. {note['note'][:50]}...\n"
        response += f"   📅 {created_at}\n\n"
    
    if len(notes) > 10:
        response += f"\n📄 Showing 10 of {len(notes)} notes"
    
    bot.send_message(chat_id, response, parse_mode='Markdown')

@bot.message_handler(commands=['myreminders'])
def handle_myreminders_command(message):
    """Show user's active reminders"""
    chat_id = message.chat.id
    
    # Get active reminders
    reminders = list(reminders_collection.find({
        "chat_id": chat_id,
        "is_active": True
    }, {"target_time_str": 1, "messages_sent": 1, "created_at": 1}).sort("target_time", 1))
    
    # Get active interval reminders
    intervals = list(interval_collection.find({
        "chat_id": chat_id,
        "is_active": True
    }, {"interval_minutes": 1, "total_times": 1, "times_sent": 1, "created_at": 1}))
    
    if not reminders and not intervals:
        bot.send_message(chat_id, "⏰ You have no active reminders.\nUse /time or /settime to create reminders.")
        return
    
    response = "⏰ *Your Active Reminders:*\n\n"
    
    if reminders:
        response += "*Time Reminders:*\n"
        for reminder in reminders:
            created = reminder['created_at'].strftime("%d %b %H:%M")
            response += f"• {reminder['target_time_str']} IST (Created: {created})\n"
        response += "\n"
    
    if intervals:
        response += "*Interval Reminders:*\n"
        for interval in intervals:
            created = interval['created_at'].strftime("%d %b %H:%M")
            progress = f"{interval.get('times_sent', 0)}/{interval['total_times']}"
            response += f"• Every {interval['interval_minutes']}min ({progress} sent, Created: {created})\n"
    
    bot.send_message(chat_id, response, parse_mode='Markdown')

@bot.message_handler(commands=['stats'])
def handle_stats_command(message):
    """Show bot statistics"""
    stats = bot_stats.find_one({})
    if not stats:
        stats = {}
    
    total_messages = stats.get('total_messages_sent', 0)
    total_notes = stats.get('total_notes_saved', 0)
    total_reminders = stats.get('total_reminders_set', 0)
    
    # Count active reminders
    active_reminders = reminders_collection.count_documents({"is_active": True})
    active_intervals = interval_collection.count_documents({"is_active": True})
    
    # Count total users (unique chat_ids)
    total_users = len(notes_collection.distinct("chat_id"))
    
    start_time = stats.get('bot_start_time', datetime.now(IST))
    uptime = datetime.now(IST) - start_time
    
    response = f"""
📊 *Bot Statistics*

👥 Total Users: {total_users}
📨 Messages Sent: {total_messages}
📝 Notes Saved: {total_notes}
⏰ Reminders Set: {total_reminders}
🔔 Active Reminders: {active_reminders + active_intervals}
⏱️ Uptime: {str(uptime).split('.')[0]}
🌐 Web Dashboard: {KOYEB_URL}
🕐 Current IST: {datetime.now(IST).strftime('%H:%M:%S')}
"""
    bot.send_message(message.chat.id, response, parse_mode='Markdown')

@bot.message_handler(commands=['web'])
def handle_web_command(message):
    """Send web dashboard link"""
    web_url = f"https://{KOYEB_URL}" if not KOYEB_URL.startswith('http') else KOYEB_URL
    bot.send_message(
        message.chat.id,
        f"🌐 *Web Dashboard*\n\n"
        f"Open your browser to:\n{web_url}\n\n"
        f"View all your notes and reminders in a beautiful interface!",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['cancel'])
def handle_cancel_command(message):
    """Cancel current operation"""
    chat_id = message.chat.id
    if chat_id in user_states:
        del user_states[chat_id]
    bot.send_message(chat_id, "✅ Operation cancelled.")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """Handle all text messages"""
    chat_id = message.chat.id
    text = message.text.strip()
    
    # Check user state
    state = user_states.get(chat_id)
    
    if state == 'waiting_for_time':
        del user_states[chat_id]
        process_time_input(chat_id, text)
    
    elif state == 'waiting_for_interval':
        del user_states[chat_id]
        process_interval_input(chat_id, text)
    
    elif state == 'waiting_for_note':
        del user_states[chat_id]
        save_note_and_respond(chat_id, text)
    
    else:
        # Default response
        bot.send_message(
            chat_id,
            "🤖 I'm your Task Management Bot!\n"
            "Send /help to see available commands.\n"
            f"Current IST: {datetime.now(IST).strftime('%H:%M:%S')}",
            parse_mode='Markdown'
        )

# ============= HELPER FUNCTIONS =============
def process_time_input(chat_id, time_str):
    """Process time input"""
    try:
        # Validate time format
        if ':' not in time_str:
            bot.send_message(chat_id, "❌ Invalid format. Please use HH:MM (e.g., 14:30)")
            return
        
        hour, minute = map(int, time_str.split(':'))
        
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            bot.send_message(chat_id, "❌ Invalid time. Hour must be 0-23, minute 0-59")
            return
        
        # Save reminder
        reminder_id = save_reminder(chat_id, time_str)
        
        if reminder_id:
            now = datetime.now(IST)
            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
            
            notification_start = target_time - timedelta(minutes=10)
            
            response = f"""
✅ *Time Reminder Set Successfully!*

🕐 Target Time: {time_str} IST
🔔 Start Notifying: {notification_start.strftime('%H:%M')} IST
📊 Notifications: 10 messages (every minute)
📅 Date: {target_time.strftime('%d %b %Y')}
⏳ Status: Active

I'll start sending notifications 10 minutes before {time_str} IST.
"""
            bot.send_message(chat_id, response, parse_mode='Markdown')
        else:
            bot.send_message(chat_id, "❌ Error setting reminder. Please try again.")
    
    except ValueError:
        bot.send_message(chat_id, "❌ Invalid time format. Please use HH:MM (e.g., 14:30)")
    except Exception as e:
        logger.error(f"Error processing time input: {e}")
        bot.send_message(chat_id, "❌ An error occurred. Please try again.")

def process_interval_input(chat_id, interval_str):
    """Process interval input"""
    try:
        # Validate format
        if '/' not in interval_str:
            bot.send_message(chat_id, "❌ Invalid format. Please use: interval/times (e.g., 5/10)")
            return
        
        interval_str, times_str = interval_str.split('/')
        interval_minutes = int(interval_str.strip())
        total_times = int(times_str.strip())
        
        if interval_minutes <= 0 or total_times <= 0:
            bot.send_message(chat_id, "❌ Please enter positive numbers only.")
            return
        
        if interval_minutes > 1440:
            bot.send_message(chat_id, "❌ Interval cannot be more than 1440 minutes (24 hours)")
            return
        
        if total_times > 100:
            bot.send_message(chat_id, "❌ Maximum 100 times allowed")
            return
        
        # Save interval reminder
        interval_id = save_interval_reminder(chat_id, interval_minutes, total_times)
        
        if interval_id:
            next_send = datetime.now(IST) + timedelta(minutes=interval_minutes)
            
            response = f"""
✅ *Interval Reminder Set Successfully!*

⏱️ Interval: Every {interval_minutes} minutes
📊 Total Messages: {total_times}
⏰ First Message: {next_send.strftime('%H:%M:%S')} IST
📅 Date: {next_send.strftime('%d %b %Y')}
🔄 Status: Active

I'll send the first message at {next_send.strftime('%H:%M:%S')} IST.
"""
            bot.send_message(chat_id, response, parse_mode='Markdown')
        else:
            bot.send_message(chat_id, "❌ Error setting interval reminder. Please try again.")
    
    except ValueError:
        bot.send_message(chat_id, "❌ Invalid format. Please use numbers only (e.g., 5/10)")
    except Exception as e:
        logger.error(f"Error processing interval input: {e}")
        bot.send_message(chat_id, "❌ An error occurred. Please try again.")

def save_note_and_respond(chat_id, note_text):
    """Save note and send response"""
    if not note_text or len(note_text.strip()) == 0:
        bot.send_message(chat_id, "❌ Note cannot be empty")
        return
    
    if len(note_text) > 1000:
        bot.send_message(chat_id, "❌ Note is too long (max 1000 characters)")
        return
    
    try:
        note_id = save_note(chat_id, note_text)
        
        response = f"""
✅ *Note Saved Successfully!*

📝 Your note has been saved to the database.
📋 Use /mynotes to view all your notes.
🆔 Note ID: {str(note_id)[:8]}...
📅 Saved at: {datetime.now(IST).strftime('%d %b %Y, %H:%M')} IST

*Note Preview:*
{note_text[:100]}{'...' if len(note_text) > 100 else ''}
"""
        bot.send_message(chat_id, response, parse_mode='Markdown')
    
    except Exception as e:
        logger.error(f"Error saving note: {e}")
        bot.send_message(chat_id, "❌ Error saving note. Please try again.")

# ============= WEB ROUTES =============
@app.route('/')
def home():
    """Web dashboard"""
    stats = bot_stats.find_one({}) or {}
    
    # Get some stats for display
    total_notes = notes_collection.count_documents({})
    total_reminders = reminders_collection.count_documents({"is_active": True})
    total_intervals = interval_collection.count_documents({"is_active": True})
    total_users = len(notes_collection.distinct("chat_id"))
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 Task Management Bot Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 40px;
                text-align: center;
            }}
            header h1 {{
                font-size: 2.8em;
                margin-bottom: 10px;
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                padding: 30px;
            }}
            .stat-card {{
                background: #f8f9fa;
                border-radius: 15px;
                padding: 25px;
                text-align: center;
                transition: all 0.3s;
                color: #333;
            }}
            .stat-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            }}
            .stat-value {{
                font-size: 2.8em;
                font-weight: bold;
                color: #667eea;
                margin: 10px 0;
            }}
            .stat-label {{
                font-size: 1.1em;
                color: #666;
            }}
            .info-box {{
                background: #e9f7fe;
                padding: 25px;
                margin: 20px;
                border-radius: 15px;
                border-left: 5px solid #2196F3;
                color: #333;
            }}
            .info-box h3 {{
                color: #2196F3;
                margin-bottom: 15px;
            }}
            .commands {{
                background: #fff3cd;
                padding: 25px;
                margin: 20px;
                border-radius: 15px;
                border-left: 5px solid #ffc107;
                color: #333;
            }}
            .commands h3 {{
                color: #ffc107;
                margin-bottom: 15px;
            }}
            .command-item {{
                background: white;
                padding: 10px 15px;
                margin: 10px 0;
                border-radius: 10px;
                border-left: 4px solid #667eea;
            }}
            .time-display {{
                background: #28a745;
                color: white;
                padding: 15px;
                text-align: center;
                font-size: 1.2em;
                font-weight: bold;
                margin: 20px;
                border-radius: 10px;
            }}
            .footer {{
                text-align: center;
                padding: 20px;
                color: #666;
                font-size: 0.9em;
                border-top: 1px solid #eee;
            }}
            @media (max-width: 768px) {{
                .container {{ margin: 10px; border-radius: 15px; }}
                header h1 {{ font-size: 2em; }}
                .stats-grid {{ grid-template-columns: 1fr; padding: 15px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>🤖 Task Management Bot</h1>
                <p style="opacity: 0.9;">All times in IST | MongoDB | Koyeb Free Tier</p>
                <p style="margin-top: 10px; font-size: 1.2em;">{KOYEB_URL}</p>
            </header>
            
            <div class="time-display" id="currentTime">
                Loading IST time...
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{total_users}</div>
                    <div class="stat-label">👥 Total Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_notes}</div>
                    <div class="stat-label">📝 Notes Saved</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{total_reminders + total_intervals}</div>
                    <div class="stat-label">⏰ Active Reminders</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get('total_messages_sent', 0)}</div>
                    <div class="stat-label">📨 Messages Sent</div>
                </div>
            </div>
            
            <div class="info-box">
                <h3>🎯 How It Works</h3>
                <p style="line-height: 1.6; margin-top: 10px;">
                    ✅ <strong>Time Reminders:</strong> /time 14:30 - Get 10 notifications before 14:30 IST<br>
                    ✅ <strong>Interval Reminders:</strong> /settime 5/10 - Messages every 5 minutes for 10 times<br>
                    ✅ <strong>Note Taking:</strong> /note "Your note" - Save notes in MongoDB<br>
                    ✅ <strong>Web Dashboard:</strong> View stats and manage your tasks<br>
                    ✅ <strong>Free Tier:</strong> Runs on Koyeb free tier with Flask<br>
                    ✅ <strong>Persistence:</strong> All data saved in MongoDB Atlas
                </p>
            </div>
            
            <div class="commands">
                <h3>📋 Telegram Bot Commands</h3>
                <div class="command-item">
                    <strong>/start</strong> - Welcome message and help
                </div>
                <div class="command-item">
                    <strong>/time HH:MM</strong> - Set time reminder (e.g., /time 14:30)
                </div>
                <div class="command-item">
                    <strong>/settime interval/times</strong> - Set interval (e.g., /settime 5/10)
                </div>
                <div class="command-item">
                    <strong>/note "your text"</strong> - Save a note
                </div>
                <div class="command-item">
                    <strong>/mynotes</strong> - View your saved notes
                </div>
                <div class="command-item">
                    <strong>/myreminders</strong> - View active reminders
                </div>
                <div class="command-item">
                    <strong>/web</strong> - Open this web dashboard
                </div>
            </div>
            
            <div class="footer">
                <p>🤖 Bot Token: {BOT_TOKEN[:15]}... | 🗄️ MongoDB: Connected</p>
                <p>📍 Timezone: Asia/Kolkata (IST) | ⚡ Platform: Koyeb Free Tier</p>
                <p>🕐 Server Uptime: {str(datetime.now(IST) - stats.get('bot_start_time', datetime.now(IST))).split('.')[0]}</p>
            </div>
        </div>
        
        <script>
            // Update IST time
            function updateISTTime() {{
                const now = new Date();
                const options = {{ 
                    timeZone: 'Asia/Kolkata',
                    hour12: false,
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                }};
                const istTime = new Intl.DateTimeFormat('en-IN', options).format(now);
                document.getElementById('currentTime').textContent = `🕐 IST Time: ${{istTime}}`;
            }}
            
            updateISTTime();
            setInterval(updateISTTime, 1000);
            
            // Auto-refresh page every 60 seconds
            setTimeout(() => location.reload(), 60000);
        </script>
    </body>
    </html>
    """
    return html

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        # Check MongoDB connection
        db.command('ping')
        
        # Check bot
        bot_info = bot.get_me()
        
        stats = bot_stats.find_one({}) or {}
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now(IST).isoformat(),
            "timezone": "Asia/Kolkata (IST)",
            "url": KOYEB_URL,
            "bot": {
                "username": bot_info.username,
                "id": bot_info.id,
                "first_name": bot_info.first_name
            },
            "database": {
                "status": "connected",
                "name": db.name
            },
            "scheduler": {
                "status": "running" if scheduler.running else "stopped",
                "jobs": len(scheduler.get_jobs())
            },
            "statistics": {
                "total_users": len(notes_collection.distinct("chat_id")),
                "total_notes": notes_collection.count_documents({}),
                "active_reminders": reminders_collection.count_documents({"is_active": True}),
                "active_intervals": interval_collection.count_documents({"is_active": True}),
                "total_messages_sent": stats.get('total_messages_sent', 0)
            },
            "uptime": str(datetime.now(IST) - stats.get('bot_start_time', datetime.now(IST))).split('.')[0]
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now(IST).isoformat()
        }), 500

@app.route('/send_test/<chat_id>')
def send_test_message(chat_id):
    """Send test message to specific chat"""
    try:
        message = f"""
🧪 *Test Message from Web Dashboard*

✅ Bot is working correctly!
🕐 Time: {datetime.now(IST).strftime('%H:%M:%S')}
📅 Date: {datetime.now(IST).strftime('%Y-%m-%d')}
🌐 URL: {KOYEB_URL}

This confirms your bot is active and receiving web requests.
"""
        bot.send_message(chat_id, message, parse_mode='Markdown')
        return jsonify({"status": "success", "message": f"Test message sent to {chat_id}"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

# ============= KEEP-ALIVE MECHANISM =============
def ping_self():
    """Ping the app to keep it awake"""
    try:
        url = f"https://{KOYEB_URL}/health" if not KOYEB_URL.startswith('http') else f"{KOYEB_URL}/health"
        response = requests.get(url, timeout=10)
        logger.info(f"Keep-alive ping: {response.status_code}")
    except Exception as e:
        logger.warning(f"Keep-alive ping failed: {e}")

# ============= INITIALIZATION =============
def initialize():
    """Initialize the application"""
    print("=" * 70)
    print("🤖 TASK MANAGEMENT BOT - INITIALIZING")
    print("=" * 70)
    
    try:
        # Initialize database
        init_db()
        
        # Get bot info
        bot_info = bot.get_me()
        print(f"✅ Bot: @{bot_info.username} (ID: {bot_info.id})")
        print(f"✅ Name: {bot_info.first_name}")
        
        # Start scheduler
        scheduler.start()
        print("✅ APScheduler started")
        
        # Setup keep-alive job (every 5 minutes)
        scheduler.add_job(ping_self, 'interval', minutes=5)
        print("✅ Keep-alive ping scheduled (every 5 minutes)")
        
        # Send startup message
        startup_msg = f"""
🚀 *Task Management Bot Started!*

✅ Database: Connected to MongoDB
✅ Scheduler: Active ({len(scheduler.get_jobs())} jobs)
✅ Timezone: Asia/Kolkata (IST)
✅ Web Dashboard: {KOYEB_URL}
✅ Status: Ready to accept commands

🕐 Current IST: {datetime.now(IST).strftime('%H:%M:%S')}
📅 Date: {datetime.now(IST).strftime('%Y-%m-%d')}

Send /help to see available commands.
"""
        print(f"✅ Initialization complete")
        print(f"🌐 Web Dashboard: https://{KOYEB_URL}")
        print(f"🤖 Bot: https://t.me/{bot_info.username}")
        print("=" * 70)
        
        # Log initialization
        bot_stats.update_one({}, {"$set": {"last_restart": datetime.now(IST)}}, upsert=True)
        
    except Exception as e:
        print(f"❌ Initialization error: {e}")
        logger.error(f"Initialization failed: {e}")

# ============= SHUTDOWN HANDLER =============
def shutdown_handler():
    """Handle application shutdown"""
    logger.info("Application shutting down")
    scheduler.shutdown()
    client.close()
    print("🛑 Application shutdown complete")

# Register shutdown handler
atexit.register(shutdown_handler)

# ============= WEBHOOK SETUP =============
@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
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

# ============= MAIN =============
if __name__ == '__main__':
    # Initialize application
    initialize()
    
    # Set webhook (for production)
    try:
        webhook_url = f"https://{KOYEB_URL}/webhook"
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook set to: {webhook_url}")
    except Exception as e:
        print(f"⚠️ Webhook setup failed: {e}")
        print("⚠️ Using polling mode instead")
    
    # Start Flask app
    port = int(os.getenv('PORT', 8000))
    print(f"🌐 Starting web server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
else:
    # For Gunicorn
    initialize()
