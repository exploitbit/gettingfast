
"""
Enhanced Task Tracker with Telegram Bot - IST Timezone
Beautiful UI with enhanced notifications
"""

import os
import sqlite3
import threading
import json
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, Response, render_template_string, jsonify, session, redirect, url_for
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import time
import secrets

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"
SECRET_KEY = secrets.token_hex(32)

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')

# Initialize Flask and Telegram bot
app = Flask(__name__)
app.secret_key = SECRET_KEY
bot = telebot.TeleBot(BOT_TOKEN)

# ============= DATABASE SETUP =============
def init_db():
    """Initialize SQLite database with all required tables"""
    conn = sqlite3.connect('tasks.db')
    c = conn.cursor()
    
    # Tasks table
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            start_time DATETIME NOT NULL,
            end_time DATETIME NOT NULL,
            completed INTEGER DEFAULT 0,
            notify_enabled INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_notified_minute INTEGER DEFAULT -1,
            priority INTEGER DEFAULT 15,
            repeat TEXT DEFAULT 'none',
            repeat_day TEXT DEFAULT NULL,
            repeat_end_date DATETIME DEFAULT NULL,
            next_occurrence DATETIME DEFAULT NULL,
            bucket TEXT DEFAULT 'today'
        )
    ''')
    
    # Subtasks table
    c.execute('''
        CREATE TABLE IF NOT EXISTS subtasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            completed INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 15,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
        )
    ''')
    
    # History table
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            title TEXT,
            description TEXT,
            type TEXT DEFAULT 'task',
            bucket TEXT DEFAULT 'today',
            repeat TEXT DEFAULT 'none',
            completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            time_range TEXT,
            priority INTEGER DEFAULT 15,
            FOREIGN KEY (task_id) REFERENCES tasks (id)
        )
    ''')
    
    # History subtasks table
    c.execute('''
        CREATE TABLE IF NOT EXISTS history_subtasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            history_id INTEGER,
            title TEXT,
            description TEXT,
            priority INTEGER DEFAULT 15,
            FOREIGN KEY (history_id) REFERENCES history (id) ON DELETE CASCADE
        )
    ''')
    
    # Notes table
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            notify_enabled INTEGER DEFAULT 0,
            notify_interval INTEGER DEFAULT 0,
            last_notified DATETIME DEFAULT NULL
        )
    ''')
    
    # Settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Insert default settings
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('hourly_report', '1')")
    
    # Notification log table
    c.execute('''
        CREATE TABLE IF NOT EXISTS notification_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            success INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ============= DATABASE HELPER FUNCTIONS =============
def get_db():
    """Get database connection"""
    conn = sqlite3.connect('tasks.db')
    conn.row_factory = sqlite3.Row
    return conn

def db_query(query, params=(), fetch_one=False, fetch_all=False):
    """Execute database query"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    
    if query.strip().upper().startswith('SELECT'):
        if fetch_one:
            result = cursor.fetchone()
        elif fetch_all:
            result = cursor.fetchall()
        else:
            result = cursor.fetchall()
    else:
        conn.commit()
        result = cursor.lastrowid
    
    conn.close()
    return result

def row_to_dict(row):
    """Convert sqlite3.Row to dictionary"""
    if row is None:
        return None
    return dict(row)

# ============= TIME FUNCTIONS =============
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

# ============= TELEGRAM FUNCTIONS =============
def send_telegram_message(text, chat_id=USER_ID):
    """Send beautiful formatted message to Telegram"""
    try:
        bot.send_message(chat_id, text, parse_mode='HTML')
        log_notification(text, True)
        print(f"📨 Telegram: {text[:100]}...")
        return True
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        log_notification(f"Error: {str(e)}", False)
        return False

def send_task_added_notification(task_title, start_time, end_time, minutes_until):
    """Send beautiful task added notification"""
    emoji = "🚀" if minutes_until > 60 else "⏰" if minutes_until > 30 else "⚡"
    
    message = f"{emoji} <b>NEW TASK ADDED</b> {emoji}\n"
    message += "━" * 30 + "\n"
    message += f"<blockquote>📝 <b>{task_title}</b></blockquote>\n"
    message += f"📅 <i>Today</i>\n"
    message += f"🕐 <code>{start_time} - {end_time}</code> IST\n"
    
    if minutes_until > 0:
        if minutes_until > 60:
            hours = minutes_until // 60
            mins = minutes_until % 60
            time_text = f"{hours}h {mins}m"
        else:
            time_text = f"{minutes_until}m"
        
        message += f"⏳ Starts in <b>{time_text}</b>\n"
    
    message += f"🔔 <spoiler>Notifications active for 10 minutes before start</spoiler>\n"
    message += "━" * 30 + "\n"
    message += f"<i>📱 Use the web app to manage tasks</i>\n"
    
    return send_telegram_message(message)

def send_task_completed_notification(task_title, subtasks_completed=0, total_subtasks=0):
    """Send beautiful task completed notification"""
    emoji = "🎉" if subtasks_completed == total_subtasks else "✅"
    
    message = f"{emoji} <b>TASK COMPLETED!</b> {emoji}\n"
    message += "━" * 30 + "\n"
    message += f"<blockquote>🎯 <b>{task_title}</b></blockquote>\n"
    
    if total_subtasks > 0:
        progress = f"{subtasks_completed}/{total_subtasks}"
        message += f"📊 Subtasks: <b>{progress}</b> completed\n"
    
    message += f"🕐 Completed at: <code>{get_ist_time().strftime('%I:%M %p')}</code> IST\n"
    message += "━" * 30 + "\n"
    message += f"<i>✨ Great work! Keep it up!</i>\n"
    
    return send_telegram_message(message)

def send_subtask_completed_notification(subtask_title, task_title):
    """Send beautiful subtask completed notification"""
    message = f"✅ <b>SUBTASK COMPLETED</b>\n"
    message += "━" * 20 + "\n"
    message += f"📋 <b>{subtask_title}</b>\n"
    message += f"📝 Parent: <i>{task_title}</i>\n"
    message += f"🕐 Time: <code>{get_ist_time().strftime('%I:%M %p')}</code>\n"
    message += "━" * 20 + "\n"
    message += f"<i>🔥 One step closer to completing the task!</i>\n"
    
    return send_telegram_message(message)

def send_note_added_notification(note_title, interval_hours):
    """Send beautiful note added notification"""
    message = f"📝 <b>NEW NOTE ADDED</b>\n"
    message += "━" * 30 + "\n"
    message += f"<blockquote>💡 <b>{note_title}</b></blockquote>\n"
    
    if interval_hours > 0:
        message += f"🔄 Reminders: Every <b>{interval_hours}h</b>\n"
        message += f"🔔 <spoiler>You'll receive regular reminders</spoiler>\n"
    else:
        message += f"🔕 <i>No reminders set</i>\n"
    
    message += f"📅 Created: <code>{get_ist_time().strftime('%I:%M %p')}</code> IST\n"
    message += "━" * 30 + "\n"
    message += f"<i>📱 Check web app for details</i>\n"
    
    return send_telegram_message(message)

def send_test_notification():
    """Send beautiful test notification"""
    now = get_ist_time()
    
    message = f"🔔 <b>TEST NOTIFICATION</b> 🔔\n"
    message += "━" * 35 + "\n"
    message += f"✅ <b>System Status: OPERATIONAL</b>\n"
    message += f"📡 <i>All systems are working perfectly!</i>\n\n"
    message += f"🕐 Time: <code>{now.strftime('%I:%M:%S %p')}</code>\n"
    message += f"📅 Date: <code>{now.strftime('%B %d, %Y')}</code>\n"
    message += f"🌐 Timezone: <code>Asia/Kolkata (IST)</code>\n"
    message += "━" * 35 + "\n"
    message += f"<i>✨ Your task tracker is ready to use!</i>\n"
    
    return send_telegram_message(message)

def log_notification(message, success):
    """Log notification to database"""
    db_query(
        "INSERT INTO notification_log (message, success) VALUES (?, ?)",
        (message[:500], 1 if success else 0)
    )

# ============= NOTIFICATION SYSTEM =============
def check_and_send_notifications():
    """Check and send notifications for tasks starting in 10 minutes"""
    try:
        now = get_ist_time()
        print(f"⏰ Notification check at {now.strftime('%H:%M:%S')} IST")
        
        # Get active tasks with notifications enabled
        tasks = db_query('''
            SELECT * FROM tasks 
            WHERE completed = 0 
            AND notify_enabled = 1
            AND datetime(start_time) > datetime('now', '-1 hour')
            ORDER BY start_time
        ''', fetch_all=True)
        
        print(f"📋 Found {len(tasks)} active tasks")
        
        for task_row in tasks:
            try:
                task = row_to_dict(task_row)
                if not task:
                    continue
                    
                task_id = task['id']
                task_title = task['title']
                start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
                start_time = IST.localize(start_time)
                
                # Calculate minutes until task starts
                minutes_until_start = int((start_time - now).total_seconds() / 60)
                
                print(f"   Task '{task_title}': Starts at {start_time.strftime('%H:%M')} IST, {minutes_until_start} minutes from now")
                
                # If task starts in 1-10 minutes, send notification
                if 1 <= minutes_until_start <= 10:
                    last_notified = task.get('last_notified_minute', -1)
                    
                    # Only send if we haven't notified for this specific minute
                    if last_notified != minutes_until_start:
                        # Create beautiful notification
                        emoji = "⚡" if minutes_until_start <= 3 else "⏰" if minutes_until_start <= 7 else "🔔"
                        
                        message = f"{emoji} <b>TASK REMINDER</b> {emoji}\n"
                        message += "━" * 30 + "\n"
                        message += f"<blockquote>📝 <b>{task_title}</b></blockquote>\n"
                        
                        if minutes_until_start == 1:
                            message += f"🕐 Starts in <b>1 minute</b> ⚡\n"
                        else:
                            message += f"🕐 Starts in <b>{minutes_until_start} minutes</b>\n"
                        
                        message += f"📅 {start_time.strftime('%I:%M %p')} IST\n"
                        message += "━" * 30 + "\n"
                        message += f"<i>🎯 Get ready! Time to focus!</i>\n"
                        
                        if send_telegram_message(message):
                            db_query('''
                                UPDATE tasks 
                                SET last_notified_minute = ? 
                                WHERE id = ?
                            ''', (minutes_until_start, task_id))
                            print(f"   ✅ Sent notification: {minutes_until_start} minutes before")
                
                # Reset notification counter if task has passed
                elif minutes_until_start <= 0 and task.get('last_notified_minute', -1) != 0:
                    db_query('''
                        UPDATE tasks 
                        SET last_notified_minute = 0 
                        WHERE id = ?
                    ''', (task_id,))
                    print(f"   🔄 Reset notifications for task {task_id}")
                    
            except Exception as e:
                print(f"   ❌ Error with task: {e}")
        
    except Exception as e:
        print(f"❌ Notification system error: {e}")
        import traceback
        traceback.print_exc()

def send_hourly_report():
    """Send beautiful hourly task status report"""
    try:
        now = get_ist_time()
        today = now.strftime('%Y-%m-%d')
        
        # Get today's tasks
        tasks = db_query('''
            SELECT * FROM tasks 
            WHERE date(start_time) = ?
            ORDER BY start_time
        ''', (today,), fetch_all=True)
        
        # Get setting
        setting = db_query("SELECT value FROM settings WHERE key = 'hourly_report'", fetch_one=True)
        if not setting or setting['value'] != '1':
            return
        
        # Create beautiful report
        emoji = "🌅" if now.hour < 12 else "☀️" if now.hour < 17 else "🌙"
        
        message = f"{emoji} <b>HOURLY REPORT</b> {emoji}\n"
        message += "━" * 35 + "\n"
        message += f"🕐 Time: <code>{now.strftime('%I:%M %p')}</code> IST\n"
        message += f"📅 Date: <code>{now.strftime('%B %d, %Y')}</code>\n"
        message += "📊 Task Status Update:\n\n"
        
        if not tasks:
            message += f"<blockquote>✅ <b>No tasks for today!</b>\n"
            message += f"✨ Enjoy your free time! 🎉</blockquote>\n"
        else:
            completed = sum(1 for t in tasks if t['completed'])
            total = len(tasks)
            
            # Progress bar
            progress_percent = int((completed / total) * 100) if total > 0 else 0
            progress_bar = "█" * (progress_percent // 5) + "░" * (20 - (progress_percent // 5))
            
            message += f"<b>{completed}/{total}</b> tasks completed\n"
            message += f"<code>{progress_bar}</code> {progress_percent}%\n\n"
            
            for task in tasks:
                status = "✅" if task['completed'] else "⏳"
                start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
                start_time = IST.localize(start_time)
                end_time = datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S')
                end_time = IST.localize(end_time)
                
                # Get subtask progress
                subtasks = db_query('SELECT * FROM subtasks WHERE task_id = ?', (task['id'],), fetch_all=True)
                completed_subtasks = sum(1 for st in subtasks if st['completed'])
                total_subtasks = len(subtasks)
                
                progress = f" ({completed_subtasks}/{total_subtasks})" if total_subtasks > 0 else ""
                
                message += f"{status} <b>{task['title']}</b>{progress}\n"
                message += f"   ⏰ {start_time.strftime('%I:%M')} - {end_time.strftime('%I:%M %p')}\n"
        
        message += "━" * 35 + "\n"
        
        if completed == total and total > 0:
            message += f"<i>🎉 Amazing! All tasks completed! 🎉</i>\n"
        elif completed > 0:
            message += f"<i>🔥 Keep going! You're doing great!</i>\n"
        else:
            message += f"<i>💪 Let's get started! You can do it!</i>\n"
        
        send_telegram_message(message)
        
    except Exception as e:
        print(f"❌ Hourly report error: {e}")

def check_note_notifications():
    """Check and send note notifications based on interval"""
    try:
        now = get_ist_time()
        
        notes = db_query('''
            SELECT * FROM notes 
            WHERE notify_enabled = 1 
            AND notify_interval > 0
        ''', fetch_all=True)
        
        for note in notes:
            note_id = note['id']
            interval_hours = note['notify_interval']
            last_notified = note['last_notified']
            
            should_notify = False
            
            if last_notified:
                last_time = datetime.strptime(last_notified, '%Y-%m-%d %H:%M:%S')
                last_time = IST.localize(last_time)
                hours_since = (now - last_time).total_seconds() / 3600
                should_notify = hours_since >= interval_hours
            else:
                should_notify = True
            
            if should_notify:
                # Create beautiful note reminder
                message = f"📝 <b>NOTE REMINDER</b>\n"
                message += "━" * 30 + "\n"
                message += f"<blockquote>💡 <b>{note['title']}</b></blockquote>\n"
                
                if note['description']:
                    desc = note['description'][:150]
                    if len(note['description']) > 150:
                        desc += "..."
                    message += f"<i>{desc}</i>\n\n"
                
                message += f"🔄 Interval: Every <b>{interval_hours}h</b>\n"
                message += f"🕐 Time: <code>{now.strftime('%I:%M %p')}</code> IST\n"
                message += "━" * 30 + "\n"
                message += f"<i>📱 Check the note in web app</i>\n"
                
                if send_telegram_message(message):
                    db_query(
                        "UPDATE notes SET last_notified = ? WHERE id = ?",
                        (now.strftime('%Y-%m-%d %H:%M:%S'), note_id)
                    )
                    
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
            
            # Check for hourly report
            now = get_ist_time()
            
            # Send hourly report at minute 0
            if now.minute == 0:
                print("📊 Sending hourly report...")
                send_hourly_report()
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
    chat_id = str(message.chat.id)
    
    # Check authorization
    if chat_id != USER_ID:
        bot.reply_to(message, "❌ <b>Unauthorized Access</b>\n\nThis bot is private and can only be used by the owner.\n\nPlease contact the administrator if you need access.")
        return
    
    now = get_ist_time()
    
    # Create inline keyboard with more buttons
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📋 Today's Tasks", callback_data='today_tasks'),
        InlineKeyboardButton("➕ Add New Task", callback_data='add_task_menu'),
        InlineKeyboardButton("📊 Hourly Report", callback_data='hourly_report'),
        InlineKeyboardButton("⏰ Current Time", callback_data='current_time'),
        InlineKeyboardButton("🔔 Test Notification", callback_data='test_notification'),
        InlineKeyboardButton("📝 View Notes", callback_data='view_notes'),
        InlineKeyboardButton("📅 View History", callback_data='view_history'),
        InlineKeyboardButton("🌐 Open Web App", web_app=WebAppInfo(url=f"https://patient-maxie-sandip232-786edcb8.koyeb.app/"))
    )
    
    welcome = f"""
