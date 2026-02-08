"""
Task Tracker with Telegram Bot - IST Timezone
Enhanced UI with GitHub Storage
"""

import os
import json
import threading
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, Response, render_template_string, jsonify, session, redirect, url_for
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import time
import secrets
import requests
import base64

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"
SECRET_KEY = secrets.token_hex(32)

# GitHub Configuration
GITHUB_TOKEN = "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"
GITHUB_REPO = "Qepheyr/gettingfast"
GITHUB_TASKS_FILE = "tasks.json"
GITHUB_HISTORY_FILE = "history.json"
GITHUB_NOTES_FILE = "notes.json"
GITHUB_SETTINGS_FILE = "settings.json"

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')

# Initialize Flask and Telegram bot
app = Flask(__name__)
app.secret_key = SECRET_KEY
bot = telebot.TeleBot(BOT_TOKEN)

# ============= GITHUB HELPER FUNCTIONS =============
def load_from_github(filename, default_data):
    """Load data from GitHub"""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            content = response.json()["content"]
            decoded = base64.b64decode(content).decode('utf-8')
            return json.loads(decoded)
        elif response.status_code == 404:
            # File doesn't exist yet, return default
            return default_data
        else:
            print(f"GitHub API Error for {filename}: {response.status_code}")
            return default_data
    except Exception as e:
        print(f"Error loading {filename} from GitHub: {e}")
        return default_data