✨ <b>Welcome to Task Tracker Pro!</b> ✨

━━━━━━━━━━━━━━━━━━━━
📱 <b>Quick Actions</b>
• Tap buttons below for instant access
• Manage tasks on the go
• Get real-time updates

🕐 <b>Current Time</b>
⏰ {now.strftime('%I:%M %p')} IST
📅 {now.strftime('%B %d, %Y')}

🔔 <b>Notifications</b>
• 10 reminders before each task
• Hourly progress reports
• Note reminders at custom intervals

━━━━━━━━━━━━━━━━━━━━
📲 <b>Web Interface</b>
https://patient-maxie-sandip232-786edcb8.koyeb.app/

💡 <b>Tip</b>: Use the web app for full features!
"""
    bot.send_message(message.chat.id, welcome, parse_mode='HTML', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """Handle inline button callbacks"""
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    if str(chat_id) != USER_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized access", show_alert=True)
        return
    
    try:
        if call.data == 'today_tasks':
            send_today_tasks_callback(chat_id, message_id)
        elif call.data == 'add_task_menu':
            show_add_task_menu(chat_id, message_id)
        elif call.data == 'hourly_report':
            send_hourly_report_callback(chat_id)
        elif call.data == 'current_time':
            send_current_time_callback(chat_id)
        elif call.data == 'test_notification':
            send_test_notification_callback(chat_id)
        elif call.data == 'view_notes':
            send_notes_list_callback(chat_id, message_id)
        elif call.data == 'view_history':
            send_recent_history_callback(chat_id, message_id)
        elif call.data.startswith('add_task_'):
            # Handle quick add task templates
            template = call.data.split('_')[2]
            handle_quick_add_task(chat_id, template)
        
        bot.answer_callback_query(call.id)
    except Exception as e:
        print(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "❌ Error occurred", show_alert=True)

def send_today_tasks_callback(chat_id, message_id):
    """Send today's tasks via callback"""
    now = get_ist_time()
    today = now.strftime('%Y-%m-%d')
    tasks = db_query('''
        SELECT * FROM tasks 
        WHERE date(start_time) = ?
        ORDER BY start_time
    ''', (today,), fetch_all=True)
    
    if not tasks:
        response = f"📅 <b>Today's Tasks</b>\n"
        response += "━" * 25 + "\n"
        response += f"<blockquote>✨ <b>No tasks for today!</b>\n"
        response += f"Enjoy your free time! 🎉</blockquote>\n\n"
        response += f"🕐 {now.strftime('%I:%M %p')} IST\n"
        response += f"📅 {now.strftime('%B %d, %Y')}"
    else:
        completed = sum(1 for t in tasks if t['completed'])
        total = len(tasks)
        
        response = f"📅 <b>Today's Tasks</b>\n"
        response += "━" * 25 + "\n"
        response += f"📊 <b>{completed}/{total}</b> tasks completed\n\n"
        
        for task in tasks:
            status = "✅" if task['completed'] else "⏳"
            start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
            start_time = IST.localize(start_time)
            end_time = datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S')
            end_time = IST.localize(end_time)
            
            # Get subtask progress
            subtasks = db_query('SELECT * FROM subtasks WHERE task_id = ?', (task['id'],), fetch_all=True)
            completed_subtasks = sum(1 for st in subtasks if st['completed'])
            total_subtasks = len(subtasks)
            
            progress = f" ({completed_subtasks}/{total_subtasks})" if total_subtasks > 0 else ""
            
            response += f"{status} <b>{task['title']}</b>{progress}\n"
            response += f"   ⏰ {start_time.strftime('%I:%M')} - {end_time.strftime('%I:%M %p')}\n\n"
        
        response += f"🕐 {now.strftime('%I:%M %p')} IST"
    
    # Add keyboard with action buttons
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("➕ Add Task", callback_data='add_task_menu'),
        InlineKeyboardButton("🔄 Refresh", callback_data='today_tasks'),
        InlineKeyboardButton("🌐 Web App", web_app=WebAppInfo(url=f"https://patient-maxie-sandip232-786edcb8.koyeb.app/"))
    )
    
    bot.edit_message_text(response, chat_id, message_id, parse_mode='HTML', reply_markup=keyboard)

def show_add_task_menu(chat_id, message_id):
    """Show add task menu with templates"""
    message = "➕ <b>Add New Task</b>\n"
    message += "━" * 25 + "\n"
    message += "Select a quick template or use the web app for full options:\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📞 Meeting (1h)", callback_data='add_task_meeting'),
        InlineKeyboardButton("💻 Work Session (2h)", callback_data='add_task_work'),
        InlineKeyboardButton("📚 Study (1.5h)", callback_data='add_task_study'),
        InlineKeyboardButton("🏋️ Exercise (45m)", callback_data='add_task_exercise'),
        InlineKeyboardButton("🌐 Web App (Full)", web_app=WebAppInfo(url=f"https://patient-maxie-sandip232-786edcb8.koyeb.app/?view=tasks")),
        InlineKeyboardButton("↩️ Back", callback_data='today_tasks')
    )
    
    bot.edit_message_text(message, chat_id, message_id, parse_mode='HTML', reply_markup=keyboard)

def handle_quick_add_task(chat_id, template):
    """Handle quick add task from template"""
    now = get_ist_time()
    today = now.strftime('%Y-%m-%d')
    
    templates = {
        'meeting': {'title': 'Team Meeting', 'duration': 60},
        'work': {'title': 'Work Session', 'duration': 120},
        'study': {'title': 'Study Time', 'duration': 90},
        'exercise': {'title': 'Exercise', 'duration': 45}
    }
    
    if template in templates:
        template_data = templates[template]
        
        # Calculate times
        start_time = now
        end_time = now + timedelta(minutes=template_data['duration'])
        
        start_str = start_time.strftime('%H:%M')
        end_str = end_time.strftime('%H:%M')
        
        # Add task to database
        start_datetime = start_time.strftime('%Y-%m-%d %H:%M:%S')
        end_datetime = end_time.strftime('%Y-%m-%d %H:%M:%S')
        
        task_id = db_query(
            "INSERT INTO tasks (title, start_time, end_time) VALUES (?, ?, ?)",
            (template_data['title'], start_datetime, end_datetime)
        )
        
        # Send confirmation
        message = f"✅ <b>Quick Task Added!</b>\n"
        message += "━" * 25 + "\n"
        message += f"📝 <b>{template_data['title']}</b>\n"
        message += f"🕐 {start_str} - {end_str} IST\n"
        message += f"⏱️ Duration: {template_data['duration']} minutes\n\n"
        message += f"🔔 Notifications will start 10 minutes before"
        
        bot.send_message(chat_id, message, parse_mode='HTML')

def send_hourly_report_callback(chat_id):
    """Send hourly report via callback"""
    send_hourly_report()
    bot.send_message(chat_id, "📊 <b>Hourly report sent!</b>\nCheck your messages for the update.", parse_mode='HTML')

def send_current_time_callback(chat_id):
    """Send current IST time via callback"""
    now = get_ist_time()
    time_msg = f"⏰ <b>Current Time</b>\n"
    time_msg += "━" * 25 + "\n"
    time_msg += f"🕐 IST: <code>{now.strftime('%I:%M:%S %p')}</code>\n"
    time_msg += f"📅 Date: <code>{now.strftime('%B %d, %Y')}</code>\n"
    time_msg += f"🌐 Timezone: <code>Asia/Kolkata</code>\n"
    time_msg += "━" * 25 + "\n"
    time_msg += f"<i>Your local time in India</i>"
    
    bot.send_message(chat_id, time_msg, parse_mode='HTML')

def send_test_notification_callback(chat_id):
    """Send test notification via callback"""
    if send_test_notification():
        bot.send_message(chat_id, "🔔 <b>Test notification sent!</b>\nCheck your messages for the beautiful notification.", parse_mode='HTML')
    else:
        bot.send_message(chat_id, "❌ <b>Failed to send test</b>\nPlease check the server logs.", parse_mode='HTML')

def send_notes_list_callback(chat_id, message_id):
    """Send notes list via callback"""
    notes = db_query('SELECT * FROM notes ORDER BY priority', fetch_all=True)
    
    if not notes:
        response = f"📝 <b>Your Notes</b>\n"
        response += "━" * 25 + "\n"
        response += f"<blockquote>📭 <b>No notes yet!</b>\n"
        response += f"Add your first note to get started!</blockquote>\n\n"
        response += f"💡 Use the web app to add notes"
    else:
        response = f"📝 <b>Your Notes</b> ({len(notes)})\n"
        response += "━" * 25 + "\n"
        
        for note in notes:
            created = datetime.strptime(note['created_at'], '%Y-%m-%d %H:%M:%S')
            created = IST.localize(created)
            
            response += f"📌 <b>{note['title']}</b>\n"
            
            if note['description']:
                desc = note['description'][:50]
                if len(note['description']) > 50:
                    desc += "..."
                response += f"   <i>{desc}</i>\n"
            
            if note['notify_enabled'] and note['notify_interval'] > 0:
                response += f"   🔔 Every {note['notify_interval']}h\n"
            
            response += f"   📅 Created: {created.strftime('%b %d, %Y')}\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("➕ Add Note", web_app=WebAppInfo(url=f"https://patient-maxie-sandip232-786edcb8.koyeb.app/?view=notes")),
        InlineKeyboardButton("🌐 Web App", web_app=WebAppInfo(url=f"https://patient-maxie-sandip232-786edcb8.koyeb.app/")),
        InlineKeyboardButton("↩️ Back", callback_data='today_tasks')
    )
    
    bot.edit_message_text(response, chat_id, message_id, parse_mode='HTML', reply_markup=keyboard)