def save_to_github(filename, data):
    """Save data to GitHub"""
    try:
        # First, get the current file to get SHA (for update)
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        get_response = requests.get(url, headers=headers)
        sha = None
        
        if get_response.status_code == 200:
            sha = get_response.json()["sha"]
        
        # Prepare content
        content = json.dumps(data, indent=2, ensure_ascii=False)
        encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        # Create payload
        payload = {
            "message": f"Update {filename} - {get_ist_time().strftime('%Y-%m-%d %H:%M:%S')}",
            "content": encoded,
            "branch": "main"
        }
        
        if sha:
            payload["sha"] = sha
        
        # Make request
        response = requests.put(url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            print(f"✅ Successfully saved {filename} to GitHub")
            return True
        else:
            print(f"❌ GitHub save error for {filename}: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error saving {filename} to GitHub: {e}")
        return False

# ============= DATA MANAGEMENT =============
def get_ist_time():
    """Get current time in IST"""
    return datetime.now(IST)

def format_ist_time(dt, format_str='%Y-%m-%d %H:%M:%S'):
    """Format datetime in IST"""
    if isinstance(dt, str):
        dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
        dt = IST.localize(dt)
    return dt.strftime(format_str)

def parse_ist_time(time_str, date_str=None):
    """Parse time string to IST datetime"""
    if date_str is None:
        date_str = get_ist_time().strftime('%Y-%m-%d')
    
    naive_dt = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
    return IST.localize(naive_dt)

def load_tasks():
    """Load tasks from GitHub"""
    default_tasks = []
    return load_from_github(GITHUB_TASKS_FILE, default_tasks)

def save_tasks(tasks):
    """Save tasks to GitHub"""
    return save_to_github(GITHUB_TASKS_FILE, tasks)

def load_history():
    """Load history from GitHub"""
    default_history = []
    return load_from_github(GITHUB_HISTORY_FILE, default_history)

def save_history(history):
    """Save history to GitHub"""
    return save_to_github(GITHUB_HISTORY_FILE, history)

def load_notes():
    """Load notes from GitHub"""
    default_notes = []
    return load_from_github(GITHUB_NOTES_FILE, default_notes)

def save_notes(notes):
    """Save notes to GitHub"""
    return save_to_github(GITHUB_NOTES_FILE, notes)

def load_settings():
    """Load settings from GitHub"""
    default_settings = {
        'hourly_report': '1',
        'half_hourly_report': '1'
    }
    return load_from_github(GITHUB_SETTINGS_FILE, default_settings)

def save_settings(settings):
    """Save settings to GitHub"""
    return save_to_github(GITHUB_SETTINGS_FILE, settings)

def get_next_task_id():
    """Get next task ID"""
    tasks = load_tasks()
    if not tasks:
        return 1
    return max(task.get('id', 0) for task in tasks) + 1

def get_next_note_id():
    """Get next note ID"""
    notes = load_notes()
    if not notes:
        return 1
    return max(note.get('id', 0) for note in notes) + 1

def get_next_history_id():
    """Get next history ID"""
    history = load_history()
    if not history:
        return 1
    return max(item.get('id', 0) for item in history) + 1

# ============= TELEGRAM FUNCTIONS =============
def send_telegram_message(text, chat_id=USER_ID):
    """Send message to Telegram"""
    try:
        bot.send_message(chat_id, text, parse_mode='HTML')
        print(f"📨 Telegram: {text[:100]}...")
        return True
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False

# ============= NOTIFICATION SYSTEM =============
def check_and_send_notifications():
    """Check and send notifications for tasks starting in 10 minutes"""
    try:
        now = get_ist_time()
        print(f"⏰ Notification check at {now.strftime('%H:%M:%S')} IST")
        
        tasks = load_tasks()
        print(f"📋 Found {len(tasks)} active tasks")
        
        for task in tasks:
            try:
                if not task:
                    continue
                    
                task_id = task.get('id')
                task_title = task.get('title', '')
                completed = task.get('completed', 0)
                notify_enabled = task.get('notify_enabled', 1)
                last_notified_minute = task.get('last_notified_minute', -1)
                
                if completed or not notify_enabled:
                    continue
                
                start_time_str = task.get('start_time')
                if not start_time_str:
                    continue
                    
                start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
                start_time = IST.localize(start_time)
                
                # Calculate minutes until task starts
                minutes_until_start = int((start_time - now).total_seconds() / 60)
                
                print(f"   Task '{task_title}': Starts at {start_time.strftime('%H:%M')} IST, {minutes_until_start} minutes from now")
                
                # If task starts in 1-10 minutes, send notification
                if 1 <= minutes_until_start <= 10:
                    # Only send if we haven't notified for this specific minute
                    if last_notified_minute != minutes_until_start:
                        message = f"⏰ <b>Task Reminder</b>\n"
                        message += f"📝 <b>{task_title}</b>\n"
                        message += f"🕐 Starts in {minutes_until_start} minute"
                        if minutes_until_start > 1:
                            message += "s"
                        message += f"\n📅 {start_time.strftime('%I:%M %p')} IST"
                        
                        if send_telegram_message(message):
                            # Update last notified minute
                            task['last_notified_minute'] = minutes_until_start
                            tasks = load_tasks()
                            for t in tasks:
                                if t.get('id') == task_id:
                                    t['last_notified_minute'] = minutes_until_start
                            save_tasks(tasks)
                            print(f"   ✅ Sent notification: {minutes_until_start} minutes before")
                
                # Reset notification counter if task has passed
                elif minutes_until_start <= 0 and last_notified_minute != 0:
                    tasks = load_tasks()
                    for t in tasks:
                        if t.get('id') == task_id:
                            t['last_notified_minute'] = 0
                    save_tasks(tasks)
                    print(f"   🔄 Reset notifications for task {task_id}")
                    
            except Exception as e:
                print(f"   ❌ Error with task: {e}")
        
    except Exception as e:
        print(f"❌ Notification system error: {e}")
        import traceback
        traceback.print_exc()

def send_half_hourly_report():
    """Send half-hourly task status report"""
    try:
        now = get_ist_time()
        today = now.strftime('%Y-%m-%d')
        
        # Get today's tasks
        all_tasks = load_tasks()
        tasks = [task for task in all_tasks if task.get('start_time', '').startswith(today)]
        
        # Get setting
        settings = load_settings()
        if settings.get('half_hourly_report') != '1':
            return
        
        if not tasks:
            message = "━━━━━━━━━━━━━━━━━━━━\n"
            message += "📊 <b>30-Minute Report</b>\n"
            message += "━━━━━━━━━━━━━━━━━━━━\n"
            message += f"🕐 Time: {now.strftime('%I:%M %p')} IST\n"
            message += f"📅 Date: {now.strftime('%B %d, %Y')}\n"
            message += "✅ <i>No active tasks for today!</i>"
        else:
            completed = sum(1 for t in tasks if t.get('completed', 0))
            total = len(tasks)
            
            message = "━━━━━━━━━━━━━━━━━━━━\n"
            message += "📊 <b>30-Minute Report</b>\n"
            message += "━━━━━━━━━━━━━━━━━━━━\n"
            message += f"🕐 Time: {now.strftime('%I:%M %p')} IST\n"
            message += f"📅 Date: {now.strftime('%B %d, %Y')}\n"
            message += f"📋 Tasks: {completed}/{total} completed\n\n"
            
            for task in tasks:
                status = "✅" if task.get('completed', 0) else "⏳"
                start_time = datetime.strptime(task.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
                start_time = IST.localize(start_time)
                end_time = datetime.strptime(task.get('end_time', ''), '%Y-%m-%d %H:%M:%S')
                end_time = IST.localize(end_time)
                
                # Get subtask progress
                subtasks = task.get('subtasks', [])
                completed_subtasks = sum(1 for st in subtasks if st.get('completed', 0))
                total_subtasks = len(subtasks)
                
                progress = f" ({completed_subtasks}/{total_subtasks})" if total_subtasks > 0 else ""
                
                message += f"{status} <b>{task.get('title', '')}</b>{progress}\n"
                message += f"   ⏰ {start_time.strftime('%I:%M')} - {end_time.strftime('%I:%M %p')}\n"
        
        send_telegram_message(message)
        
    except Exception as e:
        print(f"❌ Half-hourly report error: {e}")

def check_note_notifications():
    """Check and send note notifications based on interval"""
    try:
        now = get_ist_time()
        
        notes = load_notes()
        for note in notes:
            note_id = note.get('id')
            notify_enabled = note.get('notify_enabled', 0)
            interval_hours = note.get('notify_interval', 0)
            last_notified = note.get('last_notified')
            
            if not notify_enabled or interval_hours <= 0:
                continue
            
            should_notify = False
            
            if last_notified:
                last_time = datetime.strptime(last_notified, '%Y-%m-%d %H:%M:%S')
                last_time = IST.localize(last_time)
                hours_since = (now - last_time).total_seconds() / 3600
                should_notify = hours_since >= interval_hours
            else:
                should_notify = True
            
            if should_notify:
                message = "━━━━━━━━━━━━━━━━━━━━\n"
                message += f"📝 <b>Note Reminder</b>\n"
                message += "━━━━━━━━━━━━━━━━━━━━\n"
                message += f"📌 <b>{note.get('title', '')}</b>\n"
                message += f"🔄 Interval: Every {interval_hours} hours\n"
                message += f"⏰ Time: {now.strftime('%I:%M %p')} IST\n"
                
                description = note.get('description', '')
                if description:
                    desc = description[:200]
                    if len(description) > 200:
                        desc += "..."
                    message += f"\n<blockquote>{desc}</blockquote>"
                
                if send_telegram_message(message):
                    # Update last notified time
                    notes = load_notes()
                    for n in notes:
                        if n.get('id') == note_id:
                            n['last_notified'] = now.strftime('%Y-%m-%d %H:%M:%S')
                    save_notes(notes)
                    
    except Exception as e:
        print(f"❌ Note notification error: {e}")

def scheduler_thread():
    """Run scheduler in background thread"""
    print("🔄 Starting scheduler thread in IST...")
    
    while True:
        try:
            # Check notifications every minute
            check_and_send_notifications()
            
            # Check note notifications
            check_note_notifications()
            
            # Check for half-hourly report
            now = get_ist_time()
            
            # Send half-hourly report at minutes 0 and 30
            if now.minute == 0 or now.minute == 30:
                print("📊 Sending half-hourly report...")
                send_half_hourly_report()
                time.sleep(60)  # Sleep 1 minute to avoid duplicate
            
            # Calculate seconds until next minute
            seconds_to_wait = 60 - now.second
            time.sleep(seconds_to_wait)
            
        except Exception as e:
            print(f"❌ Scheduler error: {e}")
            time.sleep(60)

# Start scheduler thread
scheduler = threading.Thread(target=scheduler_thread, daemon=True)
scheduler.start()

# ============= TELEGRAM BOT COMMANDS =============
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Send welcome message with inline buttons"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ <b>Unauthorized Access</b>\n\nThis bot is private and only accessible to authorized users.")
        return
    
    now = get_ist_time()
    
    # Create inline keyboard
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📋 Today's Tasks", callback_data='today_tasks'),
        InlineKeyboardButton("📊 Summary", callback_data='summary'),
        InlineKeyboardButton("⏰ Current Time", callback_data='current_time'),
        InlineKeyboardButton("🔄 Test", callback_data='test_notification'),
        InlineKeyboardButton("🌐 Open Web App", web_app=WebAppInfo(url=f"https://patient-maxie-sandip232-786edcb8.koyeb.app/")),
        InlineKeyboardButton("🔙 Back", callback_data='back_to_main')
    )
    
    welcome = f"""
━━━━━━━━━━━━━━━━━━━━
🤖 <b>Task Tracker Bot</b>
━━━━━━━━━━━━━━━━━━━━

⏰ <i>Current Time:</i> <b>{now.strftime('%I:%M %p')} IST</b>
📅 <i>Date:</i> <b>{now.strftime('%B %d, %Y')}</b>

━━━━━━━━━━━━━━━━━━━━
🎯 <b>Available Commands:</b>
━━━━━━━━━━━━━━━━━━━━

• <code>/start</code> - Show this menu
• <code>/today</code> - View today's tasks
• <code>/summary</code> - Get daily summary

━━━━━━━━━━━━━━━━━━━━
🔔 <b>Notifications:</b>
━━━━━━━━━━━━━━━━━━━━

• ⏰ 1 notification per minute for 10 minutes before task starts
• 📊 Task reports every 30 minutes
• ⏲️ All times in IST

━━━━━━━━━━━━━━━━━━━━
🌐 <b>Web Interface:</b>
━━━━━━━━━━━━━━━━━━━━

https://patient-maxie-sandip232-786edcb8.koyeb.app/
"""
    bot.send_message(message.chat.id, welcome, parse_mode='HTML', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """Handle inline button callbacks"""
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    if str(chat_id) != USER_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized")
        return
    
    if call.data == 'today_tasks':
        send_today_tasks_callback(chat_id, message_id)
    elif call.data == 'summary':
        send_daily_summary_callback(chat_id, message_id)
    elif call.data == 'current_time':
        send_current_time_callback(chat_id, message_id)
    elif call.data == 'test_notification':
        send_test_notification_callback(chat_id, message_id)
    elif call.data == 'back_to_main':
        bot.delete_message(chat_id, message_id)
        send_welcome(call.message)
    
    bot.answer_callback_query(call.id)

def send_today_tasks_callback(chat_id, message_id):
    """Send today's tasks via callback"""
    now = get_ist_time()
    today = now.strftime('%Y-%m-%d')
    all_tasks = load_tasks()
    tasks = [task for task in all_tasks if task.get('start_time', '').startswith(today)]
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    
    if not tasks:
        response = "━━━━━━━━━━━━━━━━━━━━\n"
        response += "📅 <b>Today's Tasks</b>\n"
        response += "━━━━━━━━━━━━━━━━━━━━\n\n"
        response += f"📅 Date: {now.strftime('%B %d, %Y')}\n"
        response += f"⏰ Time: {now.strftime('%I:%M %p')} IST\n\n"
        response += "✅ <i>No tasks for today! 🎉</i>"
        
        bot.edit_message_text(response, chat_id, message_id, parse_mode='HTML', reply_markup=keyboard)
        return
    
    response = "━━━━━━━━━━━━━━━━━━━━\n"
    response += "📅 <b>Today's Tasks</b>\n"
    response += "━━━━━━━━━━━━━━━━━━━━\n\n"
    response += f"📅 Date: {now.strftime('%B %d, %Y')}\n"
    response += f"⏰ Time: {now.strftime('%I:%M %p')} IST\n\n"
    
    for task in tasks:
        status = "✅" if task.get('completed', 0) else "⏳"
        start_time = datetime.strptime(task.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
        start_time = IST.localize(start_time)
        end_time = datetime.strptime(task.get('end_time', ''), '%Y-%m-%d %H:%M:%S')
        end_time = IST.localize(end_time)
        
        # Get subtask progress
        subtasks = task.get('subtasks', [])
        completed_subtasks = sum(1 for st in subtasks if st.get('completed', 0))
        total_subtasks = len(subtasks)
        
        progress = f" ({completed_subtasks}/{total_subtasks})" if total_subtasks > 0 else ""
        
        response += f"{status} <b>{task.get('title', '')}</b>{progress}\n"
        response += f"   ⏰ {start_time.strftime('%I:%M')} - {end_time.strftime('%I:%M %p')}\n\n"
    
    bot.edit_message_text(response, chat_id, message_id, parse_mode='HTML', reply_markup=keyboard)

def send_daily_summary_callback(chat_id, message_id):
    """Send daily summary via callback"""
    send_daily_summary()
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    
    bot.edit_message_text("📊 <b>Summary sent to your Telegram!</b>", chat_id, message_id, parse_mode='HTML', reply_markup=keyboard)

def send_current_time_callback(chat_id, message_id):
    """Send current IST time via callback"""
    now = get_ist_time()
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    
    time_msg = "━━━━━━━━━━━━━━━━━━━━\n"
    time_msg += "⏰ <b>Current Time</b>\n"
    time_msg += "━━━━━━━━━━━━━━━━━━━━\n\n"
    time_msg += f"🕐 <b>IST:</b> {now.strftime('%I:%M:%S %p')}\n"
    time_msg += f"📅 <b>Date:</b> {now.strftime('%B %d, %Y')}\n"
    time_msg += f"🌍 <b>Timezone:</b> Asia/Kolkata\n\n"
    time_msg += f"<i>Timezone set to Indian Standard Time</i>"
    
    bot.send_message(chat_id, time_msg, parse_mode='HTML', reply_markup=keyboard)

def send_test_notification_callback(chat_id, message_id):
    """Send test notification via callback"""
    now = get_ist_time()
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    
    test_msg = "━━━━━━━━━━━━━━━━━━━━\n"
    test_msg += "🔔 <b>Test Notification</b>\n"
    test_msg += "━━━━━━━━━━━━━━━━━━━━\n\n"
    test_msg += "✅ <b>Bot is working perfectly!</b>\n"
    test_msg += f"⏰ Time: {now.strftime('%H:%M:%S')} IST\n"
    test_msg += f"📅 Date: {now.strftime('%B %d, %Y')}\n\n"
    test_msg += "<i>All systems operational! 🚀</i>"
    
    if send_telegram_message(test_msg, chat_id):
        bot.edit_message_text("✅ <b>Test notification sent successfully!</b>", chat_id, message_id, parse_mode='HTML', reply_markup=keyboard)
    else:
        bot.edit_message_text("❌ <b>Failed to send test notification</b>", chat_id, message_id, parse_mode='HTML', reply_markup=keyboard)

@bot.message_handler(commands=['today'])
def send_today_tasks(message):
    """Send today's tasks"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ <b>Unauthorized Access</b>")
        return
    
    now = get_ist_time()
    today = now.strftime('%Y-%m-%d')
    all_tasks = load_tasks()
    tasks = [task for task in all_tasks if task.get('start_time', '').startswith(today)]
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_main'))
    
    if not tasks:
        response = "━━━━━━━━━━━━━━━━━━━━\n"
        response += "📅 <b>Today's Tasks</b>\n"
        response += "━━━━━━━━━━━━━━━━━━━━\n\n"
        response += f"📅 Date: {now.strftime('%B %d, %Y')}\n"
        response += f"⏰ Time: {now.strftime('%I:%M %p')} IST\n\n"
        response += "✅ <i>No tasks for today! 🎉</i>"
        
        bot.reply_to(message, response, parse_mode='HTML', reply_markup=keyboard)
        return
    
    response = "━━━━━━━━━━━━━━━━━━━━\n"
    response += "📅 <b>Today's Tasks</b>\n"
    response += "━━━━━━━━━━━━━━━━━━━━\n\n"
    response += f"📅 Date: {now.strftime('%B %d, %Y')}\n"
    response += f"⏰ Time: {now.strftime('%I:%M %p')} IST\n\n"
    
    for task in tasks:
        status = "✅" if task.get('completed', 0) else "⏳"
        start_time = datetime.strptime(task.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
        start_time = IST.localize(start_time)
        end_time = datetime.strptime(task.get('end_time', ''), '%Y-%m-%d %H:%M:%S')
        end_time = IST.localize(end_time)
        
        response += f"{status} <b>{task.get('title', '')}</b>\n"
        response += f"   ⏰ {start_time.strftime('%I:%M')} - {end_time.strftime('%I:%M %p')}\n\n"
    
    bot.reply_to(message, response, parse_mode='HTML', reply_markup=keyboard)

@bot.message_handler(commands=['summary'])
def send_summary(message):
    """Send summary"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ <b>Unauthorized Access</b>")
        return
    
    send_daily_summary()
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_main'))
    
    bot.reply_to(message, "📊 <b>Daily summary sent to your Telegram!</b>", parse_mode='HTML', reply_markup=keyboard)

def send_daily_summary():
    """Send daily task summary"""
    try:
        now = get_ist_time()
        today = now.strftime('%Y-%m-%d')
        
        # Get today's tasks
        all_tasks = load_tasks()
        tasks = [task for task in all_tasks if task.get('start_time', '').startswith(today)]
        
        if not tasks:
            message = "━━━━━━━━━━━━━━━━━━━━\n"
            message += "📊 <b>Daily Summary</b>\n"
            message += "━━━━━━━━━━━━━━━━━━━━\n\n"
            message += f"📅 Date: {now.strftime('%B %d, %Y')}\n"
            message += f"⏰ Time: {now.strftime('%I:%M %p')} IST\n\n"
            message += "✅ <i>No tasks for today! 🎉</i>"
            send_telegram_message(message)
            return
        
        completed = sum(1 for t in tasks if t.get('completed', 0))
        total = len(tasks)
        
        message = "━━━━━━━━━━━━━━━━━━━━\n"
        message += "📊 <b>Daily Summary</b>\n"
        message += "━━━━━━━━━━━━━━━━━━━━\n\n"
        message += f"📅 Date: {now.strftime('%B %d, %Y')}\n"
        message += f"⏰ Time: {now.strftime('%I:%M %p')} IST\n"
        message += f"📋 Tasks: <b>{completed}/{total}</b> completed\n\n"
        
        for task in tasks:
            status = "✅" if task.get('completed', 0) else "⏳"
            start_time = datetime.strptime(task.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
            start_time = IST.localize(start_time)
            message += f"{status} <b>{task.get('title', '')}</b> ({start_time.strftime('%I:%M %p')})\n"
        
        send_telegram_message(message)
        
    except Exception as e:
        print(f"❌ Daily summary error: {e}")

# ============= WEBHOOK ENDPOINT =============
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
            print(f"Webhook error: {e}")
            return 'Error', 500
    return 'Bad Request', 400

# ============= HELPER FUNCTIONS =============
def format_text(text):
    """Format text with markdown-like syntax"""
    if not text:
        return ""
    
    # Convert newlines to <br>
    text = text.replace('\n', '<br>')
    
    # Convert *bold* to <strong>
    import re
    text = re.sub(r'\*(.*?)\*', r'<strong>\1</strong>', text)
    
    # Convert _italic_ to <em>
    text = re.sub(r'_(.*?)_', r'<em>\1</em>', text)
    
    return text

def calculate_time_status(start_time, end_time, is_active, completed):
    """Calculate time status for display"""
    if completed:
        return {
            'text': 'Completed',
            'status': 'completed',
            'class': 'upcoming'
        }
    
    if not is_active:
        return {
            'text': 'Inactive',
            'status': 'inactive',
            'class': 'upcoming'
        }
    
    now = get_ist_time()
    start_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
    start_dt = IST.localize(start_dt)
    end_dt = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
    end_dt = IST.localize(end_dt)
    
    # Convert to minutes for easier comparison
    current_minutes = now.hour * 60 + now.minute
    start_minutes = start_dt.hour * 60 + start_dt.minute
    end_minutes = end_dt.hour * 60 + end_dt.minute
    
    two_hours = 120  # 2 hours in minutes
    
    if current_minutes < (start_minutes - two_hours):
        # More than 2 hours before start
        return {
            'text': 'Upcoming',
            'status': 'upcoming',
            'class': 'upcoming'
        }
    elif current_minutes >= (start_minutes - two_hours) and current_minutes < start_minutes:
        # Within 2 hours of start
        minutes_before = start_minutes - current_minutes
        hours = minutes_before // 60
        minutes = minutes_before % 60
        
        if hours > 0:
            return {
                'text': f'Starts in {hours}h {minutes}m',
                'status': 'starting_soon',
                'class': 'starting_soon'
            }
        else:
            return {
                'text': f'Starts in {minutes}m',
                'status': 'starting_soon',
                'class': 'starting_soon'
            }
    elif current_minutes >= start_minutes and current_minutes <= end_minutes:
        # During task time
        minutes_left = end_minutes - current_minutes
        hours = minutes_left // 60
        minutes = minutes_left % 60
        
        if hours > 0:
            return {
                'text': f'{hours}h {minutes}m left',
                'status': 'active',
                'class': 'active'
            }
        else:
            return {
                'text': f'{minutes}m left',
                'status': 'active',
                'class': 'active'
            }
    elif current_minutes > end_minutes and current_minutes <= (end_minutes + two_hours):
        # Within 2 hours after end
        minutes_over = current_minutes - end_minutes
        hours = minutes_over // 60
        minutes = minutes_over % 60
        
        if hours > 0:
            return {
                'text': f'Due by {hours}h {minutes}m',
                'status': 'due',
                'class': 'due'
            }
        else:
            return {
                'text': f'Due by {minutes}m',
                'status': 'due',
                'class': 'due'
            }
    else:
        # More than 2 hours after end
        return {
            'text': 'Overdue',
            'status': 'overdue',
            'class': 'overdue'
        }

# ============= FLASK ROUTES =============
@app.route('/')
def index():
    """Main web interface"""
    # Check if user is logged in (using session)
    if not session.get('logged_in'):
        # No login required - auto-login
        session['logged_in'] = True
    
    # Get current view
    view = request.args.get('view', 'tasks')
    
    # Get current IST time
    now = get_ist_time()
    today = now.strftime('%Y-%m-%d')
    
    # Get all tasks (not just today's)
    all_tasks = load_tasks()
    
    # Get history
    history = load_history()
    
    # Get notes
    notes = load_notes()
    
    # Get settings
    settings = load_settings()
    
    # Calculate stats
    tasks_today = [task for task in all_tasks if task.get('start_time', '').startswith(today)]
    completed_today = sum(1 for t in tasks_today if t.get('completed', 0))
    pending_today = len(tasks_today) - completed_today
    
    # Process tasks for display
    processed_tasks = []
    for task in all_tasks:  # Show all tasks, not just today's
        if not task:
            continue
            
        # Get subtasks
        subtasks = task.get('subtasks', [])
        
        completed_subtasks = sum(1 for st in subtasks if st.get('completed', 0))
        total_subtasks = len(subtasks)
        progress_percentage = round((completed_subtasks / total_subtasks * 100)) if total_subtasks > 0 else 0
        
        # Format times
        start_dt = datetime.strptime(task.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
        start_dt = IST.localize(start_dt)
        end_dt = datetime.strptime(task.get('end_time', ''), '%Y-%m-%d %H:%M:%S')
        end_dt = IST.localize(end_dt)
        
        # Calculate time status
        time_info = calculate_time_status(
            task.get('start_time', ''),
            task.get('end_time', ''),
            not task.get('completed', 0),
            task.get('completed', 0)
        )
        
        processed_tasks.append({
            'id': task.get('id'),
            'title': task.get('title', ''),
            'description': task.get('description', ''),
            'start_time': task.get('start_time', ''),
            'end_time': task.get('end_time', ''),
            'start_display': start_dt.strftime('%I:%M %p'),
            'end_display': end_dt.strftime('%I:%M %p'),
            'date_range': start_dt.strftime('%b %d'),
            'time_range': f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}",
            'completed': task.get('completed', 0),
            'notify_enabled': task.get('notify_enabled', 1),
            'priority': task.get('priority', 15),
            'repeat': task.get('repeat', 'none'),
            'repeat_day': task.get('repeat_day'),
            'subtasks': subtasks,
            'completed_subtasks': completed_subtasks,
            'total_subtasks': total_subtasks,
            'progress_percentage': progress_percentage,
            'time_status': time_info,
            'is_active': not task.get('completed', 0),
            'is_completed_repeating': task.get('repeat', 'none') != 'none' and task.get('completed', 0)
        })
    
    # Process notes for display
    processed_notes = []
    for note in notes:
        if not note:
            continue
            
        created_at = datetime.strptime(note.get('created_at', ''), '%Y-%m-%d %H:%M:%S')
        created_at = IST.localize(created_at)
        updated_at = datetime.strptime(note.get('updated_at', ''), '%Y-%m-%d %H:%M:%S')
        updated_at = IST.localize(updated_at)
        
        processed_notes.append({
            'id': note.get('id'),
            'title': note.get('title', ''),
            'description': note.get('description', ''),
            'priority': note.get('priority', 1),
            'created_at': note.get('created_at', ''),
            'updated_at': note.get('updated_at', ''),
            'created_display': created_at.strftime('%b %d, %Y'),
            'updated_display': updated_at.strftime('%b %d, %Y'),
            'notify_enabled': note.get('notify_enabled', 0),
            'notify_interval': note.get('notify_interval', 0)
        })
    
    # Process history for display
    history_with_subtasks = []
    for item in history:
        if not item:
            continue
        item_dict = item.copy()
        item_dict['subtasks'] = item.get('subtasks', [])
        history_with_subtasks.append(item_dict)
    
    # Render the HTML template
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en" id="theme-element">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Task Tracker</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            /* CSS remains exactly the same as before */
            :root {
                --primary: #4361ee; --primary-light: #4895ef; --secondary: #3f37c9; --success: #4cc9f0; --danger: #f72585; --warning: #f8961e; --info: #4895ef; --light: #f8f9fa; --dark: #212529; --gray: #6c757d; --gray-light: #adb5bd; --border-radius: 12px; --shadow: 0 4px 6px rgba(0, 0, 0, 0.1); --transition: all 0.3s ease;
                --pink-bg: rgba(255, 182, 193, 0.1); --blue-bg: rgba(173, 216, 230, 0.15); --blue-bg-hover: rgba(173, 216, 230, 0.25);
                --note-bg: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                --note-shadow: 0 8px 32px rgba(31, 38, 135, 0.1);
                --completed-bg: rgba(108, 117, 125, 0.1);
                --completed-text: #6c757d;
                --notify-bg: rgba(248, 150, 30, 0.1);
                --notify-color: #f8961e;
            }
            
            @media (prefers-color-scheme: dark) {
                :root {
                    --primary: #5a6ff0; --primary-light: #6a80f2; --secondary: #4f46e5; --success: #5fd3f0; --danger: #ff2d8e; --warning: #ffa94d; --info: #6a80f2; --light: #121212; --dark: #ffffff; --gray: #94a3b8; --gray-light: #475569; --shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
                    --pink-bg: rgba(255, 182, 193, 0.05); --blue-bg: rgba(173, 216, 230, 0.08); --blue-bg-hover: rgba(173, 216, 230, 0.15);
                    --note-bg: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                    --note-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                    --completed-bg: rgba(108, 117, 125, 0.2);
                    --completed-text: #94a3b8;
                    --notify-bg: rgba(248, 150, 30, 0.2);
                    --notify-color: #ffa94d;
                }
            }
            
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            body { background-color: var(--light); color: var(--dark); transition: var(--transition); min-height: 100vh; display: flex; flex-direction: column; font-size: 14px; }
            
            /* Header Styles */
            .header { 
                background-color: var(--light); 
                padding: 8px 16px; 
                display: flex; 
                align-items: center; 
                justify-content: space-between; 
                box-shadow: var(--shadow); 
                position: sticky; 
                top: 0; 
                z-index: 100; 
                gap: 4px;
                flex-wrap: nowrap;
            }
            
            .header-action-btn {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                background: var(--primary);
                color: white;
                border: none;
                border-radius: 12px;
                padding: 10px 6px;
                cursor: pointer;
                transition: var(--transition);
                box-shadow: var(--shadow);
                gap: 4px;
                flex: 1;
                min-width: 0;
                max-width: 25%;
            }
            
            .header-action-btn i { font-size: 1.1rem; }
            .header-action-btn span { font-size: 0.7rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
            .header-action-btn:hover { background: var(--primary-light); transform: translateY(-2px); }
            .header-action-btn:active, .action-btn:active, .btn:active, button:active { transform: none !important; box-shadow: var(--shadow) !important; }
            
            @media (max-width: 768px) {
                .header { padding: 8px; gap: 2px; }
                .header-action-btn { 
                    padding: 8px 4px;
                    border-radius: 10px;
                }
                .header-action-btn span { font-size: 0.65rem; }
                .header-action-btn i { font-size: 1rem; }
            }

            /* Floating Action Buttons */
            .fab {
                position: fixed;
                width: 60px;
                height: 60px;
                background-color: var(--primary);
                color: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.5rem;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
                cursor: pointer;
                transition: var(--transition);
                z-index: 1000;
                border: none;
            }
            
            .fab:hover {
                background-color: var(--primary-light);
                transform: scale(1.1);
                box-shadow: 0 6px 16px rgba(0, 0, 0, 0.3);
            }
            
            .fab-tasks {
                bottom: 30px;
                right: 30px;
            }
            
            .fab-notes {
                bottom: 30px;
                right: 30px;
            }
            
            @media (max-width: 768px) {
                .fab {
                    width: 50px;
                    height: 50px;
                    font-size: 1.3rem;
                }
                
                .fab-tasks {
                    bottom: 20px;
                    right: 20px;
                }
                
                .fab-notes {
                    bottom: 20px;
                    right: 20px;
                }
            }

            .main-content { flex-grow: 1; padding: 16px; overflow-y: auto; padding-bottom: 100px; }
            .view-content { display: none; }
            .view-content.active { display: block; animation: fadeIn 0.5s ease; }
            .content-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
            .page-title { font-size: 1.5rem; font-weight: 700; color: var(--dark); }
            
            .bucket-header { display: flex; align-items: center; margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--gray-light); flex-wrap: wrap; gap: 10px;}
            .bucket-title { font-size: 1.2rem; font-weight: 600; color: var(--dark); display: flex; align-items: center; gap: 8px; }
            .bucket-count { background-color: var(--primary); color: white; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-size: 0.8rem; }
            
            .items-container { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; width: 100%; }
            @media (max-width: 1200px) { .items-container { grid-template-columns: repeat(2, 1fr) !important; } }
            @media (max-width: 768px) { .items-container { grid-template-columns: 1fr !important; } }
            
            .task-card { 
                background-color: var(--pink-bg); 
                border-radius: var(--border-radius); 
                padding: 16px; 
                box-shadow: var(--shadow); 
                transition: var(--transition); 
                animation: slideIn 0.3s ease; 
                display: flex; 
                flex-direction: column; 
                min-height: 140px;
                position: relative;
            }
            
            .task-card.completed-repeating {
                background-color: var(--completed-bg);
                opacity: 0.8;
            }
            
            .task-card.completed-repeating .task-title,
            .task-card.completed-repeating .task-description,
            .task-card.completed-repeating .task-date-range,
            .task-card.completed-repeating .task-time-range,
            .task-card.completed-repeating .repeat-badge,
            .task-card.completed-repeating .priority-badge {
                color: var(--completed-text);
            }
            
            .task-card.completed-repeating .action-btn {
                background-color: var(--completed-text);
            }
            
            .task-card.completed-repeating .action-btn:hover {
                background-color: var(--completed-text);
                transform: scale(1);
            }
            
            .notify-badge {
                background-color: var(--notify-bg);
                color: var(--notify-color);
                padding: 2px 8px;
                border-radius: 20px;
                font-size: 0.65rem;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 4px;
            }
            
            .next-occurrence-info {
                background-color: rgba(67, 97, 238, 0.1);
                border-radius: 8px;
                padding: 8px 12px;
                margin-bottom: 12px;
                font-size: 0.75rem;
                color: var(--primary);
                display: flex;
                align-items: center;
                gap: 8px;
                border-left: 3px solid var(--primary);
            }
            
            .next-occurrence-info i {
                font-size: 0.9rem;
            }
            
            @media (prefers-color-scheme: dark) {
                .task-card {
                    box-shadow: rgba(255, 255, 255, 0.05) 0px -23px 25px 0px inset, rgba(255, 255, 255, 0.04) 0px -36px 30px 0px inset, rgba(255, 255, 255, 0.03) 0px -79px 40px 0px inset, rgba(255, 255, 255, 0.02) 0px 2px 1px, rgba(255, 255, 255, 0.02) 0px 4px 2px, rgba(255, 255, 255, 0.02) 0px 8px 4px, rgba(255, 255, 255, 0.02) 0px 16px 8px, rgba(255, 255, 255, 0.02) 0px 32px 16px;
                }
            }
            
            .task-card:hover { transform: translateY(-5px); box-shadow: 0 10px 15px rgba(0, 0, 0, 0.1); }
            
            .task-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 8px; }
            .task-title { font-size: 1rem !important; font-weight: 600; color: var(--dark); margin-bottom: 4px; line-height: 1.4 !important; }
            .task-description { font-size: 0.8rem !important; color: var(--gray); margin-bottom: 12px; line-height: 1.4 !important; flex-grow: 1; }
            .task-description:empty { display: none !important; margin-bottom: 0 !important; }
            
            .task-actions { display: flex; gap: 8px; }
            .action-btn { background-color: var(--primary); color: white; border: none; border-radius: 50%; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: var(--transition); font-size: 0.8rem; }
            .action-btn:hover { background-color: var(--primary); transform: scale(1.1); }
            
            .action-btn.disabled {
                background-color: var(--gray-light);
                cursor: not-allowed;
                opacity: 0.6;
            }
            
            .action-btn.disabled:hover {
                transform: none;
                background-color: var(--gray-light);
            }
            
            .task-meta { display: flex; align-items: center; justify-content: space-between; font-size: 0.75rem; color: var(--gray); margin-top: auto; padding-top: 12px; }
            .repeat-badge { background-color: rgba(67, 97, 238, 0.1); color: var(--primary); padding: 2px 8px; border-radius: 20px; font-size: 0.65rem; font-weight: 600; display: flex; align-items: center; gap: 4px; }
            .priority-badge { background-color: rgba(108, 117, 125, 0.2); color: var(--gray); padding: 2px 8px; border-radius: 20px; font-size: 0.65rem; font-weight: 600; display: flex; align-items: center; gap: 4px; }
            
            .task-date-range { font-size: 0.75rem; color: var(--gray); margin-right: 8px; }
            .task-time-range { font-size: 0.75rem; color: var(--gray); font-weight: 500; }
            
            .subtask-number-badge { width: 22px; height: 22px; border-radius: 50%; background-color: var(--gray-light); color: var(--dark); display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: bold; transition: var(--transition); }
            .subtask-number-badge.completed { background-color: var(--primary); color: white; }
            .subtask-complete-btn { background: none; border: none; cursor: pointer; padding: 0; margin-right: 8px;}
            .edit-subtask-btn, .delete-subtask-btn { background: none; border: none; color: var(--primary); cursor: pointer; font-size: 0.7rem; opacity: 0.7; transition: var(--transition); padding: 2px 4px; }
            .edit-subtask-btn:hover, .delete-subtask-btn:hover { opacity: 1; transform: scale(1.1); }
            .delete-subtask-btn { color: var(--danger); }

            .subtasks-details { margin-top: 12px; border-top: 1px solid var(--gray-light); padding-top: 12px; }
            .subtasks-details summary { cursor: pointer; display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 0.85rem; color: var(--primary); padding: 4px 0; transition: var(--transition); }
            .subtasks-details summary:hover { color: var(--primary-light); }
            .details-toggle { margin-left: auto; transition: var(--transition); }
            .subtasks-details[open] .details-toggle { transform: rotate(90deg); }
            .subtasks-content { margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(0,0,0,0.05); }
            @media (prefers-color-scheme: dark) {
                .subtasks-content { border-top-color: rgba(255,255,255,0.05); }
            }
            .subtask-item { display: flex; align-items: flex-start; margin-bottom: 8px; padding: 8px; background: rgba(0,0,0,0.03); border-radius: 6px; }
            @media (prefers-color-scheme: dark) {
                .subtask-item { background: rgba(255,255,255,0.05); }
            }
            .subtask-details-container { flex: 1; margin-right: 8px;}
            .subtask-title { font-size: 0.85rem; color: var(--dark); cursor: pointer; }
            .subtask-completed { text-decoration: line-through; color: var(--gray); }
            .subtask-description { font-size: 0.75rem; color: var(--gray); margin-top: 4px; padding-left: 8px; border-left: 2px solid var(--primary-light); line-height: 1.4; }
            .subtask-actions { display: flex; align-items: center; margin-left: auto; }
            
            .progress-display-container { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
            .progress-bar-container { flex: 1; background: var(--gray-light); border-radius: 20px; height: 10px; overflow: hidden; }
            .progress-bar-fill { height: 100%; background: var(--primary); transition: width 0.3s ease; }
            .progress-circle { width: 36px; height: 36px; border-radius: 50%; background: conic-gradient(var(--primary) 0%, var(--gray-light) 0%); display: flex; align-items: center; justify-content: center; position: relative; flex-shrink: 0; }
            .progress-circle::before { content: ''; position: absolute; width: 26px; height: 26px; background-color: var(--light); border-radius: 50%; }
            .progress-text { font-size: 0.75rem; color: var(--gray); }
            
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.5); z-index: 1000; align-items: center; justify-content: center; animation: fadeIn 0.3s ease; }
            .modal-content { background-color: var(--light); border-radius: var(--border-radius); width: 90%; max-width: 500px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2); animation: scaleIn 0.3s ease; overflow: hidden; max-height: 90vh; overflow-y: auto; }
            .modal-header { padding: 16px; border-bottom: 1px solid var(--gray-light); display: flex; align-items: center; justify-content: space-between; }
            .modal-title { font-size: 1.2rem; font-weight: 600; color: var(--dark); }
            .close-modal { background: none; border: none; font-size: 1.3rem; color: var(--gray); cursor: pointer; transition: var(--transition); }
            .close-modal:hover { color: var(--danger); }
            .modal-body { padding: 16px; }
            .form-group { margin-bottom: 12px; }
            .form-label { display: block; margin-bottom: 4px; font-weight: 600; color: var(--dark); font-size: 0.9rem; }
            .form-input, .form-select, .form-textarea { width: 100%; padding: 8px; border: 1px solid var(--gray-light); border-radius: 6px; background-color: var(--light); color: var(--dark); transition: var(--transition); font-size: 0.9rem; }
            .form-input:focus, .form-select:focus, .form-textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2); }
            .form-textarea { min-height: 80px; resize: vertical; line-height: 1.4; }
            .form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
            .btn { padding: 8px 16px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; transition: var(--transition); font-size: 0.9rem; }
            .btn-primary { background-color: var(--primary); color: white; }
            .btn-primary:hover { background-color: var(--secondary); }
            .btn-secondary { background-color: var(--gray-light); color: white; }
            .btn-secondary:hover { background-color: var(--gray); }
            .time-input-group { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
            .date-input-group { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
            
            .checkbox-group { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
            .checkbox-label { font-weight: 500; color: var(--dark); }
            .form-checkbox { width: 18px; height: 18px; }
            
            /* History styles */
            .history-date-details { margin-bottom: 15px; }
            .history-date-summary { padding: 12px 16px; background-color: var(--blue-bg); border-radius: var(--border-radius); cursor: pointer; font-weight: 600; display: flex; align-items: center; gap: 10px; transition: var(--transition); border: 1px solid transparent; }
            .history-date-summary:hover { background-color: var(--blue-bg-hover); border-color: var(--primary-light); }
            .history-date-content { padding: 10px 0 0 15px; }
            .history-items-container { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; margin: 10px 0; }
            .history-card { background-color: var(--blue-bg); border-radius: var(--border-radius); padding: 16px; box-shadow: var(--shadow); transition: var(--transition); border: 1px solid rgba(0,0,0,0.05); border-left: 4px solid var(--success); }
            .history-card:hover { transform: translateY(-3px); box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15); }
            .history-card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
            .history-card-title { font-weight: 600; color: var(--dark); font-size: 0.8rem; display: flex; align-items: center; gap: 8px; flex: 1; }
            .history-card-title i { color: var(--primary); font-size: 0.9rem; }
            .history-card-time { font-size: 0.75rem; color: var(--gray); background: rgba(0,0,0,0.05); padding: 3px 8px; border-radius: 12px; white-space: nowrap; margin-left: 10px; }
            .history-card-description { font-size: 0.8rem; color: var(--gray); margin-bottom: 12px; line-height: 1.4; }
            .history-card-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
            .history-meta-item { background: rgba(0,0,0,0.05); color: var(--gray); padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 500; }
            .history-subitems { margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(0,0,0,0.1); }
            .history-stage-item { font-size: 0.8rem; color: var(--gray); margin-bottom: 8px; padding: 8px; background: rgba(0,0,0,0.03); border-radius: 6px; }
            .history-stage-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
            .history-stage-title { font-weight: 600; color: var(--dark); flex: 1; }
            .history-stage-description { font-size: 0.75rem; color: var(--gray); margin-top: 4px; padding-left: 8px; border-left: 2px solid var(--success); line-height: 1.4; }
            
            @media (prefers-color-scheme: dark) {
                .history-card { background-color: rgba(173, 216, 230, 0.08); border: 1px solid rgba(255,255,255,0.05); }
                .history-card-time, .history-meta-item { background: rgba(255,255,255,0.1); }
                .history-subitems { border-top-color: rgba(255,255,255,0.1); }
                .history-stage-item { background: rgba(255,255,255,0.05); }
            }
            
            /* Notes Styles */
            .notes-container { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
            .note-card {
                background: var(--note-bg);
                border-radius: var(--border-radius);
                padding: 0;
                box-shadow: var(--note-shadow);
                transition: var(--transition);
                border: 1px solid rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
            }
            
            .note-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15);
            }
            
            .note-details {
                width: 100%;
            }
            
            .note-summary {
                list-style: none;
                padding: 20px;
                cursor: pointer;
            }
            
            .note-summary::-webkit-details-marker {
                display: none;
            }
            
            .note-header {
                margin-bottom: 12px;
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
            }
            
            .note-title-wrapper {
                flex: 1;
            }
            
            .note-title {
                font-size: 1.1rem;
                font-weight: 700;
                color: var(--dark);
                margin-bottom: 4px;
                line-height: 1.3;
            }
            
            .note-date-badge-top {
                background: rgba(67, 97, 238, 0.1);
                color: var(--primary);
                padding: 4px 8px;
                border-radius: 12px;
                font-size: 0.7rem;
                font-weight: 500;
                white-space: nowrap;
                margin-left: 10px;
            }
            
            .note-content {
                padding: 0 20px 20px 20px;
            }
            
            .note-description {
                font-size: 0.9rem;
                color: var(--dark);
                line-height: 1.5;
                margin-bottom: 16px;
            }
            
            .note-description strong {
                font-weight: 700;
                color: var(--primary);
            }
            
            .note-description em {
                font-style: italic;
                color: var(--secondary);
            }
            
            .note-footer {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-top: auto;
                padding-top: 12px;
                border-top: 1px solid rgba(0,0,0,0.05);
            }
            
            @media (prefers-color-scheme: dark) {
                .note-footer {
                    border-top-color: rgba(255,255,255,0.05);
                }
            }
            
            .note-meta {
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .note-interval-badge {
                background: rgba(248, 150, 30, 0.1);
                color: var(--warning);
                padding: 4px 8px;
                border-radius: 12px;
                font-size: 0.7rem;
                font-weight: 500;
            }
            
            .note-actions {
                display: flex;
                align-items: center;
                gap: 6px;
            }
            
            .note-action-btn, .note-move-btn {
                background: none;
                border: none;
                color: var(--primary);
                cursor: pointer;
                font-size: 0.9rem;
                transition: var(--transition);
                opacity: 0.7;
                padding: 4px;
                border-radius: 4px;
            }
            
            .note-action-btn:hover, .note-move-btn:hover {
                opacity: 1;
                transform: scale(1.1);
                background: rgba(67, 97, 238, 0.1);
            }
            
            .note-action-btn.delete {
                color: var(--danger);
            }
            
            .note-action-btn.delete:hover {
                background: rgba(247, 37, 133, 0.1);
            }
            
            /* Settings View */
            .settings-card {
                background: var(--blue-bg);
                border-radius: var(--border-radius);
                padding: 24px;
                margin-bottom: 20px;
                box-shadow: var(--shadow);
            }
            
            .settings-title {
                font-size: 1.2rem;
                font-weight: 600;
                color: var(--dark);
                margin-bottom: 16px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .settings-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px 0;
                border-bottom: 1px solid rgba(0,0,0,0.1);
            }
            
            .settings-item:last-child {
                border-bottom: none;
            }
            
            .settings-label {
                font-weight: 500;
                color: var(--dark);
            }
            
            .toggle-switch {
                position: relative;
                display: inline-block;
                width: 50px;
                height: 24px;
            }
            
            .toggle-switch input {
                opacity: 0;
                width: 0;
                height: 0;
            }
            
            .toggle-slider {
                position: absolute;
                cursor: pointer;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: var(--gray-light);
                transition: .4s;
                border-radius: 24px;
            }
            
            .toggle-slider:before {
                position: absolute;
                content: "";
                height: 16px;
                width: 16px;
                left: 4px;
                bottom: 4px;
                background-color: white;
                transition: .4s;
                border-radius: 50%;
            }
            
            input:checked + .toggle-slider {
                background-color: var(--success);
            }
            
            input:checked + .toggle-slider:before {
                transform: translateX(26px);
            }
            
            .empty-state { text-align: center; padding: 32px 16px; color: var(--gray); }
            .empty-state i { font-size: 2.5rem; margin-bottom: 12px; opacity: 0.5; }
            
            .time-remaining-badge { background-color: rgba(67, 97, 238, 0.1); color: var(--primary); padding: 4px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: 600; }
            .time-remaining-badge.upcoming { background-color: rgba(108, 117, 125, 0.2); color: var(--gray); }
            .time-remaining-badge.starting_soon { background-color: rgba(248, 150, 30, 0.1); color: var(--warning); }
            .time-remaining-badge.active { background-color: rgba(76, 201, 240, 0.2); color: var(--success); }
            .time-remaining-badge.due { background-color: rgba(248, 150, 30, 0.1); color: var(--warning); }
            .time-remaining-badge.overdue { background-color: rgba(247, 37, 133, 0.1); color: var(--danger); }
            .time-remaining-badge.expired { background-color: rgba(108, 117, 125, 0.2); color: var(--gray); }
            
            @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
            @keyframes scaleIn { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }
            @keyframes slideIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
            
            @media (max-width: 768px) {
                .history-items-container { grid-template-columns: 1fr; }
                .notes-container { grid-template-columns: 1fr; }
                .task-description, .history-card-description { font-size: 0.75rem; }
                .task-card { min-height: 120px !important; }
            }
        </style>
    </head>
    <body>
        <div class="header">
            <button class="header-action-btn" onclick="switchView('tasks')" title="Tasks">
                <i class="fas fa-tasks"></i>
                <span>Tasks</span>
            </button>
            <button class="header-action-btn" onclick="switchView('notes')" title="Notes">
                <i class="fas fa-wand-magic-sparkles"></i>
                <span>Notes</span>
            </button>
            <button class="header-action-btn" onclick="switchView('history')" title="History">
                <i class="fas fa-history"></i>
                <span>History</span>
            </button>
            <button class="header-action-btn" onclick="switchView('settings')" title="Settings">
                <i class="fas fa-cog"></i>
                <span>Settings</span>
            </button>
        </div>

        <!-- Show FAB based on current view -->
        <div id="fabContainer">
            {% if view == 'tasks' %}
                <button class="fab fab-tasks" onclick="openAddTaskModal()" title="Add Task">
                    <i class="fas fa-plus"></i>
                </button>
            {% elif view == 'notes' %}
                <button class="fab fab-notes" onclick="openAddNoteModal()" title="Add Note">
                    <i class="fas fa-plus"></i>
                </button>
            {% endif %}
        </div>

        <div class="main-content">
            <!-- Tasks View -->
            <div class="view-content {{ 'active' if view == 'tasks' else '' }}" id="tasksView">
                <div class="content-header">
                    <h1 class="page-title">Tasks</h1>
                </div>
                
                <div class="bucket-header">
                    <h2 class="bucket-title">
                        <i class="fas fa-tasks"></i>
                        All Tasks
                        <span class="bucket-count">{{ processed_tasks|length }}</span>
                    </h2>
                </div>
                
                <div class="items-container">
                    {% if not processed_tasks %}
                    <div class="empty-state" style="grid-column: 1 / -1;">
                        <i class="fas fa-clipboard-list"></i>
                        <p>No tasks yet. Add a new one to get started!</p>
                    </div>
                    {% else %}
                        {% for task in processed_tasks %}
                        <div class="task-card {{ 'completed-repeating' if task.is_completed_repeating else '' }}">
                            <div class="task-header">
                                <div style="flex: 1;">
                                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;">
                                        <h3 class="task-title">{{ task.title }}</h3>
                                        <div class="task-actions">
                                            <button class="action-btn" onclick="openAddSubtaskModal('{{ task.id }}')" title="Add Subtask">
                                                <i class="fas fa-plus"></i>
                                            </button>
                                            <button class="action-btn" onclick="openEditTaskModal('{{ task.id }}')" title="Edit Task">
                                                <i class="fas fa-edit"></i>
                                            </button>
                                            {% if task.is_active %}
                                            <form method="POST" action="/complete_task" style="display:inline;">
                                                <input type="hidden" name="task_id" value="{{ task.id }}">
                                                <button type="submit" class="action-btn" title="Complete">
                                                    <i class="fas fa-check"></i>
                                                </button>
                                            </form>
                                            {% else %}
                                            <button class="action-btn disabled" title="Already Completed" disabled>
                                                <i class="fas fa-check"></i>
                                            </button>
                                            {% endif %}
                                            <form method="POST" action="/delete_task" style="display:inline;">
                                                <input type="hidden" name="task_id" value="{{ task.id }}">
                                                <button type="submit" class="action-btn" title="Delete" onclick="return confirm('Delete this task?')">
                                                    <i class="fas fa-trash"></i>
                                                </button>
                                            </form>
                                        </div>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <div>
                                            <span class="task-date-range">{{ task.date_range }}</span>
                                            <span class="task-time-range">{{ task.time_range }}</span>
                                        </div>
                                        <div class="time-remaining-badge {{ task.time_status.class }}">
                                            {{ task.time_status.text }}
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            {% if task.description %}
                            <p class="task-description">{{ format_text(task.description)|safe }}</p>
                            {% endif %}
                            
                            {% if task.is_completed_repeating %}
                            <div class="next-occurrence-info">
                                <i class="fas fa-calendar-alt"></i>
                                Next: Tomorrow at {{ task.start_display }}
                            </div>
                            {% endif %}
                            
                            {% if task.total_subtasks > 0 %}
                            <div class="progress-display-container">
                                <div class="progress-circle" style="background: conic-gradient(var(--primary) {{ task.progress_percentage }}%, var(--gray-light) 0%);">
                                    <span style="font-size: 0.65rem; z-index: 1;">{{ task.progress_percentage }}%</span>
                                </div>
                                <div class="progress-text" style="margin-left: 8px; flex: 1;">
                                    {{ task.completed_subtasks }} of {{ task.total_subtasks }} subtasks completed
                                </div>
                            </div>
                            {% endif %}
                            
                            {% if task.subtasks %}
                            <details class="subtasks-details">
                                <summary>
                                    <i class="fas fa-tasks"></i>
                                    Subtasks ({{ task.completed_subtasks }}/{{ task.total_subtasks }})
                                    <span class="details-toggle">▼</span>
                                </summary>
                                <div class="subtasks-content">
                                    {% for subtask in task.subtasks %}
                                    <div class="subtask-item">
                                        <form method="POST" action="/complete_subtask" style="display:inline;">
                                            <input type="hidden" name="task_id" value="{{ task.id }}">
                                            <input type="hidden" name="subtask_id" value="{{ subtask.id }}">
                                            <button type="submit" class="subtask-complete-btn" title="Toggle Complete">
                                                {% if subtask.completed %}
                                                <span class="subtask-number-badge completed">{{ subtask.priority }}</span>
                                                {% else %}
                                                <span class="subtask-number-badge">{{ subtask.priority }}</span>
                                                {% endif %}
                                            </button>
                                        </form>
                                        <details class="subtask-details-container">
                                            <summary class="subtask-title {{ 'subtask-completed' if subtask.completed else '' }}">
                                                {{ subtask.title }}
                                            </summary>
                                            {% if subtask.description %}
                                            <div class="subtask-description">{{ format_text(subtask.description)|safe }}</div>
                                            {% endif %}
                                        </details>
                                        <div class="subtask-actions">
                                            <button class="edit-subtask-btn" onclick="openEditSubtaskModal('{{ task.id }}', '{{ subtask.id }}')" title="Edit Subtask">
                                                <i class="fas fa-edit"></i>
                                            </button>
                                            <form method="POST" action="/delete_subtask" style="display:inline;">
                                                <input type="hidden" name="task_id" value="{{ task.id }}">
                                                <input type="hidden" name="subtask_id" value="{{ subtask.id }}">
                                                <button type="submit" class="delete-subtask-btn" title="Delete Subtask">
                                                    <i class="fas fa-trash"></i>
                                                </button>
                                            </form>
                                        </div>
                                    </div>
                                    {% endfor %}
                                </div>
                            </details>
                            {% endif %}
                            
                            <div class="task-meta">
                                {% if task.repeat != 'none' %}
                                <span class="repeat-badge">
                                    <i class="fas fa-repeat"></i>
                                    {% if task.repeat == 'daily' %}
                                        Daily
                                    {% elif task.repeat == 'weekly' %}
                                        Weekly on {{ task.repeat_day or 'Sunday' }}
                                    {% else %}
                                        {{ task.repeat }}
                                    {% endif %}
                                </span>
                                {% else %}
                                <span class="repeat-badge">
                                    <i class="fas fa-repeat"></i> None
                                </span>
                                {% endif %}
                                
                                <span class="priority-badge">P{{ task.priority }}</span>
                                
                                {% if task.notify_enabled %}
                                <span class="notify-badge">
                                    <i class="fas fa-bell"></i> Notify
                                </span>
                                {% endif %}
                            </div>
                        </div>
                        {% endfor %}
                    {% endif %}
                </div>
            </div>

            <!-- Notes View -->
            <div class="view-content {{ 'active' if view == 'notes' else '' }}" id="notesView">
                <div class="content-header">
                    <h1 class="page-title">Notes</h1>
                </div>
                <div class="notes-container">
                    {% if not processed_notes %}
                    <div class="empty-state" style="grid-column: 1 / -1;">
                        <i class="fas fa-wand-magic-sparkles"></i>
                        <p>No notes yet. Add one to get started!</p>
                    </div>
                    {% else %}
                        {% for note in processed_notes %}
                        <div class="note-card">
                            <details class="note-details">
                                <summary class="note-summary">
                                    <div class="note-header">
                                        <div class="note-title-wrapper">
                                            <h3 class="note-title">{{ note.title }}</h3>
                                        </div>
                                        <span class="note-date-badge-top">Created: {{ note.created_display }}</span>
                                    </div>
                                </summary>
                                <div class="note-content">
                                    {% if note.description %}
                                    <div class="note-description">{{ format_text(note.description)|safe }}</div>
                                    {% endif %}
                                    <div class="note-footer">
                                        <div class="note-meta">
                                            {% if note.notify_enabled %}
                                            <span class="note-interval-badge">
                                                <i class="fas fa-bell"></i> Every {{ note.notify_interval }}h
                                            </span>
                                            {% endif %}
                                        </div>
                                        <div class="note-actions">
                                            <form method="POST" action="/move_note" style="display:inline;">
                                                <input type="hidden" name="note_id" value="{{ note.id }}">
                                                <input type="hidden" name="direction" value="down">
                                                <button type="submit" class="note-move-btn" title="Move Down">
                                                    <i class="fas fa-arrow-down"></i>
                                                </button>
                                            </form>
                                            <form method="POST" action="/move_note" style="display:inline;">
                                                <input type="hidden" name="note_id" value="{{ note.id }}">
                                                <input type="hidden" name="direction" value="up">
                                                <button type="submit" class="note-move-btn" title="Move Up" style="margin-left: 6px;">
                                                    <i class="fas fa-arrow-up"></i>
                                                </button>
                                            </form>
                                            <button class="note-action-btn" onclick="openEditNoteModal('{{ note.id }}')" title="Edit Note">
                                                <i class="fas fa-edit"></i>
                                            </button>
                                            <form method="POST" action="/delete_note" style="display:inline;">
                                                <input type="hidden" name="note_id" value="{{ note.id }}">
                                                <button type="submit" class="note-action-btn delete" title="Delete Note">
                                                    <i class="fas fa-trash"></i>
                                                </button>
                                            </form>
                                        </div>
                                    </div>
                                </div>
                            </details>
                        </div>
                        {% endfor %}
                    {% endif %}
                </div>
            </div>

            <!-- History View -->
            <div class="view-content {{ 'active' if view == 'history' else '' }}" id="historyView">
                <div class="content-header">
                    <h1 class="page-title">History</h1>
                </div>
                
                <div id="historyContainer">
                    {% if not history_with_subtasks %}
                    <div class="empty-state">
                        <i class="fas fa-history"></i>
                        <p>No completed items yet. Complete some items to see them here!</p>
                    </div>
                    {% else %}
                        {% set grouped_history = {} %}
                        {% for item in history_with_subtasks %}
                            {% set date = item.completed_at[:10] %}
                            {% set date_display = datetime.strptime(date, '%Y-%m-%d').strftime('%B %d, %Y') %}
                            {% if date_display not in grouped_history %}
                                {% set _ = grouped_history.update({date_display: []}) %}
                            {% endif %}
                            {% set _ = grouped_history[date_display].append(item) %}
                        {% endfor %}
                        
                        {% for date_display, items in grouped_history.items()|sort(reverse=true) %}
                        <div class="history-date-group">
                            <details class="history-date-details">
                                <summary class="history-date-summary">
                                    <i class="fas fa-calendar"></i>{{ date_display }}
                                    <span class="details-toggle">▼</span>
                                </summary>
                                <div class="history-date-content">
                                    <div class="history-items-container">
                                        {% for item in items %}
                                        <div class="history-card">
                                            <div class="history-card-header">
                                                <div class="history-card-title">
                                                    <i class="fas fa-tasks"></i>
                                                    {{ item.title }}
                                                </div>
                                                <div class="history-card-time">
                                                    {{ datetime.strptime(item.completed_at, '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p') }}
                                                </div>
                                            </div>
                                            {% if item.description %}
                                            <div class="history-card-description">{{ format_text(item.description)|safe }}</div>
                                            {% endif %}
                                            <div class="history-card-meta">
                                                {% if item.bucket %}
                                                <span class="history-meta-item">Bucket: {{ item.bucket|title }}</span>
                                                {% endif %}
                                                {% if item.repeat %}
                                                <span class="history-meta-item">Repeat: {{ 'No' if item.repeat == 'none' else item.repeat|title }}</span>
                                                {% endif %}
                                                {% if item.time_range %}
                                                <span class="history-meta-item">Time: {{ item.time_range }}</span>
                                                {% endif %}
                                                {% if item.priority %}
                                                <span class="history-meta-item">Priority: P{{ item.priority }}</span>
                                                {% endif %}
                                            </div>
                                            {% if item.subtasks %}
                                            <div class="history-subitems">
                                                {% for subtask in item.subtasks %}
                                                <div class="history-stage-item">
                                                    <div class="history-stage-header">
                                                        <span class="history-stage-title">{{ subtask.title }}</span>
                                                    </div>
                                                    {% if subtask.description %}
                                                    <div class="history-stage-description">{{ format_text(subtask.description)|safe }}</div>
                                                    {% endif %}
                                                </div>
                                                {% endfor %}
                                            </div>
                                            {% endif %}
                                        </div>
                                        {% endfor %}
                                    </div>
                                </div>
                            </details>
                        </div>
                        {% endfor %}
                    {% endif %}
                </div>
            </div>
            
            <!-- Settings View -->
            <div class="view-content {{ 'active' if view == 'settings' else '' }}" id="settingsView">
                <div class="content-header">
                    <h1 class="page-title">Settings</h1>
                </div>
                
                <div class="settings-card">
                    <h2 class="settings-title">
                        <i class="fas fa-bell"></i>
                        Notification Settings
                    </h2>
                    
                    <div class="settings-item">
                        <span class="settings-label">30-Minute Task Status Reports</span>
                        <form method="POST" id="halfHourlyReportForm" action="/toggle_setting">
                            <input type="hidden" name="key" value="half_hourly_report">
                            <label class="toggle-switch">
                                <input type="checkbox" name="enabled" {{ 'checked' if settings.get('half_hourly_report') == '1' else '' }} onchange="this.form.submit()">
                                <span class="toggle-slider"></span>
                            </label>
                        </form>
                    </div>
                    
                    <p style="margin-top: 16px; color: var(--gray); font-size: 0.85rem;">
                        <i class="fas fa-info-circle"></i> 
                        30-minute reports send task status updates (completed/pending) to Telegram every 30 minutes.
                    </p>
                </div>
                
                <div class="settings-card">
                    <h2 class="settings-title">
                        <i class="fas fa-info-circle"></i>
                        System Information
                    </h2>
                    
                    <div class="settings-item">
                        <span class="settings-label">Python Version</span>
                        <span class="settings-value">{{ python_version }}</span>
                    </div>
                    
                    <div class="settings-item">
                        <span class="settings-label">Server Time (IST)</span>
                        <span class="settings-value">{{ now.strftime('%Y-%m-%d %H:%M:%S') }}</span>
                    </div>
                    
                    <div class="settings-item">
                        <span class="settings-label">Total Tasks</span>
                        <span class="settings-value">{{ all_tasks|length }}</span>
                    </div>
                    
                    <div class="settings-item">
                        <span class="settings-label">Total Notes</span>
                        <span class="settings-value">{{ notes|length }}</span>
                    </div>
                </div>
                
                <div class="settings-card">
                    <h2 class="settings-title">
                        <i class="fas fa-robot"></i>
                        Telegram Integration
                    </h2>
                    
                    <div class="settings-item">
                        <span class="settings-label">Notifications</span>
                        <span class="settings-value">✅ Active</span>
                    </div>
                    
                    <div class="settings-item">
                        <span class="settings-label">Task Reminders</span>
                        <span class="settings-value">10 messages before start</span>
                    </div>
                    
                    <div class="settings-item">
                        <span class="settings-label">Note Reminders</span>
                        <span class="settings-value">Custom intervals</span>
                    </div>
                    
                    <p style="margin-top: 16px; color: var(--gray); font-size: 0.85rem;">
                        <i class="fas fa-key"></i> 
                        Telegram User ID: {{ USER_ID }}
                    </p>
                </div>
            </div>
        </div>

        <!-- Modals -->
        <div class="modal" id="addTaskModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2 class="modal-title">Add Task</h2>
                    <button type="button" class="close-modal" onclick="closeAddTaskModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <form method="POST" action="/add_task" id="addTaskForm">
                        <div class="form-group">
                            <label class="form-label">Title</label>
                            <input type="text" class="form-input" name="title" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Description</label>
                            <textarea class="form-textarea" name="description" placeholder="Optional details"></textarea>
                            <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Priority</label>
                            <select class="form-select" name="priority">
                                {% for i in range(1, 16) %}
                                <option value="{{ i }}" {% if i==15 %}selected{% endif %}>{{ i }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="checkbox-group">
                            <input type="checkbox" class="form-checkbox" name="notify_enabled" id="notifyEnabled" checked>
                            <label class="checkbox-label" for="notifyEnabled">Telegram reminders</label>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Repeat</label>
                            <select class="form-select" name="repeat" id="repeatSelect">
                                <option value="none">None</option>
                                <option value="daily">Daily</option>
                                <option value="weekly" id="weeklyOption">Weekly on {{ now.strftime('%A') }}</option>
                            </select>
                        </div>
                        <div class="date-input-group">
                            <div class="form-group">
                                <label class="form-label">Start Date</label>
                                <input type="date" class="form-input" name="start_date" id="startDate" value="{{ now.strftime('%Y-%m-%d') }}">
                            </div>
                            <div class="form-group">
                                <label class="form-label">End Date</label>
                                <input type="date" class="form-input" name="end_date" id="endDate" value="{{ now.strftime('%Y-%m-%d') }}">
                            </div>
                        </div>
                        <div class="time-input-group">
                            <div class="form-group">
                                <label class="form-label">Start Time</label>
                                <input type="time" class="form-input" name="start_time" id="startTime" value="{{ now.strftime('%H:%M') }}">
                            </div>
                            <div class="form-group">
                                <label class="form-label">End Time</label>
                                <input type="time" class="form-input" name="end_time" id="endTime" value="{{ (now + timedelta(hours=1)).strftime('%H:%M') }}">
                            </div>
                        </div>
                        <div class="form-group" id="repeatEndDateGroup">
                            <label class="form-label">End of Repeat Date (Leave empty for infinite)</label>
                            <input type="date" class="form-input" name="repeat_end_date" id="repeatEndDate">
                        </div>
                        <div class="form-actions">
                            <button type="button" class="btn btn-secondary" onclick="closeAddTaskModal()">Cancel</button>
                            <button type="submit" class="btn btn-primary">Add Task</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>

        <div class="modal" id="addNoteModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2 class="modal-title">Add Note</h2>
                    <button type="button" class="close-modal" onclick="closeAddNoteModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <form method="POST" action="/add_note">
                        <div class="form-group">
                            <label class="form-label">Title</label>
                            <input type="text" class="form-input" name="title" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Description</label>
                            <textarea class="form-textarea" name="description" placeholder="Optional details"></textarea>
                            <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                        </div>
                        <div class="checkbox-group">
                            <input type="checkbox" class="form-checkbox" name="notify_enabled" id="noteNotifyEnabled">
                            <label class="checkbox-label" for="noteNotifyEnabled">Enable regular Telegram notifications</label>
                        </div>
                        <div class="form-group" id="noteIntervalGroup" style="display: none;">
                            <label class="form-label">Notification Interval (hours)</label>
                            <input type="number" class="form-input" name="notify_interval" min="1" max="24" value="12" placeholder="Enter interval in hours">
                        </div>
                        <div class="form-actions">
                            <button type="button" class="btn btn-secondary" onclick="closeAddNoteModal()">Cancel</button>
                            <button type="submit" class="btn btn-primary">Save Note</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
        
        <div class="modal" id="editNoteModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2 class="modal-title">Edit Note</h2>
                    <button type="button" class="close-modal" onclick="closeEditNoteModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <form method="POST" action="/update_note" id="editNoteForm">
                        <input type="hidden" name="note_id" id="editNoteId">
                        <div class="form-group">
                            <label class="form-label">Title</label>
                            <input type="text" class="form-input" name="title" id="editNoteTitle" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Description</label>
                            <textarea class="form-textarea" name="description" id="editNoteDescription"></textarea>
                            <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                        </div>
                        <div class="checkbox-group">
                            <input type="checkbox" class="form-checkbox" name="notify_enabled" id="editNoteNotifyEnabled">
                            <label class="checkbox-label" for="editNoteNotifyEnabled">Enable regular Telegram notifications</label>
                        </div>
                        <div class="form-group" id="editNoteIntervalGroup" style="display: none;">
                            <label class="form-label">Notification Interval (hours)</label>
                            <input type="number" class="form-input" name="notify_interval" id="editNoteInterval" min="1" max="24" value="12" placeholder="Enter interval in hours">
                        </div>
                        <div class="form-actions">
                            <button type="button" class="btn btn-secondary" onclick="closeEditNoteModal()">Cancel</button>
                            <button type="submit" class="btn btn-primary">Update Note</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>

        <div class="modal" id="addSubtaskModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2 class="modal-title">Add Subtask</h2>
                    <button type="button" class="close-modal" onclick="closeAddSubtaskModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <form method="POST" action="/add_subtask" id="addSubtaskForm">
                        <input type="hidden" name="task_id" id="addSubtaskTaskId">
                        <div class="form-group">
                            <label class="form-label">Subtask Title</label>
                            <input type="text" class="form-input" name="title" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Description</label>
                            <textarea class="form-textarea" name="description" placeholder="Optional details"></textarea>
                            <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                        </div>
                        <div class="form-actions">
                            <button type="button" class="btn btn-secondary" onclick="closeAddSubtaskModal()">Cancel</button>
                            <button type="submit" class="btn btn-primary">Add Subtask</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>

        <div class="modal" id="editTaskModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2 class="modal-title">Edit Task</h2>
                    <button type="button" class="close-modal" onclick="closeEditTaskModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <form method="POST" action="/update_task" id="editTaskForm">
                        <input type="hidden" name="task_id" id="editTaskId">
                        <div class="form-group">
                            <label class="form-label">Title</label>
                            <input type="text" class="form-input" name="title" id="editTaskTitle" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Description</label>
                            <textarea class="form-textarea" name="description" id="editTaskDescription"></textarea>
                            <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Priority</label>
                            <select class="form-select" name="priority" id="editTaskPriority">
                                {% for i in range(1, 16) %}
                                <option value="{{ i }}">{{ i }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="checkbox-group">
                            <input type="checkbox" class="form-checkbox" name="notify_enabled" id="editTaskNotifyEnabled">
                            <label class="checkbox-label" for="editTaskNotifyEnabled">Telegram reminders</label>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Repeat</label>
                            <select class="form-select" name="repeat" id="editTaskRepeat">
                                <option value="none">None</option>
                                <option value="daily">Daily</option>
                                <option value="weekly">Weekly</option>
                            </select>
                        </div>
                        <div class="date-input-group">
                            <div class="form-group">
                                <label class="form-label">Start Date</label>
                                <input type="date" class="form-input" name="start_date" id="editTaskStartDate">
                            </div>
                            <div class="form-group">
                                <label class="form-label">End Date</label>
                                <input type="date" class="form-input" name="end_date" id="editTaskEndDate">
                            </div>
                        </div>
                        <div class="time-input-group">
                            <div class="form-group">
                                <label class="form-label">Start Time</label>
                                <input type="time" class="form-input" name="start_time" id="editTaskStartTime">
                            </div>
                            <div class="form-group">
                                <label class="form-label">End Time</label>
                                <input type="time" class="form-input" name="end_time" id="editTaskEndTime">
                            </div>
                        </div>
                        <div class="form-group" id="editRepeatEndDateGroup">
                            <label class="form-label">End of Repeat Date (Leave empty for infinite)</label>
                            <input type="date" class="form-input" name="repeat_end_date" id="editRepeatEndDate">
                        </div>
                        <div class="form-actions">
                            <button type="button" class="btn btn-secondary" onclick="closeEditTaskModal()">Cancel</button>
                            <button type="submit" class="btn btn-primary">Update Task</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>

        <div class="modal" id="editSubtaskModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2 class="modal-title">Edit Subtask</h2>
                    <button type="button" class="close-modal" onclick="closeEditSubtaskModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <form method="POST" action="/update_subtask" id="editSubtaskForm">
                        <input type="hidden" name="task_id" id="editSubtaskTaskId">
                        <input type="hidden" name="subtask_id" id="editSubtaskId">
                        <div class="form-group">
                            <label class="form-label">Subtask Title</label>
                            <input type="text" class="form-input" name="title" id="editSubtaskTitle" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Subtask Description</label>
                            <textarea class="form-textarea" name="description" id="editSubtaskDescription"></textarea>
                            <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Priority</label>
                            <select class="form-select" name="priority" id="editSubtaskPriority">
                                {% for i in range(1, 16) %}
                                <option value="{{ i }}">{{ i }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="form-actions">
                            <button type="button" class="btn btn-secondary" onclick="closeEditSubtaskModal()">Cancel</button>
                            <button type="submit" class="btn btn-primary">Update Subtask</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>

        <script>
            function switchView(viewName) {
                const url = new URL(window.location);
                url.searchParams.set('view', viewName);
                window.history.replaceState({}, '', url);
                document.querySelectorAll('.view-content').forEach(view => view.classList.remove('active'));
                document.getElementById(viewName + 'View').classList.add('active');
                
                // Update FAB based on view
                updateFAB(viewName);
            }
            
            function updateFAB(viewName) {
                const fabContainer = document.getElementById('fabContainer');
                if (fabContainer) {
                    if (viewName === 'tasks') {
                        fabContainer.innerHTML = '<button class="fab fab-tasks" onclick="openAddTaskModal()" title="Add Task"><i class="fas fa-plus"></i></button>';
                    } else if (viewName === 'notes') {
                        fabContainer.innerHTML = '<button class="fab fab-notes" onclick="openAddNoteModal()" title="Add Note"><i class="fas fa-plus"></i></button>';
                    } else {
                        fabContainer.innerHTML = '';
                    }
                }
            }

            function openModal(modalId) { 
                document.getElementById(modalId).style.display = 'flex'; 
                document.getElementById(modalId).scrollTop = 0;
            }
            function closeModal(modalId) { document.getElementById(modalId).style.display = 'none'; }

            function openAddTaskModal() { 
                // Set default time to next hour
                const now = new Date();
                const nextHour = new Date(now.getTime() + 60 * 60 * 1000);
                
                document.getElementById('startTime').value = now.toTimeString().slice(0,5);
                document.getElementById('endTime').value = nextHour.toTimeString().slice(0,5);
                
                // Update weekly option text with current day
                const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
                const dayName = days[now.getDay()];
                const weeklyOption = document.getElementById('weeklyOption');
                if (weeklyOption) {
                    weeklyOption.textContent = `Weekly on ${dayName}`;
                }
                
                openModal('addTaskModal'); 
            }
            
            function closeAddTaskModal() { closeModal('addTaskModal'); }
            function closeEditTaskModal() { closeModal('editTaskModal'); }
            function closeEditSubtaskModal() { closeModal('editSubtaskModal'); }
            
            function openAddNoteModal() { 
                openModal('addNoteModal'); 
                // Show/hide interval input based on checkbox
                const checkbox = document.getElementById('noteNotifyEnabled');
                const intervalGroup = document.getElementById('noteIntervalGroup');
                checkbox.addEventListener('change', function() {
                    intervalGroup.style.display = this.checked ? 'block' : 'none';
                });
            }
            
            function closeAddNoteModal() { closeModal('addNoteModal'); }
            function closeEditNoteModal() { closeModal('editNoteModal'); }
            
            function openAddSubtaskModal(taskId) {
                document.getElementById('addSubtaskTaskId').value = taskId;
                openModal('addSubtaskModal');
            }
            function closeAddSubtaskModal() { closeModal('addSubtaskModal'); }

            async function openEditTaskModal(taskId) {
                try {
                    const response = await fetch(`/get_task/${taskId}`);
                    const taskData = await response.json();
                    
                    if (taskData) {
                        document.getElementById('editTaskId').value = taskId;
                        document.getElementById('editTaskTitle').value = taskData.title || '';
                        document.getElementById('editTaskDescription').value = taskData.description || '';
                        document.getElementById('editTaskPriority').value = taskData.priority || 15;
                        document.getElementById('editTaskRepeat').value = taskData.repeat || 'none';
                        document.getElementById('editTaskNotifyEnabled').checked = taskData.notify_enabled || false;
                        
                        // Set date values
                        const startDate = new Date(taskData.start_time);
                        const endDate = new Date(taskData.end_time);
                        document.getElementById('editTaskStartDate').value = startDate.toISOString().split('T')[0];
                        document.getElementById('editTaskEndDate').value = endDate.toISOString().split('T')[0];
                        
                        // Set time values
                        document.getElementById('editTaskStartTime').value = startDate.toTimeString().slice(0,5);
                        document.getElementById('editTaskEndTime').value = endDate.toTimeString().slice(0,5);
                        
                        // Set repeat end date
                        if (taskData.repeat_end_date) {
                            const repeatEndDate = new Date(taskData.repeat_end_date);
                            document.getElementById('editRepeatEndDate').value = repeatEndDate.toISOString().split('T')[0];
                        } else {
                            document.getElementById('editRepeatEndDate').value = '';
                        }
                        
                        // Show/hide repeat end date
                        const repeatSelect = document.getElementById('editTaskRepeat');
                        const repeatEndDateGroup = document.getElementById('editRepeatEndDateGroup');
                        if (repeatSelect.value === 'none') {
                            repeatEndDateGroup.style.display = 'none';
                        } else {
                            repeatEndDateGroup.style.display = 'block';
                        }
                        
                        openModal('editTaskModal');
                    }
                } catch (error) {
                    console.error('Error loading task:', error);
                    alert('Error loading task data');
                }
            }
            
            async function openEditNoteModal(noteId) {
                try {
                    const response = await fetch(`/get_note/${noteId}`);
                    const noteData = await response.json();
                    
                    if (noteData) {
                        document.getElementById('editNoteId').value = noteId;
                        document.getElementById('editNoteTitle').value = noteData.title || '';
                        document.getElementById('editNoteDescription').value = noteData.description || '';
                        document.getElementById('editNoteNotifyEnabled').checked = noteData.notify_enabled || false;
                        document.getElementById('editNoteInterval').value = noteData.notify_interval || 12;
                        
                        const intervalGroup = document.getElementById('editNoteIntervalGroup');
                        intervalGroup.style.display = noteData.notify_enabled ? 'block' : 'none';
                        
                        openModal('editNoteModal');
                        
                        // Add change event for checkbox
                        document.getElementById('editNoteNotifyEnabled').addEventListener('change', function() {
                            intervalGroup.style.display = this.checked ? 'block' : 'none';
                        });
                    }
                } catch (error) {
                    console.error('Error loading note:', error);
                    alert('Error loading note data');
                }
            }

            async function openEditSubtaskModal(taskId, subtaskId) {
                try {
                    const response = await fetch(`/get_subtask/${taskId}/${subtaskId}`);
                    const subtaskData = await response.json();
                    
                    if (subtaskData) {
                        document.getElementById('editSubtaskTaskId').value = taskId;
                        document.getElementById('editSubtaskId').value = subtaskId;
                        document.getElementById('editSubtaskTitle').value = subtaskData.title || '';
                        document.getElementById('editSubtaskDescription').value = subtaskData.description || '';
                        document.getElementById('editSubtaskPriority').value = subtaskData.priority || 15;
                        openModal('editSubtaskModal');
                    }
                } catch (error) {
                    console.error('Error loading subtask:', error);
                    alert('Error loading subtask data');
                }
            }

            document.addEventListener('DOMContentLoaded', () => {
                const urlParams = new URLSearchParams(window.location.search);
                const viewParam = urlParams.get('view');
                if (viewParam) {
                    switchView(viewParam);
                } else {
                    // Initialize FAB for current view
                    updateFAB('tasks');
                }
                
                // Date validation for add task form
                const startDateInput = document.getElementById('startDate');
                const endDateInput = document.getElementById('endDate');
                const startTimeInput = document.getElementById('startTime');
                const endTimeInput = document.getElementById('endTime');
                const repeatSelect = document.getElementById('repeatSelect');
                const repeatEndDateGroup = document.getElementById('repeatEndDateGroup');
                
                if (startDateInput && endDateInput) {
                    startDateInput.addEventListener('change', function() {
                        const startDate = new Date(this.value);
                        const endDate = new Date(endDateInput.value);
                        const maxEndDate = new Date(startDate);
                        maxEndDate.setDate(maxEndDate.getDate() + 1);
                        
                        if (endDate > maxEndDate) {
                            endDateInput.value = maxEndDate.toISOString().split('T')[0];
                        }
                        
                        if (endDate < startDate) {
                            endDateInput.value = this.value;
                        }
                    });
                    
                    endDateInput.addEventListener('change', function() {
                        const startDate = new Date(startDateInput.value);
                        const endDate = new Date(this.value);
                        const maxEndDate = new Date(startDate);
                        maxEndDate.setDate(maxEndDate.getDate() + 1);
                        
                        if (endDate > maxEndDate) {
                            this.value = maxEndDate.toISOString().split('T')[0];
                        }
                        
                        if (endDate < startDate) {
                            this.value = startDateInput.value;
                        }
                    });
                }
                
                // Time validation
                if (startTimeInput && endTimeInput) {
                    startTimeInput.addEventListener('change', function() {
                        const startTime = this.value;
                        const endTime = endTimeInput.value;
                        
                        if (startDateInput.value === endDateInput.value && startTime >= endTime) {
                            const start = new Date(`2000-01-01T${startTime}`);
                            start.setHours(start.getHours() + 1);
                            endTimeInput.value = start.toTimeString().slice(0,5);
                        }
                    });
                    
                    endTimeInput.addEventListener('change', function() {
                        const startTime = startTimeInput.value;
                        const endTime = this.value;
                        
                        if (startDateInput.value === endDateInput.value && endTime <= startTime) {
                            const end = new Date(`2000-01-01T${endTime}`);
                            if (end.getHours() === 0) {
                                startTimeInput.value = '23:00';
                            } else {
                                const start = new Date(`2000-01-01T${endTime}`);
                                start.setHours(start.getHours() - 1);
                                startTimeInput.value = start.toTimeString().slice(0,5);
                            }
                        }
                    });
                }
                
                // Show/hide repeat end date based on repeat selection
                if (repeatSelect && repeatEndDateGroup) {
                    repeatSelect.addEventListener('change', function() {
                        if (this.value === 'none') {
                            repeatEndDateGroup.style.display = 'none';
                        } else {
                            repeatEndDateGroup.style.display = 'block';
                        }
                    });
                    
                    // Initial state
                    if (repeatSelect.value === 'none') {
                        repeatEndDateGroup.style.display = 'none';
                    }
                }
                
                // Handle note notification checkbox
                const noteNotifyCheckbox = document.getElementById('noteNotifyEnabled');
                const noteIntervalGroup = document.getElementById('noteIntervalGroup');
                
                if (noteNotifyCheckbox && noteIntervalGroup) {
                    noteNotifyCheckbox.addEventListener('change', function() {
                        noteIntervalGroup.style.display = this.checked ? 'block' : 'none';
                    });
                }
            });
            
            // Update time badges every minute
            function updateTimeBadges() {
                const now = new Date();
                const currentMinutes = now.getHours() * 60 + now.minutes;
                
                document.querySelectorAll('.time-remaining-badge').forEach(badge => {
                    // This is a simplified version - you would need to store
                    // the actual start/end times in data attributes for accurate calculation
                    badge.textContent = badge.className.includes('active') ? 'Active' : 
                                      badge.className.includes('upcoming') ? 'Upcoming' :
                                      badge.className.includes('starting_soon') ? 'Starting Soon' :
                                      badge.className.includes('due') ? 'Due' :
                                      badge.className.includes('overdue') ? 'Overdue' : 'Completed';
                });
            }
            
            // Update every minute
            setInterval(updateTimeBadges, 60000);
        </script>
    </body>
    </html>
    ''',
    tasks=processed_tasks,
    history_with_subtasks=history_with_subtasks,
    processed_notes=processed_notes,
    settings=settings,
    view=view,
    datetime=datetime,
    now=now,
    USER_ID=USER_ID,
    completed_today=completed_today,
    pending_today=pending_today,
    all_tasks=all_tasks,
    notes=notes,
    format_text=format_text,
    python_version='3.x',
    timedelta=timedelta)

# ============= ACTION ROUTES =============
@app.route('/add_task', methods=['POST'])
def add_task():
    """Add a new task"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    priority = int(request.form.get('priority', 15))
    notify_enabled = 1 if request.form.get('notify_enabled') == 'on' else 0
    repeat = request.form.get('repeat', 'none')
    
    # For weekly repeat, get the day from the current date
    repeat_day = None
    if repeat == 'weekly':
        now = get_ist_time()
        repeat_day = now.strftime('%A')  # Gets day name like "Monday"
    
    repeat_end_date = request.form.get('repeat_end_date')
    
    start_date = request.form.get('start_date')
    start_time = request.form.get('start_time')
    end_date = request.form.get('end_date')
    end_time = request.form.get('end_time')
    
    if not title or not start_date or not start_time:
        return redirect(url_for('index', view='tasks'))
    
    # Create datetime in IST
    start_dt = parse_ist_time(start_time, start_date)
    end_dt = parse_ist_time(end_time, end_date)
    
    start_datetime = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_datetime = end_dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Load existing tasks
    tasks = load_tasks()
    
    # Create new task
    new_task = {
        'id': get_next_task_id(),
        'title': title,
        'description': description,
        'start_time': start_datetime,
        'end_time': end_datetime,
        'notify_enabled': notify_enabled,
        'priority': priority,
        'repeat': repeat,
        'repeat_day': repeat_day,
        'repeat_end_date': repeat_end_date,
        'next_occurrence': start_datetime if repeat != 'none' else None,
        'completed': 0,
        'subtasks': [],
        'last_notified_minute': -1,
        'bucket': 'today',
        'created_at': get_ist_time().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    tasks.append(new_task)
    save_tasks(tasks)
    
    # Send notification if enabled and starting soon
    if notify_enabled:
        now = get_ist_time()
        minutes_until = int((start_dt - now).total_seconds() / 60)
        
        if 1 <= minutes_until <= 10:
            message = "━━━━━━━━━━━━━━━━━━━━\n"
            message += "✅ <b>Task Added</b>\n"
            message += "━━━━━━━━━━━━━━━━━━━━\n\n"
            message += f"📝 <b>{title}</b>\n"
            message += f"🕐 Starts in {minutes_until} minute"
            if minutes_until > 1:
                message += "s"
            message += f"\n📅 {start_dt.strftime('%I:%M %p')} IST"
            send_telegram_message(message)
    
    return redirect(url_for('index', view='tasks'))

@app.route('/add_subtask', methods=['POST'])
def add_subtask():
    """Add a subtask"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = int(request.form.get('task_id'))
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    
    if task_id and title:
        tasks = load_tasks()
        
        for task in tasks:
            if task.get('id') == task_id:
                subtasks = task.get('subtasks', [])
                
                # Get current max priority for this task's subtasks
                priority = 1
                if subtasks:
                    max_priority = max(st.get('priority', 0) for st in subtasks)
                    priority = max_priority + 1
                
                new_subtask = {
                    'id': len(subtasks) + 1,
                    'title': title,
                    'description': description,
                    'priority': priority,
                    'completed': 0,
                    'created_at': get_ist_time().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                subtasks.append(new_subtask)
                task['subtasks'] = subtasks
                save_tasks(tasks)
                break
    
    return redirect(url_for('index', view='tasks'))

@app.route('/complete_task', methods=['POST'])
def complete_task():
    """Mark task as completed"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = int(request.form.get('task_id'))
    
    if task_id:
        tasks = load_tasks()
        
        for task in tasks:
            if task.get('id') == task_id and not task.get('completed', 0):
                # Mark task as completed
                task['completed'] = 1
                save_tasks(tasks)
                
                # Get task time range for history
                start_dt = datetime.strptime(task.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
                start_dt = IST.localize(start_dt)
                end_dt = datetime.strptime(task.get('end_time', ''), '%Y-%m-%d %H:%M:%S')
                end_dt = IST.localize(end_dt)
                time_range = f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}"
                
                # Load history
                history = load_history()
                
                # Add to history
                new_history_item = {
                    'id': get_next_history_id(),
                    'task_id': task_id,
                    'title': task.get('title', ''),
                    'description': task.get('description', ''),
                    'type': 'task',
                    'bucket': task.get('bucket', 'today'),
                    'repeat': task.get('repeat', 'none'),
                    'time_range': time_range,
                    'priority': task.get('priority', 15),
                    'completed_at': get_ist_time().strftime('%Y-%m-%d %H:%M:%S'),
                    'subtasks': [st for st in task.get('subtasks', []) if st.get('completed', 0)]
                }
                
                history.append(new_history_item)
                save_history(history)
                
                # Send notification
                now = get_ist_time()
                message = "━━━━━━━━━━━━━━━━━━━━\n"
                message += f"🎉 <b>Task Completed!</b>\n"
                message += "━━━━━━━━━━━━━━━━━━━━\n\n"
                message += f"✅ <b>{task.get('title', '')}</b>\n"
                message += f"⏰ {now.strftime('%I:%M %p')} IST\n\n"
                message += "<i>Great job! Keep it up! 🚀</i>"
                send_telegram_message(message)
                break
    
    return redirect(url_for('index', view='tasks'))

@app.route('/complete_subtask', methods=['POST'])
def complete_subtask():
    """Toggle subtask completion"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = int(request.form.get('task_id'))
    subtask_id = int(request.form.get('subtask_id'))
    
    if task_id and subtask_id:
        tasks = load_tasks()
        
        for task in tasks:
            if task.get('id') == task_id:
                subtasks = task.get('subtasks', [])
                for subtask in subtasks:
                    if subtask.get('id') == subtask_id:
                        # Toggle completion
                        current_status = subtask.get('completed', 0)
                        subtask['completed'] = 0 if current_status else 1
                        save_tasks(tasks)
                        
                        # Send notification if completed
                        if subtask['completed'] == 1:
                            message = "━━━━━━━━━━━━━━━━━━━━\n"
                            message += f"✅ <b>Subtask Completed</b>\n"
                            message += "━━━━━━━━━━━━━━━━━━━━\n\n"
                            message += f"📝 <b>{subtask.get('title', '')}</b>\n"
                            message += f"📋 <i>Parent Task:</i> {task.get('title', '')}\n"
                            message += f"⏰ Time: {get_ist_time().strftime('%I:%M %p')} IST\n\n"
                            message += "<i>One step closer! 👏</i>"
                            send_telegram_message(message)
                        break
                break
    
    return redirect(url_for('index', view='tasks'))

@app.route('/delete_task', methods=['POST'])
def delete_task():
    """Delete a task"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = int(request.form.get('task_id'))
    
    if task_id:
        tasks = load_tasks()
        tasks = [task for task in tasks if task.get('id') != task_id]
        save_tasks(tasks)
    
    return redirect(url_for('index', view='tasks'))

@app.route('/delete_subtask', methods=['POST'])
def delete_subtask():
    """Delete a subtask"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = int(request.form.get('task_id'))
    subtask_id = int(request.form.get('subtask_id'))
    
    if task_id and subtask_id:
        tasks = load_tasks()
        
        for task in tasks:
            if task.get('id') == task_id:
                subtasks = task.get('subtasks', [])
                task['subtasks'] = [st for st in subtasks if st.get('id') != subtask_id]
                save_tasks(tasks)
                break
    
    return redirect(url_for('index', view='tasks'))

@app.route('/add_note', methods=['POST'])
def add_note():
    """Add a new note"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    notify_enabled = 1 if request.form.get('notify_enabled') == 'on' else 0
    notify_interval = int(request.form.get('notify_interval', 12))
    
    if title:
        notes = load_notes()
        
        # Get max priority
        priority = 1
        if notes:
            max_priority = max(note.get('priority', 0) for note in notes)
            priority = max_priority + 1
        
        new_note = {
            'id': get_next_note_id(),
            'title': title,
            'description': description,
            'priority': priority,
            'notify_enabled': notify_enabled,
            'notify_interval': notify_interval,
            'last_notified': None,
            'created_at': get_ist_time().strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': get_ist_time().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        notes.append(new_note)
        save_notes(notes)
        
        # Send notification if enabled
        if notify_enabled and notify_interval > 0:
            message = "━━━━━━━━━━━━━━━━━━━━\n"
            message += f"📝 <b>New Note Added</b>\n"
            message += "━━━━━━━━━━━━━━━━━━━━\n\n"
            message += f"📌 <b>{title}</b>\n"
            message += f"🔄 Interval: Every {notify_interval} hours\n"
            message += f"🔔 You'll receive regular reminders"
            send_telegram_message(message)
    
    return redirect(url_for('index', view='notes'))

@app.route('/update_note', methods=['POST'])
def update_note():
    """Update a note"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    note_id = int(request.form.get('note_id'))
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    notify_enabled = 1 if request.form.get('notify_enabled') == 'on' else 0
    notify_interval = int(request.form.get('notify_interval', 12))
    
    if note_id and title:
        notes = load_notes()
        
        for note in notes:
            if note.get('id') == note_id:
                note['title'] = title
                note['description'] = description
                note['notify_enabled'] = notify_enabled
                note['notify_interval'] = notify_interval
                note['updated_at'] = get_ist_time().strftime('%Y-%m-%d %H:%M:%S')
                save_notes(notes)
                break
    
    return redirect(url_for('index', view='notes'))

@app.route('/delete_note', methods=['POST'])
def delete_note():
    """Delete a note"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    note_id = int(request.form.get('note_id'))
    
    if note_id:
        notes = load_notes()
        notes = [note for note in notes if note.get('id') != note_id]
        save_notes(notes)
    
    return redirect(url_for('index', view='notes'))

@app.route('/move_note', methods=['POST'])
def move_note():
    """Move note up or down"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    note_id = int(request.form.get('note_id'))
    direction = request.form.get('direction')
    
    if note_id and direction:
        notes = load_notes()
        
        # Find the note
        note_index = -1
        for i, note in enumerate(notes):
            if note.get('id') == note_id:
                note_index = i
                break
        
        if note_index >= 0:
            current_note = notes[note_index]
            current_priority = current_note.get('priority', 1)
            
            if direction == 'up' and note_index > 0:
                # Swap with note above
                note_above = notes[note_index - 1]
                note_above_priority = note_above.get('priority', 1)
                
                current_note['priority'] = note_above_priority
                note_above['priority'] = current_priority
                
                # Swap positions in list
                notes[note_index], notes[note_index - 1] = notes[note_index - 1], notes[note_index]
            
            elif direction == 'down' and note_index < len(notes) - 1:
                # Swap with note below
                note_below = notes[note_index + 1]
                note_below_priority = note_below.get('priority', 1)
                
                current_note['priority'] = note_below_priority
                note_below['priority'] = current_priority
                
                # Swap positions in list
                notes[note_index], notes[note_index + 1] = notes[note_index + 1], notes[note_index]
            
            save_notes(notes)
    
    return redirect(url_for('index', view='notes'))

@app.route('/update_task', methods=['POST'])
def update_task():
    """Update a task"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = int(request.form.get('task_id'))
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    priority = int(request.form.get('priority', 15))
    notify_enabled = 1 if request.form.get('notify_enabled') == 'on' else 0
    repeat = request.form.get('repeat', 'none')
    repeat_day = request.form.get('repeat_day')
    repeat_end_date = request.form.get('repeat_end_date')
    
    start_date = request.form.get('start_date')
    start_time = request.form.get('start_time')
    end_date = request.form.get('end_date')
    end_time = request.form.get('end_time')
    
    if task_id and title and start_date and start_time:
        # Create datetime in IST
        start_dt = parse_ist_time(start_time, start_date)
        end_dt = parse_ist_time(end_time, end_date)
        
        start_datetime = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_datetime = end_dt.strftime('%Y-%m-%d %H:%M:%S')
        
        tasks = load_tasks()
        
        for task in tasks:
            if task.get('id') == task_id:
                task['title'] = title
                task['description'] = description
                task['start_time'] = start_datetime
                task['end_time'] = end_datetime
                task['notify_enabled'] = notify_enabled
                task['priority'] = priority
                task['repeat'] = repeat
                task['repeat_day'] = repeat_day
                task['repeat_end_date'] = repeat_end_date
                task['next_occurrence'] = start_datetime if repeat != 'none' else None
                save_tasks(tasks)
                break
    
    return redirect(url_for('index', view='tasks'))

@app.route('/update_subtask', methods=['POST'])
def update_subtask():
    """Update a subtask"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = int(request.form.get('task_id'))
    subtask_id = int(request.form.get('subtask_id'))
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    priority = int(request.form.get('priority', 15))
    
    if subtask_id and title:
        tasks = load_tasks()
        
        for task in tasks:
            if task.get('id') == task_id:
                subtasks = task.get('subtasks', [])
                for subtask in subtasks:
                    if subtask.get('id') == subtask_id:
                        subtask['title'] = title
                        subtask['description'] = description
                        subtask['priority'] = priority
                        save_tasks(tasks)
                        break
                break
    
    return redirect(url_for('index', view='tasks'))

@app.route('/toggle_setting', methods=['POST'])
def toggle_setting():
    """Toggle a setting"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    key = request.form.get('key')
    enabled = request.form.get('enabled')
    
    if key and enabled is not None:
        settings = load_settings()
        settings[key] = '1' if enabled == 'on' else '0'
        save_settings(settings)
        
        # Send confirmation
        if key == 'half_hourly_report':
            if settings[key] == '1':
                message = "━━━━━━━━━━━━━━━━━━━━\n"
                message += "📊 <b>30-Minute Reports Enabled</b>\n"
                message += "━━━━━━━━━━━━━━━━━━━━\n\n"
                message += "You'll receive task status reports every 30 minutes"
            else:
                message = "━━━━━━━━━━━━━━━━━━━━\n"
                message += "📊 <b>30-Minute Reports Disabled</b>\n"
                message += "━━━━━━━━━━━━━━━━━━━━\n\n"
                message += "30-minute task reports have been turned off"
            send_telegram_message(message)
    
    return redirect(url_for('index', view='settings'))

# ============= API ENDPOINTS =============
@app.route('/get_task/<int:task_id>')
def get_task_api(task_id):
    """Get task data for editing"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    tasks = load_tasks()
    for task in tasks:
        if task.get('id') == task_id:
            return jsonify(task)
    return jsonify({'error': 'Task not found'}), 404

@app.route('/get_note/<int:note_id>')
def get_note_api(note_id):
    """Get note data for editing"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    notes = load_notes()
    for note in notes:
        if note.get('id') == note_id:
            return jsonify(note)
    return jsonify({'error': 'Note not found'}), 404

@app.route('/get_subtask/<int:task_id>/<int:subtask_id>')
def get_subtask_api(task_id, subtask_id):
    """Get subtask data for editing"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    tasks = load_tasks()
    for task in tasks:
        if task.get('id') == task_id:
            subtasks = task.get('subtasks', [])
            for subtask in subtasks:
                if subtask.get('id') == subtask_id:
                    return jsonify(subtask)
            break
    
    return jsonify({'error': 'Subtask not found'}), 404

# ============= START APPLICATION =============
def start_bot_polling():
    """Start Telegram bot polling in background"""
    print("🤖 Starting Telegram bot polling...")
    try:
        bot.polling(none_stop=True, interval=1, timeout=30)
    except Exception as e:
        print(f"❌ Bot polling error: {e}")
        time.sleep(5)
        start_bot_polling()

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Task Tracker Starting...")
    now = get_ist_time()
    print(f"📅 IST Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🤖 Telegram User ID: {USER_ID}")
    print(f"🔔 Notifications: 1 per minute for 10 minutes before task start")
    print(f"📊 30-Minute Reports: Enabled")
    print(f"💾 Storage: GitHub Repository")
    print("=" * 60)
    
    # Start Telegram bot in background thread
    bot_thread = threading.Thread(target=start_bot_polling, daemon=True)
    bot_thread.start()
    
    # Start Flask app
    port = int(os.getenv('PORT', 8000))
    print(f"🌐 Web server: http://0.0.0.0:{port}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