def send_recent_history_callback(chat_id, message_id):
    """Send recent history via callback"""
    history = db_query('''
        SELECT * FROM history 
        ORDER BY completed_at DESC 
        LIMIT 5
    ''', fetch_all=True)
    
    if not history:
        response = f"📜 <b>Task History</b>\n"
        response += "━" * 25 + "\n"
        response += f"<blockquote>📭 <b>No completed tasks yet!</b>\n"
        response += f"Complete some tasks to see history here!</blockquote>"
    else:
        response = f"📜 <b>Recent History</b>\n"
        response += "━" * 25 + "\n"
        
        for item in history:
            completed = datetime.strptime(item['completed_at'], '%Y-%m-%d %H:%M:%S')
            completed = IST.localize(completed)
            
            response += f"✅ <b>{item['title']}</b>\n"
            response += f"   🕐 {completed.strftime('%I:%M %p')}\n"
            response += f"   📅 {completed.strftime('%b %d')}\n\n"
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📋 Today's Tasks", callback_data='today_tasks'),
        InlineKeyboardButton("🌐 Full History", web_app=WebAppInfo(url=f"https://patient-maxie-sandip232-786edcb8.koyeb.app/?view=history")),
        InlineKeyboardButton("↩️ Back", callback_data='today_tasks')
    )
    
    bot.edit_message_text(response, chat_id, message_id, parse_mode='HTML', reply_markup=keyboard)

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
            'class': 'completed'
        }
    
    if not is_active:
        return {
            'text': 'Inactive',
            'status': 'inactive',
            'class': 'inactive'
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
        minutes_before = start_minutes - current_minutes
        hours = minutes_before // 60
        
        if hours >= 24:
            days = hours // 24
            return {
                'text': f'In {days}d',
                'status': 'upcoming',
                'class': 'upcoming'
            }
        elif hours > 0:
            return {
                'text': f'In {hours}h',
                'status': 'upcoming',
                'class': 'upcoming'
            }
        else:
            return {
                'text': 'Upcoming',
                'status': 'upcoming',
                'class': 'upcoming'
            }
    elif current_minutes >= (start_minutes - two_hours) and current_minutes < start_minutes:
        # Within 2 hours of start
        minutes_before = start_minutes - current_minutes
        
        if minutes_before > 60:
            hours = minutes_before // 60
            mins = minutes_before % 60
            return {
                'text': f'In {hours}h {mins}m',
                'status': 'starting_soon',
                'class': 'starting_soon'
            }
        else:
            return {
                'text': f'In {minutes_before}m',
                'status': 'starting_soon',
                'class': 'starting_soon'
            }
    elif current_minutes >= start_minutes and current_minutes <= end_minutes:
        # During task time
        minutes_left = end_minutes - current_minutes
        
        if minutes_left > 60:
            hours = minutes_left // 60
            mins = minutes_left % 60
            return {
                'text': f'{hours}h {mins}m left',
                'status': 'active',
                'class': 'active'
            }
        else:
            return {
                'text': f'{minutes_left}m left',
                'status': 'active',
                'class': 'active'
            }
    elif current_minutes > end_minutes and current_minutes <= (end_minutes + two_hours):
        # Within 2 hours after end
        minutes_over = current_minutes - end_minutes
        
        if minutes_over > 60:
            hours = minutes_over // 60
            mins = minutes_over % 60
            return {
                'text': f'{hours}h {mins}m ago',
                'status': 'due',
                'class': 'due'
            }
        else:
            return {
                'text': f'{minutes_over}m ago',
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
    # Auto-login (no access code needed)
    session['logged_in'] = True
    
    # Get current view
    view = request.args.get('view', 'tasks')
    
    # Get current IST time
    now = get_ist_time()
    today = now.strftime('%Y-%m-%d')
    
    # Get tasks for today
    tasks = db_query('''
        SELECT * FROM tasks 
        WHERE date(start_time) = ?
        ORDER BY start_time
    ''', (today,), fetch_all=True)
    
    # Get all tasks for stats
    all_tasks = db_query('SELECT * FROM tasks', fetch_all=True)
    
    # Get history
    history = db_query('''
        SELECT h.* 
        FROM history h
        ORDER BY h.completed_at DESC
        LIMIT 20
    ''', fetch_all=True)
    
    # Get history subtasks
    history_with_subtasks = []
    for item in history:
        item_dict = row_to_dict(item)
        if item_dict:
            subtasks = db_query('''
                SELECT * FROM history_subtasks 
                WHERE history_id = ?
            ''', (item_dict['id'],), fetch_all=True)
            item_dict['subtasks'] = [row_to_dict(st) for st in subtasks]
            history_with_subtasks.append(item_dict)
    
    # Get notes
    notes = db_query('SELECT * FROM notes ORDER BY priority', fetch_all=True)
    
    # Get settings
    settings = {}
    setting_rows = db_query("SELECT key, value FROM settings", fetch_all=True)
    for row in setting_rows:
        row_dict = row_to_dict(row)
        if row_dict:
            settings[row_dict['key']] = row_dict['value']
    
    # Calculate stats
    completed_today = sum(1 for t in tasks if t['completed'])
    pending_today = len(tasks) - completed_today
    
    # Process tasks for display
    processed_tasks = []
    for task in tasks:
        task_dict = row_to_dict(task)
        if not task_dict:
            continue
            
        # Get subtasks
        subtasks = db_query('''
            SELECT * FROM subtasks 
            WHERE task_id = ?
            ORDER BY priority
        ''', (task_dict['id'],), fetch_all=True)
        
        completed_subtasks = sum(1 for st in subtasks if st['completed'])
        total_subtasks = len(subtasks)
        progress_percentage = round((completed_subtasks / total_subtasks * 100)) if total_subtasks > 0 else 0
        
        # Format times
        start_dt = datetime.strptime(task_dict['start_time'], '%Y-%m-%d %H:%M:%S')
        start_dt = IST.localize(start_dt)
        end_dt = datetime.strptime(task_dict['end_time'], '%Y-%m-%d %H:%M:%S')
        end_dt = IST.localize(end_dt)
        
        # Calculate time status
        time_info = calculate_time_status(
            task_dict['start_time'],
            task_dict['end_time'],
            not task_dict['completed'],
            task_dict['completed']
        )
        
        # Format repeat text
        repeat_text = ''
        if task_dict['repeat'] != 'none':
            if task_dict['repeat'] == 'daily':
                repeat_text = 'Daily'
            elif task_dict['repeat'] == 'weekly':
                day = task_dict['repeat_day'] or 'Monday'
                repeat_text = f'Weekly on {day}'
        
        processed_tasks.append({
            'id': task_dict['id'],
            'title': task_dict['title'],
            'description': task_dict['description'],
            'start_time': task_dict['start_time'],
            'end_time': task_dict['end_time'],
            'start_display': start_dt.strftime('%I:%M %p'),
            'end_display': end_dt.strftime('%I:%M %p'),
            'date_range': start_dt.strftime('%b %d'),
            'time_range': f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}",
            'completed': task_dict['completed'],
            'notify_enabled': task_dict['notify_enabled'],
            'priority': task_dict['priority'],
            'repeat': task_dict['repeat'],
            'repeat_day': task_dict['repeat_day'],
            'repeat_text': repeat_text,
            'subtasks': [row_to_dict(st) for st in subtasks],
            'completed_subtasks': completed_subtasks,
            'total_subtasks': total_subtasks,
            'progress_percentage': progress_percentage,
            'time_status': time_info,
            'is_active': not task_dict['completed'],
            'is_completed_repeating': task_dict['repeat'] != 'none' and task_dict['completed']
        })
    
    # Process notes for display
    processed_notes = []
    for note in notes:
        note_dict = row_to_dict(note)
        if note_dict:
            created_at = datetime.strptime(note_dict['created_at'], '%Y-%m-%d %H:%M:%S')
            created_at = IST.localize(created_at)
            updated_at = datetime.strptime(note_dict['updated_at'], '%Y-%m-%d %H:%M:%S')
            updated_at = IST.localize(updated_at)
            
            # Format created date nicely
            created_display = created_at.strftime('%b %d, %Y')
            
            processed_notes.append({
                'id': note_dict['id'],
                'title': note_dict['title'],
                'description': note_dict['description'],
                'priority': note_dict['priority'],
                'created_at': note_dict['created_at'],
                'updated_at': note_dict['updated_at'],
                'created_display': created_display,
                'updated_display': updated_at.strftime('%b %d, %Y'),
                'notify_enabled': note_dict['notify_enabled'],
                'notify_interval': note_dict['notify_interval']
            })
    
    # Group history by date
    grouped_history = {}
    for item in history_with_subtasks:
        date = item['completed_at'][:10]
        date_display = datetime.strptime(date, '%Y-%m-%d').strftime('%B %d, %Y')
        if date_display not in grouped_history:
            grouped_history[date_display] = []
        grouped_history[date_display].append(item)
    
    # Sort dates newest first
    grouped_history = dict(sorted(grouped_history.items(), key=lambda x: datetime.strptime(x[0], '%B %d, %Y'), reverse=True))
    
    # Render the HTML template
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en" id="theme-element">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Task Tracker Pro</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            /* Base Styles */
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
            
            /* Header Styles - Single horizontal line */
            .header { 
                background-color: var(--light); 
                padding: 12px 16px; 
                display: flex; 
                align-items: center; 
                justify-content: space-between; 
                box-shadow: var(--shadow); 
                position: sticky; 
                top: 0; 
                z-index: 100;
                flex-wrap: nowrap;
                overflow-x: auto;
                white-space: nowrap;
                gap: 8px;
            }
            
            .header::-webkit-scrollbar {
                display: none;
            }
            
            .header-action-btn {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                background: transparent;
                color: var(--gray);
                border: none;
                border-radius: var(--border-radius);
                padding: 8px 12px;
                cursor: pointer;
                transition: var(--transition);
                min-width: 70px;
                flex-shrink: 0;
            }
            
            .header-action-btn i { 
                font-size: 1.2rem; 
                margin-bottom: 4px;
            }
            
            .header-action-btn span { 
                font-size: 0.7rem; 
                font-weight: 600; 
            }
            
            .header-action-btn:hover { 
                color: var(--primary); 
                background: rgba(67, 97, 238, 0.1);
            }
            
            .header-action-btn.active { 
                color: var(--primary); 
                background: rgba(67, 97, 238, 0.15);
                border-bottom: 2px solid var(--primary);
            }
            
            @media (max-width: 768px) {
                .header { 
                    padding: 10px 12px;
                    gap: 6px;
                }
                
                .header-action-btn { 
                    min-width: 65px;
                    padding: 6px 8px;
                }
                
                .header-action-btn i { 
                    font-size: 1.1rem; 
                }
                
                .header-action-btn span { 
                    font-size: 0.65rem; 
                }
            }
            
            /* Time Display */
            .time-display {
                background: var(--primary);
                color: white;
                padding: 6px 12px;
                border-radius: 20px;
                font-size: 0.8rem;
                font-weight: 600;
                margin-left: auto;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                gap: 6px;
            }

            /* Floating Action Buttons */
            .fab {
                position: fixed;
                width: 56px;
                height: 56px;
                background-color: var(--primary);
                color: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.4rem;
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
            
            /* Task Cards - Same as PHP version */
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
                border-left: 4px solid var(--primary);
            }
            
            .task-card.completed {
                border-left-color: var(--success);
                opacity: 0.8;
            }
            
            .task-card.completed-repeating {
                background-color: var(--completed-bg);
                opacity: 0.8;
                border-left-color: var(--completed-text);
            }
            
            .task-card.upcoming {
                border-left-color: var(--warning);
            }
            
            .task-card.active {
                border-left-color: var(--success);
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.9; }
            }
            
            .task-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
            .task-title { font-size: 1rem; font-weight: 600; color: var(--dark); }
            .task-status { font-size: 0.7rem; padding: 3px 8px; border-radius: 20px; font-weight: 600; }
            .status-pending { background: #fff3cd; color: #856404; }
            .status-completed { background: #d4edda; color: #155724; }
            
            .task-time { display: flex; align-items: center; gap: 8px; color: var(--gray); font-size: 0.8rem; margin: 8px 0; }
            .task-notice { font-size: 0.7rem; color: var(--warning); margin: 5px 0; }
            
            .task-actions { 
                display: grid; 
                grid-template-columns: 1fr 1fr; 
                gap: 10px; 
                margin-top: 15px; 
            }
            
            .action-btn { 
                padding: 8px; 
                border: none; 
                border-radius: 8px; 
                font-size: 0.8rem; 
                cursor: pointer; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                gap: 5px; 
                font-weight: 600;
                transition: var(--transition);
            }
            
            .btn-success { background: var(--success); color: white; }
            .btn-success:hover { background: #3db8d8; }
            
            .btn-danger { background: var(--danger); color: white; }
            .btn-danger:hover { background: #e01e6e; }
            
            .btn-primary { background: var(--primary); color: white; }
            .btn-primary:hover { background: var(--primary-light); }
            
            .btn-warning { background: var(--warning); color: white; }
            .btn-warning:hover { background: #f57c00; }
            
            .task-meta { display: flex; align-items: center; justify-content: space-between; font-size: 0.7rem; color: var(--gray); margin-top: auto; padding-top: 12px; }
            .repeat-badge { background-color: rgba(67, 97, 238, 0.1); color: var(--primary); padding: 3px 8px; border-radius: 20px; font-size: 0.65rem; font-weight: 600; display: flex; align-items: center; gap: 4px; }
            .priority-badge { background-color: rgba(108, 117, 125, 0.2); color: var(--gray); padding: 3px 8px; border-radius: 20px; font-size: 0.65rem; font-weight: 600; display: flex; align-items: center; gap: 4px; }
            
            .notify-badge {
                background-color: var(--notify-bg);
                color: var(--notify-color);
                padding: 3px 8px;
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
            
            .time-remaining-badge { 
                padding: 4px 10px; 
                border-radius: 20px; 
                font-size: 0.7rem; 
                font-weight: 600; 
                display: inline-block;
                margin-left: auto;
            }
            
            .time-remaining-badge.upcoming { background-color: rgba(108, 117, 125, 0.2); color: var(--gray); }
            .time-remaining-badge.starting_soon { background-color: rgba(248, 150, 30, 0.1); color: var(--warning); }
            .time-remaining-badge.active { background-color: rgba(76, 201, 240, 0.2); color: var(--success); }
            .time-remaining-badge.due { background-color: rgba(248, 150, 30, 0.1); color: var(--warning); }
            .time-remaining-badge.overdue { background-color: rgba(247, 37, 133, 0.1); color: var(--danger); }
            .time-remaining-badge.completed { background-color: rgba(76, 201, 240, 0.2); color: var(--success); }
            .time-remaining-badge.inactive { background-color: rgba(108, 117, 125, 0.2); color: var(--gray); }
            
            /* Subtasks */
            .subtasks-details { margin-top: 12px; border-top: 1px solid var(--gray-light); padding-top: 12px; }
            .subtasks-details summary { cursor: pointer; display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 0.8rem; color: var(--primary); padding: 4px 0; transition: var(--transition); }
            .subtasks-details summary:hover { color: var(--primary-light); }
            .details-toggle { margin-left: auto; transition: var(--transition); }
            .subtasks-details[open] .details-toggle { transform: rotate(90deg); }
            .subtasks-content { margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(0,0,0,0.05); }
            
            .subtask-item { display: flex; align-items: flex-start; margin-bottom: 8px; padding: 8px; background: rgba(0,0,0,0.03); border-radius: 6px; }
            .subtask-details-container { flex: 1; margin-right: 8px;}
            .subtask-title { font-size: 0.8rem; color: var(--dark); cursor: pointer; }
            .subtask-completed { text-decoration: line-through; color: var(--gray); }
            .subtask-description { font-size: 0.7rem; color: var(--gray); margin-top: 4px; padding-left: 8px; border-left: 2px solid var(--primary-light); line-height: 1.4; }
            .subtask-actions { display: flex; align-items: center; margin-left: auto; }
            
            .subtask-number-badge { width: 20px; height: 20px; border-radius: 50%; background-color: var(--gray-light); color: var(--dark); display: flex; align-items: center; justify-content: center; font-size: 0.65rem; font-weight: bold; transition: var(--transition); }
            .subtask-number-badge.completed { background-color: var(--primary); color: white; }
            .subtask-complete-btn { background: none; border: none; cursor: pointer; padding: 0; margin-right: 8px;}
            .edit-subtask-btn, .delete-subtask-btn { background: none; border: none; color: var(--primary); cursor: pointer; font-size: 0.7rem; opacity: 0.7; transition: var(--transition); padding: 2px 4px; }
            .edit-subtask-btn:hover, .delete-subtask-btn:hover { opacity: 1; transform: scale(1.1); }
            .delete-subtask-btn { color: var(--danger); }
            
            .progress-display-container { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
            .progress-circle { width: 36px; height: 36px; border-radius: 50%; background: conic-gradient(var(--primary) 0%, var(--gray-light) 0%); display: flex; align-items: center; justify-content: center; position: relative; flex-shrink: 0; }
            .progress-circle::before { content: ''; position: absolute; width: 26px; height: 26px; background-color: var(--light); border-radius: 50%; }
            .progress-text { font-size: 0.75rem; color: var(--gray); }
            
            /* Notes Styles - Updated for right alignment */
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
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 0;
                padding-bottom: 0;
                border-bottom: none;
            }
            
            .note-title-section {
                flex: 1;
            }
            
            .note-title {
                font-size: 1.1rem;
                font-weight: 700;
                color: var(--dark);
                margin-bottom: 4px;
                line-height: 1.3;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .note-date {
                font-size: 0.75rem;
                color: var(--gray);
                font-weight: 500;
                margin-left: auto;
                white-space: nowrap;
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
            
            .note-footer {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-top: auto;
                padding-top: 12px;
                border-top: 1px solid rgba(0,0,0,0.05);
            }
            
            .note-meta {
                display: flex;
                align-items: center;
                gap: 8px;
            }
            
            .note-date-badge {
                background: rgba(67, 97, 238, 0.1);
                color: var(--primary);
                padding: 4px 8px;
                border-radius: 12px;
                font-size: 0.7rem;
                font-weight: 500;
            }
            
            .note-interval-badge {
                background: rgba(248, 150, 30, 0.1);
                color: var(--notify-color);
                padding: 4px 8px;
                border-radius: 12px;
                font-size: 0.7rem;
                font-weight: 500;
                display: flex;
                align-items: center;
                gap: 4px;
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
            
            /* Empty State */
            .empty-state { 
                text-align: center; 
                padding: 40px 16px; 
                color: var(--gray); 
                grid-column: 1 / -1;
            }
            
            .empty-state i { 
                font-size: 3rem; 
                margin-bottom: 16px; 
                opacity: 0.3; 
            }
            
            .empty-state p { 
                font-size: 1rem; 
                margin-bottom: 20px; 
            }
            
            /* Modals */
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.5); z-index: 1000; align-items: center; justify-content: center; animation: fadeIn 0.3s ease; }
            .modal-content { background-color: var(--light); border-radius: var(--border-radius); width: 90%; max-width: 500px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2); animation: scaleIn 0.3s ease; overflow: hidden; max-height: 90vh; overflow-y: auto; }
            .modal-header { padding: 16px; border-bottom: 1px solid var(--gray-light); display: flex; align-items: center; justify-content: space-between; }
            .modal-title { font-size: 1.2rem; font-weight: 600; color: var(--dark); }
            .close-modal { background: none; border: none; font-size: 1.3rem; color: var(--gray); cursor: pointer; transition: var(--transition); }
            .close-modal:hover { color: var(--danger); }
            .modal-body { padding: 16px; }
            .form-group { margin-bottom: 12px; }
            .form-label { display: block; margin-bottom: 4px; font-weight: 600; color: var(--dark); font-size: 0.9rem; }
            .form-input, .form-select, .form-textarea { width: 100%; padding: 10px; border: 1px solid var(--gray-light); border-radius: 6px; background-color: var(--light); color: var(--dark); transition: var(--transition); font-size: 0.9rem; }
            .form-input:focus, .form-select:focus, .form-textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2); }
            .form-textarea { min-height: 80px; resize: vertical; line-height: 1.4; }
            .form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
            .btn { padding: 10px 18px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; transition: var(--transition); font-size: 0.9rem; }
            .time-input-group { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
            .date-input-group { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
            
            .checkbox-group { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
            .checkbox-label { font-weight: 500; color: var(--dark); font-size: 0.9rem; }
            .form-checkbox { width: 18px; height: 18px; }
            
            /* Animations */
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
            <button class="header-action-btn {{ 'active' if view == 'tasks' else '' }}" onclick="switchView('tasks')" title="Tasks">
                <i class="fas fa-tasks"></i>
                <span>Tasks</span>
            </button>
            <button class="header-action-btn {{ 'active' if view == 'notes' else '' }}" onclick="switchView('notes')" title="Notes">
                <i class="fas fa-wand-magic-sparkles"></i>
                <span>Notes</span>
            </button>
            <button class="header-action-btn {{ 'active' if view == 'history' else '' }}" onclick="switchView('history')" title="History">
                <i class="fas fa-history"></i>
                <span>History</span>
            </button>
            <button class="header-action-btn {{ 'active' if view == 'settings' else '' }}" onclick="switchView('settings')" title="Settings">
                <i class="fas fa-cog"></i>
                <span>Settings</span>
            </button>
            <div class="time-display">
                <i class="fas fa-clock"></i>
                {{ now.strftime('%I:%M %p') }} IST
            </div>
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
                
                <!-- Stats Cards -->
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px;">
                    <div style="background: var(--primary); color: white; padding: 16px; border-radius: var(--border-radius); text-align: center;">
                        <div style="font-size: 1.5rem; font-weight: bold;">{{ processed_tasks|length }}</div>
                        <div style="font-size: 0.8rem;">Total Tasks</div>
                    </div>
                    <div style="background: var(--success); color: white; padding: 16px; border-radius: var(--border-radius); text-align: center;">
                        <div style="font-size: 1.5rem; font-weight: bold;">{{ completed_today }}</div>
                        <div style="font-size: 0.8rem;">Completed</div>
                    </div>
                    <div style="background: var(--warning); color: white; padding: 16px; border-radius: var(--border-radius); text-align: center;">
                        <div style="font-size: 1.5rem; font-weight: bold;">{{ pending_today }}</div>
                        <div style="font-size: 0.8rem;">Pending</div>
                    </div>
                </div>
                
                <div class="bucket-header">
                    <h2 class="bucket-title">
                        <i class="fas fa-tasks"></i>
                        Today's Tasks
                        <span class="bucket-count">{{ processed_tasks|length }}</span>
                    </h2>
                </div>
                
                <div class="items-container">
                    {% if not processed_tasks %}
                    <div class="empty-state">
                        <i class="fas fa-clipboard-list"></i>
                        <p>No tasks for today. Add a new one to get started!</p>
                        <button class="btn btn-primary" onclick="openAddTaskModal()">
                            <i class="fas fa-plus"></i> Add Your First Task
                        </button>
                    </div>
                    {% else %}
                        {% for task in processed_tasks %}
                        <div class="task-card {{ 'completed' if task.completed else '' }} {{ 'active' if task.time_status.class == 'active' else '' }} {{ 'upcoming' if task.time_status.class == 'starting_soon' else '' }}">
                            <div class="task-header">
                                <div class="task-title">{{ task.title }}</div>
                                <div class="task-status {{ 'status-completed' if task.completed else 'status-pending' }}">
                                    {{ '✅ Completed' if task.completed else '⏳ Pending' }}
                                </div>
                            </div>
                            
                            <div class="task-time">
                                <i class="far fa-clock"></i>
                                {{ task.start_display }} - {{ task.end_display }} IST
                                <span class="time-remaining-badge {{ task.time_status.class }}">
                                    {{ task.time_status.text }}
                                </span>
                            </div>
                            
                            {% if task.time_status.class == 'starting_soon' and not task.completed %}
                            <div class="task-notice">
                                <i class="fas fa-bell"></i>
                                Notifications active: {{ task.time_status.text }}
                            </div>
                            {% endif %}
                            
                            {% if task.description %}
                            <div style="font-size: 0.85rem; color: var(--gray); margin: 8px 0; line-height: 1.4;">
                                {{ format_text(task.description)|safe }}
                            </div>
                            {% endif %}
                            
                            {% if task.total_subtasks > 0 %}
                            <div class="progress-display-container">
                                <div class="progress-circle" style="background: conic-gradient(var(--primary) {{ task.progress_percentage }}%, var(--gray-light) 0%);">
                                    <span style="font-size: 0.65rem; z-index: 1;">{{ task.progress_percentage }}%</span>
                                </div>
                                <div class="progress-text">
                                    {{ task.completed_subtasks }} of {{ task.total_subtasks }} subtasks completed
                                </div>
                            </div>
                            {% endif %}
                            
                            <div class="task-actions">
                                {% if not task.completed %}
                                <form method="POST" action="/complete_task" style="display: contents;">
                                    <input type="hidden" name="task_id" value="{{ task.id }}">
                                    <button type="submit" class="action-btn btn-success">
                                        <i class="fas fa-check"></i> Complete
                                    </button>
                                </form>
                                {% endif %}
                                
                                <button class="action-btn btn-primary" onclick="openEditTaskModal('{{ task.id }}')">
                                    <i class="fas fa-edit"></i> Edit
                                </button>
                                
                                <button class="action-btn btn-warning" onclick="openAddSubtaskModal('{{ task.id }}')">
                                    <i class="fas fa-plus"></i> Subtask
                                </button>
                                
                                <form method="POST" action="/delete_task" style="display: contents;">
                                    <input type="hidden" name="task_id" value="{{ task.id }}">
                                    <button type="submit" class="action-btn btn-danger" onclick="return confirm('Delete this task?')">
                                        <i class="fas fa-trash"></i> Delete
                                    </button>
                                </form>
                            </div>
                            
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
                                {% if task.repeat_text %}
                                <span class="repeat-badge">
                                    <i class="fas fa-repeat"></i> {{ task.repeat_text }}
                                </span>
                                {% else %}
                                <span class="repeat-badge">
                                    <i class="fas fa-repeat"></i> None
                                </span>
                                {% endif %}
                                
                                <span class="priority-badge">P{{ task.priority }}</span>
                                
                                {% if task.notify_enabled %}
                                <span class="notify-badge">
                                    <i class="fas fa-bell"></i> Telegram
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
                    <div class="empty-state">
                        <i class="fas fa-wand-magic-sparkles"></i>
                        <p>No notes yet. Add one to get started!</p>
                        <button class="btn btn-primary" onclick="openAddNoteModal()">
                            <i class="fas fa-plus"></i> Add Your First Note
                        </button>
                    </div>
                    {% else %}
                        {% for note in processed_notes %}
                        <div class="note-card">
                            <details class="note-details">
                                <summary class="note-summary">
                                    <div class="note-header">
                                        <div class="note-title-section">
                                            <h3 class="note-title">{{ note.title }}</h3>
                                        </div>
                                        <div class="note-date">
                                            Created: {{ note.created_display }}
                                        </div>
                                    </div>
                                </summary>
                                <div class="note-content">
                                    {% if note.description %}
                                    <div class="note-description">{{ format_text(note.description)|safe }}</div>
                                    {% endif %}
                                    <div class="note-footer">
                                        <div class="note-meta">
                                            {% if note.notify_enabled and note.notify_interval > 0 %}
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
                    {% if not grouped_history %}
                    <div class="empty-state">
                        <i class="fas fa-history"></i>
                        <p>No completed items yet. Complete some items to see them here!</p>
                    </div>
                    {% else %}
                        {% for date_display, items in grouped_history.items() %}
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
                        <span class="settings-label">Hourly Task Status Reports</span>
                        <form method="POST" id="hourlyReportForm" action="/toggle_setting">
                            <input type="hidden" name="key" value="hourly_report">
                            <label class="toggle-switch">
                                <input type="checkbox" name="enabled" {{ 'checked' if settings.get('hourly_report') == '1' else '' }} onchange="this.form.submit()">
                                <span class="toggle-slider"></span>
                            </label>
                        </form>
                    </div>
                    
                    <p style="margin-top: 16px; color: var(--gray); font-size: 0.85rem;">
                        <i class="fas fa-info-circle"></i> 
                        Hourly reports send task status updates (completed/pending) to Telegram every hour.
                    </p>
                </div>
                
                <div class="settings-card">
                    <h2 class="settings-title">
                        <i class="fas fa-info-circle"></i>
                        System Information
                    </h2>
                    
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
                    
                    <div class="settings-item">
                        <span class="settings-label">Total History Items</span>
                        <span class="settings-value">{{ history|length }}</span>
                    </div>
                </div>
                
                <div class="settings-card">
                    <h2 class="settings-title">
                        <i class="fas fa-robot"></i>
                        Telegram Integration
                    </h2>
                    
                    <div class="settings-item">
                        <span class="settings-label">User ID</span>
                        <span class="settings-value">{{ USER_ID }}</span>
                    </div>
                    
                    <div class="settings-item">
                        <span class="settings-label">Task Reminders</span>
                        <span class="settings-value">10 messages before start</span>
                    </div>
                    
                    <div class="settings-item">
                        <span class="settings-label">Note Reminders</span>
                        <span class="settings-value">Custom intervals</span>
                    </div>
                    
                    <div class="settings-item">
                        <span class="settings-label">Status</span>
                        <span class="settings-value" style="color: var(--success);">✅ Active</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Modals -->
        <div class="modal" id="addTaskModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2 class="modal-title">Add New Task</h2>
                    <button type="button" class="close-modal" onclick="closeAddTaskModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <form method="POST" action="/add_task" id="addTaskForm">
                        <div class="form-group">
                            <label class="form-label">Task Title</label>
                            <input type="text" class="form-input" name="title" required placeholder="What needs to be done?">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Description (Optional)</label>
                            <textarea class="form-textarea" name="description" placeholder="Add details about the task..."></textarea>
                            <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Priority (1=High, 15=Low)</label>
                            <select class="form-select" name="priority">
                                {% for i in range(1, 16) %}
                                <option value="{{ i }}" {% if i==15 %}selected{% endif %}>{{ i }}</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="checkbox-group">
                            <input type="checkbox" class="form-checkbox" name="notify_enabled" id="notifyEnabled" checked>
                            <label class="checkbox-label" for="notifyEnabled">Telegram reminders (10 notifications before start)</label>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Repeat</label>
                            <select class="form-select" name="repeat" id="repeatSelect" onchange="toggleRepeatOptions()">
                                <option value="none">None (One-time task)</option>
                                <option value="daily">Daily</option>
                                <option value="weekly">Weekly on {{ now.strftime('%A') }}</option>
                            </select>
                        </div>
                        <div id="repeatDayGroup" style="display: none; margin-bottom: 12px;">
                            <label class="form-label">Repeat on day</label>
                            <select class="form-select" name="repeat_day" id="repeatDaySelect">
                                <option value="Monday">Monday</option>
                                <option value="Tuesday">Tuesday</option>
                                <option value="Wednesday">Wednesday</option>
                                <option value="Thursday">Thursday</option>
                                <option value="Friday">Friday</option>
                                <option value="Saturday">Saturday</option>
                                <option value="Sunday">Sunday</option>
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
                                <label class="form-label">Start Time (IST)</label>
                                <input type="time" class="form-input" name="start_time" id="startTime" value="{{ now.strftime('%H:%M') }}">
                            </div>
                            <div class="form-group">
                                <label class="form-label">End Time (IST)</label>
                                <input type="time" class="form-input" name="end_time" id="endTime" value="{{ (now + timedelta(hours=1)).strftime('%H:%M') }}">
                            </div>
                        </div>
                        <div class="form-group" id="repeatEndDateGroup" style="display: none;">
                            <label class="form-label">End of Repeat Date (Optional)</label>
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
                    <h2 class="modal-title">Add New Note</h2>
                    <button type="button" class="close-modal" onclick="closeAddNoteModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <form method="POST" action="/add_note">
                        <div class="form-group">
                            <label class="form-label">Note Title</label>
                            <input type="text" class="form-input" name="title" required placeholder="Note title...">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Description (Optional)</label>
                            <textarea class="form-textarea" name="description" placeholder="Add your note content here..."></textarea>
                            <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                        </div>
                        <div class="checkbox-group">
                            <input type="checkbox" class="form-checkbox" name="notify_enabled" id="noteNotifyEnabled">
                            <label class="checkbox-label" for="noteNotifyEnabled">Enable regular reminders</label>
                        </div>
                        <div class="form-group" id="noteIntervalGroup" style="display: none;">
                            <label class="form-label">Reminder Interval (hours)</label>
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
                            <label class="form-label">Note Title</label>
                            <input type="text" class="form-input" name="title" id="editNoteTitle" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Description</label>
                            <textarea class="form-textarea" name="description" id="editNoteDescription"></textarea>
                            <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                        </div>
                        <div class="checkbox-group">
                            <input type="checkbox" class="form-checkbox" name="notify_enabled" id="editNoteNotifyEnabled">
                            <label class="checkbox-label" for="editNoteNotifyEnabled">Enable regular reminders</label>
                        </div>
                        <div class="form-group" id="editNoteIntervalGroup" style="display: none;">
                            <label class="form-label">Reminder Interval (hours)</label>
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
                            <input type="text" class="form-input" name="title" required placeholder="What needs to be done?">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Description (Optional)</label>
                            <textarea class="form-textarea" name="description" placeholder="Add details..."></textarea>
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
                            <label class="form-label">Task Title</label>
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
                            <select class="form-select" name="repeat" id="editTaskRepeat" onchange="toggleEditRepeatOptions()">
                                <option value="none">None</option>
                                <option value="daily">Daily</option>
                                <option value="weekly">Weekly</option>
                            </select>
                        </div>
                        <div id="editRepeatDayGroup" style="display: none; margin-bottom: 12px;">
                            <label class="form-label">Repeat on day</label>
                            <select class="form-select" name="repeat_day" id="editRepeatDaySelect">
                                <option value="Monday">Monday</option>
                                <option value="Tuesday">Tuesday</option>
                                <option value="Wednesday">Wednesday</option>
                                <option value="Thursday">Thursday</option>
                                <option value="Friday">Friday</option>
                                <option value="Saturday">Saturday</option>
                                <option value="Sunday">Sunday</option>
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
                        <div class="form-group" id="editRepeatEndDateGroup" style="display: none;">
                            <label class="form-label">End of Repeat Date (Optional)</label>
                            <input type="date" class="form-input" name="repeat_end_date" id="editTaskRepeatEndDate">
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
                
                // Update active button
                document.querySelectorAll('.header-action-btn').forEach(btn => {
                    btn.classList.remove('active');
                });
                event.currentTarget.classList.add('active');
                
                // Show correct content
                document.querySelectorAll('.view-content').forEach(view => {
                    view.classList.remove('active');
                });
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
            
            function closeModal(modalId) { 
                document.getElementById(modalId).style.display = 'none'; 
            }

            function openAddTaskModal() { 
                // Set default time to next hour
                const now = new Date();
                const nextHour = new Date(now.getTime() + 60 * 60 * 1000);
                
                document.getElementById('startTime').value = now.toTimeString().slice(0,5);
                document.getElementById('endTime').value = nextHour.toTimeString().slice(0,5);
                
                // Set weekly option to current day
                const daySelect = document.getElementById('repeatDaySelect');
                const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
                const today = days[now.getDay()];
                
                // Find and select today in the dropdown
                for (let i = 0; i < daySelect.options.length; i++) {
                    if (daySelect.options[i].value === today) {
                        daySelect.selectedIndex = i;
                        break;
                    }
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
                        
                        // Set repeat day if weekly
                        if (taskData.repeat === 'weekly' && taskData.repeat_day) {
                            document.getElementById('editRepeatDaySelect').value = taskData.repeat_day;
                            document.getElementById('editRepeatDayGroup').style.display = 'block';
                        }
                        
                        // Set repeat end date
                        if (taskData.repeat_end_date) {
                            const repeatEndDate = new Date(taskData.repeat_end_date);
                            document.getElementById('editTaskRepeatEndDate').value = repeatEndDate.toISOString().split('T')[0];
                            document.getElementById('editRepeatEndDateGroup').style.display = 'block';
                        }
                        
                        // Show/hide repeat options
                        toggleEditRepeatOptions();
                        
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

            function toggleRepeatOptions() {
                const repeatSelect = document.getElementById('repeatSelect');
                const repeatDayGroup = document.getElementById('repeatDayGroup');
                const repeatEndDateGroup = document.getElementById('repeatEndDateGroup');
                
                if (repeatSelect.value === 'weekly') {
                    repeatDayGroup.style.display = 'block';
                    repeatEndDateGroup.style.display = 'block';
                } else if (repeatSelect.value === 'daily') {
                    repeatDayGroup.style.display = 'none';
                    repeatEndDateGroup.style.display = 'block';
                } else {
                    repeatDayGroup.style.display = 'none';
                    repeatEndDateGroup.style.display = 'none';
                }
            }
            
            function toggleEditRepeatOptions() {
                const repeatSelect = document.getElementById('editTaskRepeat');
                const repeatDayGroup = document.getElementById('editRepeatDayGroup');
                const repeatEndDateGroup = document.getElementById('editRepeatEndDateGroup');
                
                if (repeatSelect.value === 'weekly') {
                    repeatDayGroup.style.display = 'block';
                    repeatEndDateGroup.style.display = 'block';
                } else if (repeatSelect.value === 'daily') {
                    repeatDayGroup.style.display = 'none';
                    repeatEndDateGroup.style.display = 'block';
                } else {
                    repeatDayGroup.style.display = 'none';
                    repeatEndDateGroup.style.display = 'none';
                }
            }

            document.addEventListener('DOMContentLoaded', () => {
                const urlParams = new URLSearchParams(window.location.search);
                const viewParam = urlParams.get('view');
                if (viewParam) {
                    // Set active button for current view
                    document.querySelectorAll('.header-action-btn').forEach(btn => {
                        btn.classList.remove('active');
                        if (btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(viewParam)) {
                            btn.classList.add('active');
                        }
                    });
                    
                    // Initialize FAB for current view
                    updateFAB(viewParam);
                } else {
                    // Initialize FAB for default view
                    updateFAB('tasks');
                }
                
                // Initialize repeat options
                toggleRepeatOptions();
                
                // Date validation for add task form
                const startDateInput = document.getElementById('startDate');
                const endDateInput = document.getElementById('endDate');
                const startTimeInput = document.getElementById('startTime');
                const endTimeInput = document.getElementById('endTime');
                
                if (startDateInput && endDateInput) {
                    startDateInput.addEventListener('change', function() {
                        const startDate = new Date(this.value);
                        const endDate = new Date(endDateInput.value);
                        
                        if (endDate < startDate) {
                            endDateInput.value = this.value;
                        }
                    });
                    
                    endDateInput.addEventListener('change', function() {
                        const startDate = new Date(startDateInput.value);
                        const endDate = new Date(this.value);
                        
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
                }
                
                // Handle note notification checkbox
                const noteNotifyCheckbox = document.getElementById('noteNotifyEnabled');
                const noteIntervalGroup = document.getElementById('noteIntervalGroup');
                
                if (noteNotifyCheckbox && noteIntervalGroup) {
                    noteNotifyCheckbox.addEventListener('change', function() {
                        noteIntervalGroup.style.display = this.checked ? 'block' : 'none';
                    });
                }
                
                // Update time display every minute
                function updateTimeDisplay() {
                    const now = new Date();
                    const timeElements = document.querySelectorAll('.time-display');
                    timeElements.forEach(el => {
                        const timeString = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                        el.innerHTML = `<i class="fas fa-clock"></i> ${timeString} IST`;
                    });
                }
                
                updateTimeDisplay();
                setInterval(updateTimeDisplay, 60000);
            });
            
            // Update time badges every minute
            function updateTimeBadges() {
                const now = new Date();
                const currentMinutes = now.getHours() * 60 + now.getMinutes();
                
                document.querySelectorAll('.time-remaining-badge').forEach(badge => {
                    // This would need server-side calculation for accurate times
                    // For now, just update the text based on class
                    if (badge.className.includes('active')) {
                        badge.textContent = 'Active Now';
                    } else if (badge.className.includes('starting_soon')) {
                        badge.textContent = 'Starting Soon';
                    } else if (badge.className.includes('upcoming')) {
                        badge.textContent = 'Upcoming';
                    } else if (badge.className.includes('due')) {
                        badge.textContent = 'Recently Due';
                    } else if (badge.className.includes('overdue')) {
                        badge.textContent = 'Overdue';
                    } else if (badge.className.includes('completed')) {
                        badge.textContent = 'Completed';
                    }
                });
            }
            
            // Update every minute
            setInterval(updateTimeBadges, 60000);
        </script>
    </body>
    </html>
    ''',
    tasks=processed_tasks,
    grouped_history=grouped_history,
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
    history=history,
    format_text=format_text,
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
    repeat_day = request.form.get('repeat_day')
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
    
    # If weekly repeat but no day specified, use current day
    if repeat == 'weekly' and not repeat_day:
        repeat_day = get_ist_time().strftime('%A')
    
    # Insert task
    task_id = db_query(
        """INSERT INTO tasks (title, description, start_time, end_time, notify_enabled, 
           priority, repeat, repeat_day, repeat_end_date, next_occurrence) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, description, start_datetime, end_datetime, notify_enabled, 
         priority, repeat, repeat_day, repeat_end_date, 
         start_datetime if repeat != 'none' else None)
    )
    
    # Send beautiful notification if enabled
    if notify_enabled:
        now = get_ist_time()
        minutes_until = int((start_dt - now).total_seconds() / 60)
        
        # Format times for display
        start_display = start_dt.strftime('%I:%M %p')
        end_display = end_dt.strftime('%I:%M %p')
        
        send_task_added_notification(title, start_display, end_display, minutes_until)
    
    return redirect(url_for('index', view='tasks'))

@app.route('/add_subtask', methods=['POST'])
def add_subtask():
    """Add a subtask"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = request.form.get('task_id')
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    
    if task_id and title:
        # Get current max priority for this task's subtasks
        subtasks = db_query(
            'SELECT priority FROM subtasks WHERE task_id = ? ORDER BY priority DESC LIMIT 1',
            (task_id,), fetch_one=True
        )
        
        priority = 1
        if subtasks and subtasks['priority']:
            priority = subtasks['priority'] + 1
        
        db_query(
            "INSERT INTO subtasks (task_id, title, description, priority) VALUES (?, ?, ?, ?)",
            (task_id, title, description, priority)
        )
    
    return redirect(url_for('index', view='tasks'))

@app.route('/complete_task', methods=['POST'])
def complete_task():
    """Mark task as completed"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = request.form.get('task_id')
    
    if task_id:
        task = db_query("SELECT * FROM tasks WHERE id = ?", (task_id,), fetch_one=True)
        
        if task and not task['completed']:
            # Mark task as completed
            db_query("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
            
            # Get task time range for history
            start_dt = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
            start_dt = IST.localize(start_dt)
            end_dt = datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S')
            end_dt = IST.localize(end_dt)
            time_range = f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}"
            
            # Add to history
            history_id = db_query(
                """INSERT INTO history (task_id, title, description, type, bucket, 
                   repeat, time_range, priority) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, task['title'], task['description'], 'task', task['bucket'], 
                 task['repeat'], time_range, task['priority'])
            )
            
            # Add completed subtasks to history
            subtasks = db_query(
                "SELECT * FROM subtasks WHERE task_id = ? AND completed = 1",
                (task_id,), fetch_all=True
            )
            
            for subtask in subtasks:
                db_query(
                    """INSERT INTO history_subtasks (history_id, title, description, priority) 
                       VALUES (?, ?, ?, ?)""",
                    (history_id, subtask['title'], subtask['description'], subtask['priority'])
                )
            
            # Send beautiful notification
            send_task_completed_notification(
                task['title'],
                len(subtasks),
                db_query("SELECT COUNT(*) as count FROM subtasks WHERE task_id = ?", (task_id,), fetch_one=True)['count']
            )
    
    return redirect(url_for('index', view='tasks'))

@app.route('/complete_subtask', methods=['POST'])
def complete_subtask():
    """Toggle subtask completion"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = request.form.get('task_id')
    subtask_id = request.form.get('subtask_id')
    
    if task_id and subtask_id:
        # Get current completion status
        subtask = db_query(
            "SELECT * FROM subtasks WHERE id = ?",
            (subtask_id,), fetch_one=True
        )
        
        if subtask:
            new_status = 0 if subtask['completed'] else 1
            db_query(
                "UPDATE subtasks SET completed = ? WHERE id = ?",
                (new_status, subtask_id)
            )
            
            # Send beautiful notification if completed
            if new_status == 1:
                task = db_query(
                    "SELECT title FROM tasks WHERE id = ?",
                    (task_id,), fetch_one=True
                )
                
                if task:
                    send_subtask_completed_notification(subtask['title'], task['title'])
    
    return redirect(url_for('index', view='tasks'))

@app.route('/delete_task', methods=['POST'])
def delete_task():
    """Delete a task"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = request.form.get('task_id')
    
    if task_id:
        db_query("DELETE FROM tasks WHERE id = ?", (task_id,))
    
    return redirect(url_for('index', view='tasks'))

@app.route('/delete_subtask', methods=['POST'])
def delete_subtask():
    """Delete a subtask"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = request.form.get('task_id')
    subtask_id = request.form.get('subtask_id')
    
    if subtask_id:
        db_query("DELETE FROM subtasks WHERE id = ?", (subtask_id,))
    
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
        # Get max priority
        notes = db_query(
            "SELECT priority FROM notes ORDER BY priority DESC LIMIT 1",
            fetch_one=True
        )
        
        priority = 1
        if notes and notes['priority']:
            priority = notes['priority'] + 1
        
        db_query(
            """INSERT INTO notes (title, description, priority, notify_enabled, notify_interval) 
               VALUES (?, ?, ?, ?, ?)""",
            (title, description, priority, notify_enabled, notify_interval)
        )
        
        # Send beautiful notification if enabled
        if notify_enabled and notify_interval > 0:
            send_note_added_notification(title, notify_interval)
    
    return redirect(url_for('index', view='notes'))

@app.route('/update_note', methods=['POST'])
def update_note():
    """Update a note"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    note_id = request.form.get('note_id')
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    notify_enabled = 1 if request.form.get('notify_enabled') == 'on' else 0
    notify_interval = int(request.form.get('notify_interval', 12))
    
    if note_id and title:
        db_query(
            """UPDATE notes SET title = ?, description = ?, notify_enabled = ?, 
               notify_interval = ?, updated_at = CURRENT_TIMESTAMP 
               WHERE id = ?""",
            (title, description, notify_enabled, notify_interval, note_id)
        )
    
    return redirect(url_for('index', view='notes'))

@app.route('/delete_note', methods=['POST'])
def delete_note():
    """Delete a note"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    note_id = request.form.get('note_id')
    
    if note_id:
        db_query("DELETE FROM notes WHERE id = ?", (note_id,))
    
    return redirect(url_for('index', view='notes'))

@app.route('/move_note', methods=['POST'])
def move_note():
    """Move note up or down"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    note_id = request.form.get('note_id')
    direction = request.form.get('direction')
    
    if note_id and direction:
        # Get current note
        note = db_query(
            "SELECT id, priority FROM notes WHERE id = ?",
            (note_id,), fetch_one=True
        )
        
        if note:
            current_priority = note['priority']
            
            if direction == 'up':
                # Get note above
                above_note = db_query(
                    "SELECT id, priority FROM notes WHERE priority < ? ORDER BY priority DESC LIMIT 1",
                    (current_priority,), fetch_one=True
                )
                
                if above_note:
                    # Swap priorities
                    db_query("UPDATE notes SET priority = ? WHERE id = ?", 
                            (above_note['priority'], note_id))
                    db_query("UPDATE notes SET priority = ? WHERE id = ?", 
                            (current_priority, above_note['id']))
            
            elif direction == 'down':
                # Get note below
                below_note = db_query(
                    "SELECT id, priority FROM notes WHERE priority > ? ORDER BY priority ASC LIMIT 1",
                    (current_priority,), fetch_one=True
                )
                
                if below_note:
                    # Swap priorities
                    db_query("UPDATE notes SET priority = ? WHERE id = ?", 
                            (below_note['priority'], note_id))
                    db_query("UPDATE notes SET priority = ? WHERE id = ?", 
                            (current_priority, below_note['id']))
    
    return redirect(url_for('index', view='notes'))

@app.route('/update_task', methods=['POST'])
def update_task():
    """Update a task"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = request.form.get('task_id')
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
        
        # If weekly repeat but no day specified, use current day
        if repeat == 'weekly' and not repeat_day:
            repeat_day = get_ist_time().strftime('%A')
        
        db_query(
            """UPDATE tasks SET title = ?, description = ?, start_time = ?, end_time = ?, 
               notify_enabled = ?, priority = ?, repeat = ?, repeat_day = ?, repeat_end_date = ?,
               next_occurrence = ? 
               WHERE id = ?""",
            (title, description, start_datetime, end_datetime, notify_enabled, 
             priority, repeat, repeat_day, repeat_end_date,
             start_datetime if repeat != 'none' else None, task_id)
        )
    
    return redirect(url_for('index', view='tasks'))

@app.route('/update_subtask', methods=['POST'])
def update_subtask():
    """Update a subtask"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    task_id = request.form.get('task_id')
    subtask_id = request.form.get('subtask_id')
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    priority = int(request.form.get('priority', 15))
    
    if subtask_id and title:
        db_query(
            "UPDATE subtasks SET title = ?, description = ?, priority = ? WHERE id = ?",
            (title, description, priority, subtask_id)
        )
    
    return redirect(url_for('index', view='tasks'))

@app.route('/toggle_setting', methods=['POST'])
def toggle_setting():
    """Toggle a setting"""
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    
    key = request.form.get('key')
    enabled = request.form.get('enabled')
    
    if key and enabled is not None:
        value = '1' if enabled == 'on' else '0'
        db_query(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        
        # Send beautiful confirmation
        if key == 'hourly_report':
            if value == '1':
                message = f"📊 <b>HOURLY REPORTS ENABLED</b>\n"
                message += "━" * 30 + "\n"
                message += f"✅ <b>You'll now receive hourly updates!</b>\n"
                message += f"🕐 Every hour at :00 minutes\n"
                message += f"📊 Task progress reports\n"
                message += "━" * 30 + "\n"
                message += f"<i>Stay informed about your tasks!</i>"
            else:
                message = f"📊 <b>HOURLY REPORTS DISABLED</b>\n"
                message += "━" * 30 + "\n"
                message += f"🔕 <b>Hourly reports turned off</b>\n"
                message += f"📱 You can enable them anytime in settings\n"
                message += "━" * 30 + "\n"
                message += f"<i>You'll still get task reminders</i>"
            send_telegram_message(message)
    
    return redirect(url_for('index', view='settings'))

# ============= API ENDPOINTS =============
@app.route('/get_task/<int:task_id>')
def get_task_api(task_id):
    """Get task data for editing"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    task = db_query("SELECT * FROM tasks WHERE id = ?", (task_id,), fetch_one=True)
    if task:
        return jsonify(row_to_dict(task))
    return jsonify({'error': 'Task not found'}), 404

@app.route('/get_note/<int:note_id>')
def get_note_api(note_id):
    """Get note data for editing"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    note = db_query("SELECT * FROM notes WHERE id = ?", (note_id,), fetch_one=True)
    if note:
        return jsonify(row_to_dict(note))
    return jsonify({'error': 'Note not found'}), 404

@app.route('/get_subtask/<int:task_id>/<int:subtask_id>')
def get_subtask_api(task_id, subtask_id):
    """Get subtask data for editing"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    subtask = db_query(
        "SELECT * FROM subtasks WHERE id = ? AND task_id = ?",
        (subtask_id, task_id), fetch_one=True
    )
    if subtask:
        return jsonify(row_to_dict(subtask))
    return jsonify({'error': 'Subtask not found'}), 404

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
    print("🚀 Task Tracker Pro Starting...")
    now = get_ist_time()
    print(f"📅 IST Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🤖 Telegram User ID: {USER_ID}")
    print(f"🔔 Beautiful notifications with emojis and formatting")
    print(f"🌐 Web interface: Same beautiful UI as PHP version")
    print("=" * 60)
    
    # Start Telegram bot in background thread
    bot_thread = threading.Thread(target=start_bot_polling, daemon=True)
    bot_thread.start()
    
    # Start Flask app
    port = int(os.getenv('PORT', 8000))
    print(f"🌐 Web server: http://0.0.0.0:{port}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
