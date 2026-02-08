"""
Task Tracker Telegram Bot with Embedded PHP Web Interface
All-in-one solution with SQLite database
"""

import os
import json
import time
import sqlite3
import threading
import zipfile
import io
from datetime import datetime, timedelta
import telebot
from telebot import types
from flask import Flask, request, jsonify, Response, send_file

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"
MINI_APP_URL = "https://t.me/mini_app_link"  # Replace with your actual Telegram Mini App URL

# Database file
DB_FILE = "task_tracker.db"

# ============= INITIALIZE =============
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# Global variables
monitor_active = True
hourly_notifications = True
app_start_time = datetime.now()

# ============= DATABASE FUNCTIONS =============
def init_database():
    """Initialize SQLite database"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tasks table
    c.execute('''CREATE TABLE IF NOT EXISTS tasks
                 (id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  description TEXT,
                  bucket TEXT,
                  repeat TEXT,
                  repeat_day TEXT,
                  repeat_end_date TEXT,
                  start_time TEXT NOT NULL,
                  end_time TEXT NOT NULL,
                  completed INTEGER DEFAULT 0,
                  created_at TEXT,
                  next_occurrence TEXT,
                  priority INTEGER DEFAULT 15,
                  notify_enabled INTEGER DEFAULT 0,
                  last_notified TEXT)''')
    
    # Subtasks table
    c.execute('''CREATE TABLE IF NOT EXISTS subtasks
                 (id TEXT PRIMARY KEY,
                  task_id TEXT NOT NULL,
                  title TEXT NOT NULL,
                  description TEXT,
                  completed INTEGER DEFAULT 0,
                  priority INTEGER DEFAULT 15,
                  FOREIGN KEY (task_id) REFERENCES tasks (id))''')
    
    # Notes table
    c.execute('''CREATE TABLE IF NOT EXISTS notes
                 (id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  description TEXT,
                  priority INTEGER DEFAULT 1,
                  created_at TEXT,
                  updated_at TEXT,
                  notify_enabled INTEGER DEFAULT 0,
                  notify_interval INTEGER DEFAULT 0,
                  last_notified TEXT)''')
    
    # History table
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  task_id TEXT,
                  title TEXT,
                  description TEXT,
                  type TEXT,
                  bucket TEXT,
                  repeat TEXT,
                  completed_at TEXT,
                  time_range TEXT,
                  priority INTEGER)''')
    
    # Config table
    c.execute('''CREATE TABLE IF NOT EXISTS config
                 (key TEXT PRIMARY KEY,
                  value TEXT)''')
    
    # Initialize config
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('access_code', '1234')")
    c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('hourly_report', '1')")
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def db_execute(query, params=()):
    """Execute SQL query"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def db_fetch_all(query, params=()):
    """Fetch all rows"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

def db_fetch_one(query, params=()):
    """Fetch one row"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(query, params)
    row = c.fetchone()
    conn.close()
    return row

# ============= HELPER FUNCTIONS =============
def log_telegram_notification(message, success=True):
    """Log Telegram notification"""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO history (title, description, type, completed_at) VALUES (?, ?, ?, ?)",
                  ('Telegram Notification', message[:200], 'notification', datetime.now().isoformat()))
        conn.commit()
        conn.close()
    except:
        pass

def send_telegram_message(chat_id, text, reply_markup=None, parse_mode='HTML'):
    """Send message to Telegram"""
    try:
        bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
        log_telegram_notification(text, True)
        return True
    except Exception as e:
        log_telegram_notification(f"Error: {str(e)}", False)
        return False

def create_main_menu_keyboard():
    """Create main menu inline keyboard"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    buttons = [
        types.InlineKeyboardButton("📱 Open Mini App", web_app=types.WebAppInfo(url=MINI_APP_URL)),
        types.InlineKeyboardButton("📊 Stats", callback_data="stats"),
        types.InlineKeyboardButton("🔔 Hourly ON" if hourly_notifications else "🔕 Hourly OFF", 
                                  callback_data="toggle_hourly"),
        types.InlineKeyboardButton("✅ Completed", callback_data="completed_tasks"),
        types.InlineKeyboardButton("📋 All Tasks", callback_data="all_tasks"),
        types.InlineKeyboardButton("⏳ Remaining", callback_data="remaining_tasks"),
        types.InlineKeyboardButton("📝 Notes", callback_data="notes"),
        types.InlineKeyboardButton("💾 Export Data", callback_data="export_data")
    ]
    
    keyboard.add(buttons[0])
    keyboard.add(buttons[1], buttons[2])
    keyboard.add(buttons[3], buttons[4])
    keyboard.add(buttons[5], buttons[6])
    keyboard.add(buttons[7])
    
    return keyboard

def create_back_to_menu_keyboard():
    """Create back to menu keyboard"""
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu"))
    return keyboard

def get_bot_stats():
    """Get bot statistics"""
    total_tasks = db_fetch_one("SELECT COUNT(*) FROM tasks")[0]
    completed_tasks = db_fetch_one("SELECT COUNT(*) FROM tasks WHERE completed = 1")[0]
    tasks_with_notify = db_fetch_one("SELECT COUNT(*) FROM tasks WHERE notify_enabled = 1")[0]
    
    total_notes = db_fetch_one("SELECT COUNT(*) FROM notes")[0]
    notes_with_notify = db_fetch_one("SELECT COUNT(*) FROM notes WHERE notify_enabled = 1")[0]
    
    return {
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'remaining_tasks': total_tasks - completed_tasks,
        'tasks_with_notifications': tasks_with_notify,
        'total_notes': total_notes,
        'notes_with_notifications': notes_with_notify,
        'hourly_notifications': hourly_notifications,
        'uptime': str(datetime.now() - app_start_time).split('.')[0]
    }

def export_database_zip():
    """Export database as ZIP file"""
    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Add database file
        if os.path.exists(DB_FILE):
            zip_file.write(DB_FILE, 'task_tracker.db')
        
        # Add tables as JSON
        conn = get_db_connection()
        tables = ['tasks', 'subtasks', 'notes', 'history', 'config']
        
        for table in tables:
            rows = db_fetch_all(f"SELECT * FROM {table}")
            if rows:
                data = [dict(row) for row in rows]
                json_data = json.dumps(data, indent=2, default=str)
                zip_file.writestr(f'{table}.json', json_data)
        
        conn.close()
        
        # Add metadata
        metadata = {
            'export_time': datetime.now().isoformat(),
            'total_tasks': db_fetch_one("SELECT COUNT(*) FROM tasks")[0],
            'total_notes': db_fetch_one("SELECT COUNT(*) FROM notes")[0],
            'app_version': '1.0',
            'user_id': USER_ID
        }
        zip_file.writestr('metadata.json', json.dumps(metadata, indent=2))
    
    zip_buffer.seek(0)
    return zip_buffer

# ============= MONITORING FUNCTIONS =============
def check_task_reminders():
    """Check and send task reminders"""
    try:
        tasks = db_fetch_all("SELECT * FROM tasks WHERE completed = 0 AND notify_enabled = 1")
        
        current_time = datetime.now()
        
        for task in tasks:
            task_dict = dict(task)
            start_time_str = task_dict['start_time']
            last_notified = task_dict['last_notified']
            
            if not start_time_str:
                continue
            
            try:
                start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
            except:
                continue
            
            # Calculate time difference in minutes
            time_diff = (start_time - current_time).total_seconds() / 60
            
            # Send 10 reminders in the 10 minutes before task starts
            if 0 < time_diff <= 10:
                reminder_minutes = int(time_diff)
                
                if reminder_minutes in range(1, 11):
                    # Check if we already sent this reminder
                    if last_notified:
                        try:
                            last_time = datetime.strptime(last_notified, '%Y-%m-%d %H:%M:%S')
                            minutes_since_last = (current_time - last_time).total_seconds() / 60
                            if minutes_since_last < 1:
                                continue
                        except:
                            pass
                    
                    # Send reminder
                    message = f"⏰ <b>Task Reminder</b>\n"
                    message += f"📝 <b>{task_dict['title']}</b>\n"
                    message += f"🕐 Starts in {reminder_minutes} minute{'s' if reminder_minutes > 1 else ''}\n"
                    message += f"📅 {start_time.strftime('%I:%M %p')}\n"
                    
                    if send_telegram_message(USER_ID, message):
                        # Update last_notified time
                        db_execute("UPDATE tasks SET last_notified = ? WHERE id = ?",
                                  (current_time.strftime('%Y-%m-%d %H:%M:%S'), task_dict['id']))
            
    except Exception as e:
        print(f"Error checking task reminders: {e}")

def check_note_reminders():
    """Check and send note reminders"""
    try:
        notes = db_fetch_all("SELECT * FROM notes WHERE notify_enabled = 1")
        
        current_time = datetime.now()
        
        for note in notes:
            note_dict = dict(note)
            interval_hours = note_dict['notify_interval']
            last_notified = note_dict['last_notified']
            
            if interval_hours <= 0:
                continue
            
            # Check if it's time to send reminder
            if last_notified:
                try:
                    last_time = datetime.strptime(last_notified, '%Y-%m-%d %H:%M:%S')
                    hours_since_last = (current_time - last_time).total_seconds() / 3600
                    
                    if hours_since_last < interval_hours:
                        continue
                except:
                    pass
            
            # Send note reminder
            message = f"📝 <b>Note Reminder</b>\n"
            message += f"📌 <b>{note_dict['title']}</b>\n"
            message += f"🕐 Interval: Every {interval_hours} hours\n"
            message += f"⏰ {current_time.strftime('%I:%M %p')}\n"
            
            description = note_dict.get('description', '')
            if description:
                if len(description) > 200:
                    description = description[:200] + '...'
                message += f"\n{description}"
            
            if send_telegram_message(USER_ID, message):
                # Update last_notified time
                db_execute("UPDATE notes SET last_notified = ? WHERE id = ?",
                          (current_time.strftime('%Y-%m-%d %H:%M:%S'), note_dict['id']))
            
    except Exception as e:
        print(f"Error checking note reminders: {e}")

def send_hourly_report():
    """Send hourly task status report"""
    global hourly_notifications
    
    if not hourly_notifications:
        return
    
    try:
        current_time = datetime.now()
        current_date = current_time.date()
        
        # Get today's tasks
        tasks = db_fetch_all("""
            SELECT * FROM tasks 
            WHERE DATE(start_time) = DATE(?) 
            OR (repeat != 'none' AND completed = 0)
        """, (current_time.strftime('%Y-%m-%d'),))
        
        if not tasks:
            message = f"📊 <b>Hourly Task Report</b>\n"
            message += f"🕐 {current_time.strftime('%I:%M %p')}\n"
            message += f"📅 {current_time.strftime('%B %d, %Y')}\n"
            message += f"✅ No tasks for today!"
        else:
            completed_tasks = [t for t in tasks if t['completed'] == 1]
            pending_tasks = [t for t in tasks if t['completed'] == 0]
            
            message = f"📊 <b>Hourly Task Report</b>\n"
            message += f"🕐 {current_time.strftime('%I:%M %p')}\n"
            message += f"📅 {current_time.strftime('%B %d, %Y')}\n"
            message += f"📋 Total: {len(tasks)} tasks\n\n"
            
            message += f"✅ <b>Completed ({len(completed_tasks)})</b>\n"
            for task in completed_tasks[:3]:
                title = task['title']
                if len(title) > 30:
                    title = title[:27] + '...'
                notify = "🔔" if task['notify_enabled'] else ""
                message += f"   ✓ {title} {notify}\n"
            
            if len(completed_tasks) > 3:
                message += f"   ... and {len(completed_tasks) - 3} more\n"
            
            message += f"\n⏳ <b>Pending ({len(pending_tasks)})</b>\n"
            for task in pending_tasks[:3]:
                title = task['title']
                if len(title) > 30:
                    title = title[:27] + '...'
                
                try:
                    start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
                    time_str = start_time.strftime('%I:%M %p')
                    notify = "🔔" if task['notify_enabled'] else ""
                    message += f"   • {title} ({time_str}) {notify}\n"
                except:
                    notify = "🔔" if task['notify_enabled'] else ""
                    message += f"   • {title} {notify}\n"
            
            if len(pending_tasks) > 3:
                message += f"   ... and {len(pending_tasks) - 3} more\n"
        
        send_telegram_message(USER_ID, message)
        
    except Exception as e:
        print(f"Error sending hourly report: {e}")

def monitoring_loop():
    """Main monitoring loop"""
    global monitor_active
    
    last_hourly_report = datetime.now()
    last_minute_check = datetime.now()
    
    while monitor_active:
        try:
            current_time = datetime.now()
            
            # Check task reminders every minute
            if (current_time - last_minute_check).total_seconds() >= 60:
                check_task_reminders()
                check_note_reminders()
                last_minute_check = current_time
            
            # Send hourly report
            if (current_time - last_hourly_report).total_seconds() >= 3600:
                send_hourly_report()
                last_hourly_report = current_time
            
            time.sleep(10)
            
        except Exception as e:
            print(f"Monitoring error: {e}")
            time.sleep(30)

# ============= TELEGRAM COMMAND HANDLERS =============
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Send welcome message with inline keyboard"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    welcome_msg = """
🤖 <b>Welcome to Task Tracker Bot!</b>

I help you manage your tasks and notes with:
• Task reminders (10 minutes before start)
• Note reminders (custom intervals)
• Hourly status reports
• Web interface for full management

<b>User ID:</b> 8469993808
<b>Status:</b> ✅ Active
"""
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("ℹ️ Basic Info", callback_data="basic_info"),
        types.InlineKeyboardButton("🌐 Web Interface", url=f"http://{request.host}/"),
        types.InlineKeyboardButton("📋 Main Menu", callback_data="main_menu")
    )
    
    send_telegram_message(message.chat.id, welcome_msg, keyboard)

@bot.message_handler(commands=['menu'])
def show_main_menu(message):
    """Show main menu"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    menu_msg = "📱 <b>Main Menu</b>\n\nChoose an option below:"
    keyboard = create_main_menu_keyboard()
    send_telegram_message(message.chat.id, menu_msg, keyboard)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """Handle all callback queries"""
    if str(call.message.chat.id) != USER_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized access")
        return
    
    try:
        if call.data == "main_menu":
            menu_msg = "📱 <b>Main Menu</b>\n\nChoose an option below:"
            keyboard = create_main_menu_keyboard()
            bot.edit_message_text(
                menu_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "basic_info":
            stats = get_bot_stats()
            info_msg = f"""
ℹ️ <b>Basic Information</b>

• <b>User ID:</b> {USER_ID}
• <b>Bot Status:</b> ✅ Active
• <b>Web Interface:</b> http://{request.host}/
• <b>Started:</b> {app_start_time.strftime('%Y-%m-%d %H:%M:%S')}
• <b>Uptime:</b> {stats['uptime']}
• <b>Tasks:</b> {stats['total_tasks']} total, {stats['completed_tasks']} completed
• <b>Notes:</b> {stats['total_notes']} total
"""
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                info_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "stats":
            stats = get_bot_stats()
            stats_msg = f"""
📊 <b>Bot Statistics</b>

📋 <b>Tasks:</b>
   • Total: {stats['total_tasks']}
   • Completed: {stats['completed_tasks']}
   • Remaining: {stats['remaining_tasks']}
   • With Notifications: {stats['tasks_with_notifications']}

📝 <b>Notes:</b>
   • Total: {stats['total_notes']}
   • With Notifications: {stats['notes_with_notifications']}

🔔 <b>Notifications:</b>
   • Hourly Reports: {'✅ ON' if stats['hourly_notifications'] else '❌ OFF'}

⏰ <b>System:</b>
   • Uptime: {stats['uptime']}
   • Last Check: {datetime.now().strftime('%H:%M:%S')}
"""
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                stats_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "toggle_hourly":
            global hourly_notifications
            hourly_notifications = not hourly_notifications
            
            # Save to database
            db_execute("UPDATE config SET value = ? WHERE key = 'hourly_report'",
                      ('1' if hourly_notifications else '0',))
            
            status_msg = f"""
🔔 <b>Hourly Notifications</b>

Status: {'✅ TURNED ON' if hourly_notifications else '❌ TURNED OFF'}

Hourly task reports will {'now be sent' if hourly_notifications else 'no longer be sent'} every hour.
"""
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                status_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            bot.answer_callback_query(call.id, f"Hourly reports {'enabled' if hourly_notifications else 'disabled'}")
        
        elif call.data == "completed_tasks":
            tasks = db_fetch_all("SELECT * FROM tasks WHERE completed = 1 ORDER BY created_at DESC LIMIT 10")
            
            if not tasks:
                message_text = "✅ <b>Completed Tasks</b>\n\nNo completed tasks found."
            else:
                message_text = f"✅ <b>Completed Tasks</b>\n\nTotal: {len(tasks)} tasks\n\n"
                for i, task in enumerate(tasks, 1):
                    title = task['title']
                    if len(title) > 40:
                        title = title[:37] + '...'
                    
                    notify_icon = "🔔" if task['notify_enabled'] else ""
                    message_text += f"{i}. {title} {notify_icon}\n"
            
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "all_tasks":
            tasks = db_fetch_all("SELECT * FROM tasks ORDER BY created_at DESC LIMIT 10")
            
            if not tasks:
                message_text = "📋 <b>All Tasks</b>\n\nNo tasks found."
            else:
                message_text = f"📋 <b>All Tasks</b>\n\nTotal: {len(tasks)} tasks\n\n"
                for i, task in enumerate(tasks, 1):
                    title = task['title']
                    if len(title) > 40:
                        title = title[:37] + '...'
                    
                    completed = task['completed']
                    notify_icon = "🔔" if task['notify_enabled'] else ""
                    status_icon = "✅" if completed else "⏳"
                    
                    message_text += f"{i}. {status_icon} {title} {notify_icon}\n"
            
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "remaining_tasks":
            tasks = db_fetch_all("SELECT * FROM tasks WHERE completed = 0 ORDER BY start_time LIMIT 10")
            
            if not tasks:
                message_text = "⏳ <b>Remaining Tasks</b>\n\nNo remaining tasks. Great job!"
            else:
                message_text = f"⏳ <b>Remaining Tasks</b>\n\nTotal: {len(tasks)} tasks\n\n"
                for i, task in enumerate(tasks, 1):
                    title = task['title']
                    if len(title) > 40:
                        title = title[:37] + '...'
                    
                    notify_icon = "🔔" if task['notify_enabled'] else ""
                    
                    # Show time
                    time_str = ""
                    start_time = task['start_time']
                    if start_time:
                        try:
                            start_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
                            time_str = start_dt.strftime('%I:%M %p')
                        except:
                            pass
                    
                    if time_str:
                        message_text += f"{i}. {title} ({time_str}) {notify_icon}\n"
                    else:
                        message_text += f"{i}. {title} {notify_icon}\n"
            
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "notes":
            notes = db_fetch_all("SELECT * FROM notes ORDER BY created_at DESC LIMIT 10")
            
            if not notes:
                message_text = "📝 <b>Notes</b>\n\nNo notes found."
            else:
                message_text = f"📝 <b>Notes</b>\n\nTotal: {len(notes)} notes\n\n"
                for i, note in enumerate(notes, 1):
                    title = note['title']
                    if len(title) > 40:
                        title = title[:37] + '...'
                    
                    notify_icon = "🔔" if note['notify_enabled'] else ""
                    message_text += f"{i}. {title} {notify_icon}\n"
            
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "export_data":
            # Send preparing message
            bot.answer_callback_query(call.id, "📦 Preparing data export...")
            
            # Create ZIP file
            zip_buffer = export_database_zip()
            
            # Send as document
            try:
                bot.send_document(
                    USER_ID,
                    zip_buffer.getvalue(),
                    visible_file_name=f'task_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip',
                    caption="📦 <b>Database Export</b>\n\nAll your tasks and notes data in ZIP format."
                )
                bot.answer_callback_query(call.id, "✅ Data sent successfully!")
            except Exception as e:
                bot.answer_callback_query(call.id, f"❌ Error: {str(e)}")
        
        else:
            bot.answer_callback_query(call.id, "Unknown command")
    
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle other messages"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    if message.text.lower() in ['menu', 'main menu', 'show menu']:
        show_main_menu(message)
    else:
        response = "Send /start to see the main menu or /menu to open the menu directly."
        send_telegram_message(message.chat.id, response, parse_mode=None)

# ============= EMBEDDED PHP WEB INTERFACE =============
@app.route('/')
def php_interface():
    """Serve the PHP-like web interface"""
    # Check if user is logged in via session
    session_data = request.cookies.get('task_tracker_session')
    is_logged_in = False
    
    if session_data:
        # Simple session validation (in production use proper sessions)
        try:
            session_info = json.loads(session_data)
            is_logged_in = session_info.get('authenticated', False)
        except:
            pass
    
    # Handle POST requests
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        if action == 'login':
            access_code = request.form.get('access_code', '')
            config = db_fetch_one("SELECT value FROM config WHERE key = 'access_code'")
            
            if config and access_code == config[0]:
                # Set session cookie
                session_info = {'authenticated': True, 'user': USER_ID}
                response = app.make_response(php_home_page())
                response.set_cookie('task_tracker_session', json.dumps(session_info), max_age=86400)
                return response
            else:
                return php_login_page("Invalid access code")
        
        elif action == 'logout':
            response = app.make_response(php_login_page("Logged out successfully"))
            response.set_cookie('task_tracker_session', '', expires=0)
            return response
        
        elif action == 'add_task':
            if not is_logged_in:
                return php_login_page("Please login first")
            
            # Add task logic here
            title = request.form.get('title', '')
            description = request.form.get('description', '')
            start_date = request.form.get('start_date', datetime.now().strftime('%Y-%m-%d'))
            start_time = request.form.get('start_time', datetime.now().strftime('%H:%M'))
            
            task_id = f"task_{int(time.time())}_{os.urandom(4).hex()}"
            
            db_execute("""
                INSERT INTO tasks (id, title, description, start_time, end_time, created_at, priority, notify_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, title, description, 
                f"{start_date} {start_time}:00",
                f"{start_date} {start_time}:00",
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                15, 0
            ))
            
            return php_home_page()
        
        elif action == 'toggle_notify':
            task_id = request.form.get('task_id', '')
            if task_id:
                current = db_fetch_one("SELECT notify_enabled FROM tasks WHERE id = ?", (task_id,))
                if current:
                    new_value = 0 if current[0] else 1
                    db_execute("UPDATE tasks SET notify_enabled = ? WHERE id = ?", (new_value, task_id))
            
            return php_home_page()
        
        elif action == 'complete_task':
            task_id = request.form.get('task_id', '')
            if task_id:
                db_execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
            
            return php_home_page()
        
        elif action == 'delete_task':
            task_id = request.form.get('task_id', '')
            if task_id:
                db_execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                db_execute("DELETE FROM subtasks WHERE task_id = ?", (task_id,))
            
            return php_home_page()
        
        elif action == 'export_data':
            if not is_logged_in:
                return php_login_page("Please login first")
            
            # Create and send ZIP
            zip_buffer = export_database_zip()
            
            response = send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'task_export_{datetime.now().strftime("%Y%m%d")}.zip'
            )
            return response
    
    # GET requests
    if not is_logged_in:
        return php_login_page()
    
    return php_home_page()

def php_login_page(error_message=""):
    """Generate login page"""
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Task Tracker - Login</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{
            --primary: #4361ee;
            --primary-light: #4895ef;
            --danger: #f72585;
            --light: #f8f9fa;
            --dark: #212529;
            --border-radius: 12px;
            --shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        
        .login-container {{
            background: white;
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            width: 100%;
            max-width: 400px;
            overflow: hidden;
        }}
        
        .login-header {{
            background: var(--primary);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .login-header h1 {{
            font-size: 1.8rem;
            margin-bottom: 5px;
        }}
        
        .login-body {{
            padding: 30px;
        }}
        
        .form-group {{ margin-bottom: 20px; }}
        
        .form-label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--dark);
        }}
        
        .form-input {{
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 16px;
        }}
        
        .form-input:focus {{
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }}
        
        .btn {{
            width: 100%;
            padding: 14px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.3s;
        }}
        
        .btn:hover {{ background: var(--primary-light); }}
        
        .error-message {{
            background: rgba(247, 37, 133, 0.1);
            color: var(--danger);
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 20px;
            text-align: center;
            border: 1px solid rgba(247, 37, 133, 0.2);
        }}
        
        .success-message {{
            background: rgba(72, 149, 239, 0.1);
            color: var(--primary);
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 20px;
            text-align: center;
            border: 1px solid rgba(72, 149, 239, 0.2);
        }}
        
        .telegram-link {{
            text-align: center;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }}
        
        .telegram-link a {{
            color: var(--primary);
            text-decoration: none;
            font-weight: 500;
        }}
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h1><i class="fas fa-tasks"></i> Task Tracker</h1>
            <p>Web Interface</p>
        </div>
        
        <div class="login-body">
            {'<div class="error-message">' + error_message + '</div>' if error_message and 'Invalid' in error_message else ''}
            {'<div class="success-message">' + error_message + '</div>' if error_message and 'Logged' in error_message else ''}
            
            <form method="POST" action="/">
                <input type="hidden" name="action" value="login">
                
                <div class="form-group">
                    <label class="form-label">Access Code</label>
                    <input type="password" class="form-input" name="access_code" required 
                           placeholder="Enter access code" autocomplete="off">
                </div>
                
                <button type="submit" class="btn">
                    <i class="fas fa-sign-in-alt"></i> Access System
                </button>
            </form>
            
            <div class="telegram-link">
                <p>Also available on Telegram: @TaskTrackerBot</p>
            </div>
        </div>
    </div>
</body>
</html>
"""

def php_home_page():
    """Generate main home page"""
    # Get tasks and notes
    tasks = db_fetch_all("SELECT * FROM tasks ORDER BY start_time")
    notes = db_fetch_all("SELECT * FROM notes ORDER BY created_at DESC")
    stats = get_bot_stats()
    
    tasks_html = ""
    for task in tasks:
        task_dict = dict(task)
        task_id = task_dict['id']
        title = task_dict['title']
        description = task_dict['description'] or ""
        start_time = task_dict['start_time']
        completed = task_dict['completed']
        notify_enabled = task_dict['notify_enabled']
        
        # Format time
        time_str = ""
        try:
            dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            time_str = dt.strftime('%I:%M %p')
        except:
            time_str = start_time
        
        # Get subtasks
        subtasks = db_fetch_all("SELECT * FROM subtasks WHERE task_id = ? ORDER BY priority", (task_id,))
        completed_subtasks = sum(1 for st in subtasks if st['completed'])
        total_subtasks = len(subtasks)
        
        tasks_html += f"""
        <div class="task-card">
            <div class="task-header">
                <div class="task-title-row">
                    <h3 class="task-title {'completed' if completed else ''}">{title}</h3>
                    <div class="task-actions">
                        <form method="POST" action="/" style="display: inline;">
                            <input type="hidden" name="action" value="toggle_notify">
                            <input type="hidden" name="task_id" value="{task_id}">
                            <button type="submit" class="action-btn {'active' if notify_enabled else ''}" 
                                    title="{'Disable' if notify_enabled else 'Enable'} notifications">
                                <i class="fas fa-bell"></i>
                            </button>
                        </form>
                        
                        <form method="POST" action="/" style="display: inline;">
                            <input type="hidden" name="action" value="complete_task">
                            <input type="hidden" name="task_id" value="{task_id}">
                            <button type="submit" class="action-btn {'completed' if completed else ''}" 
                                    title="{'Completed' if completed else 'Mark complete'}">
                                <i class="fas fa-check"></i>
                            </button>
                        </form>
                        
                        <form method="POST" action="/" style="display: inline;">
                            <input type="hidden" name="action" value="delete_task">
                            <input type="hidden" name="task_id" value="{task_id}">
                            <button type="submit" class="action-btn delete" title="Delete">
                                <i class="fas fa-trash"></i>
                            </button>
                        </form>
                    </div>
                </div>
                
                <div class="task-meta">
                    <span class="task-time">{time_str}</span>
                    {'<span class="task-notify"><i class="fas fa-bell"></i> Notify</span>' if notify_enabled else ''}
                </div>
            </div>
            
            {f'<p class="task-description">{description[:100]}{"..." if len(description) > 100 else ""}</p>' if description else ''}
            
            {f'<div class="subtasks"><i class="fas fa-tasks"></i> {completed_subtasks}/{total_subtasks} subtasks</div>' if total_subtasks > 0 else ''}
        </div>
        """
    
    notes_html = ""
    for note in notes:
        note_dict = dict(note)
        title = note_dict['title']
        description = note_dict['description'] or ""
        notify_enabled = note_dict['notify_enabled']
        notify_interval = note_dict['notify_interval']
        
        notes_html += f"""
        <div class="note-card">
            <h4>{title}</h4>
            {f'<p>{description[:100]}{"..." if len(description) > 100 else ""}</p>' if description else ''}
            {'<div class="note-notify"><i class="fas fa-bell"></i> Every ' + str(notify_interval) + 'h</div>' if notify_enabled else ''}
        </div>
        """
    
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Task Tracker</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{
            --primary: #4361ee;
            --primary-light: #4895ef;
            --danger: #f72585;
            --success: #4cc9f0;
            --light: #f8f9fa;
            --dark: #212529;
            --gray: #6c757d;
            --border-radius: 12px;
            --shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            --card-bg: rgba(255, 182, 193, 0.1);
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: var(--light);
            color: var(--dark);
            min-height: 100vh;
        }}
        
        .header {{
            background: white;
            padding: 15px 20px;
            box-shadow: var(--shadow);
            position: sticky;
            top: 0;
            z-index: 100;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .logo {{ font-size: 1.5rem; font-weight: 700; color: var(--primary); }}
        
        .nav-buttons {{
            display: flex;
            gap: 10px;
        }}
        
        .nav-btn {{
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 20px;
            padding: 8px 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 500;
            text-decoration: none;
        }}
        
        .nav-btn:hover {{ background: var(--primary-light); }}
        
        .nav-btn.logout {{ background: var(--danger); }}
        .nav-btn.logout:hover {{ background: #e1156f; }}
        
        .main-content {{
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: white;
            border-radius: var(--border-radius);
            padding: 20px;
            box-shadow: var(--shadow);
            text-align: center;
        }}
        
        .stat-value {{
            font-size: 2rem;
            font-weight: bold;
            color: var(--primary);
            margin: 10px 0;
        }}
        
        .section {{
            margin-bottom: 30px;
        }}
        
        .section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--primary-light);
        }}
        
        .section-title {{
            font-size: 1.3rem;
            color: var(--dark);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .add-btn {{
            background: var(--success);
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .tasks-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 15px;
        }}
        
        .task-card {{
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 15px;
            box-shadow: var(--shadow);
        }}
        
        .task-header {{
            margin-bottom: 10px;
        }}
        
        .task-title-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 5px;
        }}
        
        .task-title {{
            font-size: 1.1rem;
            font-weight: 600;
            flex: 1;
        }}
        
        .task-title.completed {{
            text-decoration: line-through;
            color: var(--gray);
        }}
        
        .task-actions {{
            display: flex;
            gap: 5px;
        }}
        
        .action-btn {{
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }}
        
        .action-btn.active {{ background: #f8961e; }}
        .action-btn.completed {{ background: var(--success); }}
        .action-btn.delete {{ background: var(--danger); }}
        
        .task-meta {{
            display: flex;
            gap: 10px;
            font-size: 0.85rem;
            color: var(--gray);
        }}
        
        .task-notify {{
            background: rgba(248, 150, 30, 0.1);
            color: #f8961e;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.75rem;
        }}
        
        .task-description {{
            font-size: 0.9rem;
            color: var(--gray);
            margin: 10px 0;
            line-height: 1.4;
        }}
        
        .subtasks {{
            font-size: 0.8rem;
            color: var(--gray);
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid rgba(0,0,0,0.1);
        }}
        
        .notes-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 15px;
        }}
        
        .note-card {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: var(--border-radius);
            padding: 15px;
            box-shadow: var(--shadow);
        }}
        
        .note-card h4 {{
            margin-bottom: 8px;
            color: var(--dark);
        }}
        
        .note-card p {{
            font-size: 0.9rem;
            color: var(--gray);
            line-height: 1.4;
        }}
        
        .note-notify {{
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 0.75rem;
            display: inline-block;
            margin-top: 10px;
        }}
        
        .empty-state {{
            text-align: center;
            padding: 40px 20px;
            color: var(--gray);
        }}
        
        .empty-state i {{
            font-size: 3rem;
            margin-bottom: 15px;
            opacity: 0.5;
        }}
        
        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }}
        
        .modal-content {{
            background: white;
            border-radius: var(--border-radius);
            width: 90%;
            max-width: 500px;
            padding: 20px;
        }}
        
        @media (max-width: 768px) {{
            .tasks-grid, .notes-grid {{
                grid-template-columns: 1fr;
            }}
            
            .stats-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
            
            .nav-buttons {{
                flex-wrap: wrap;
                justify-content: flex-end;
            }}
            
            .nav-btn span {{
                display: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">
            <i class="fas fa-tasks"></i> Task Tracker
        </div>
        
        <div class="nav-buttons">
            <a href="https://t.me/TaskTrackerBot" class="nav-btn" target="_blank">
                <i class="fab fa-telegram"></i>
                <span>Telegram</span>
            </a>
            
            <form method="POST" action="/" style="display: inline;">
                <input type="hidden" name="action" value="export_data">
                <button type="submit" class="nav-btn">
                    <i class="fas fa-download"></i>
                    <span>Export Data</span>
                </button>
            </form>
            
            <form method="POST" action="/">
                <input type="hidden" name="action" value="logout">
                <button type="submit" class="nav-btn logout">
                    <i class="fas fa-sign-out-alt"></i>
                    <span>Logout</span>
                </button>
            </form>
        </div>
    </div>
    
    <div class="main-content">
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Tasks</h3>
                <div class="stat-value">{stats['total_tasks']}</div>
                <p>{stats['completed_tasks']} completed</p>
            </div>
            
            <div class="stat-card">
                <h3>Remaining Tasks</h3>
                <div class="stat-value">{stats['remaining_tasks']}</div>
                <p>{stats['tasks_with_notifications']} with notifications</p>
            </div>
            
            <div class="stat-card">
                <h3>Total Notes</h3>
                <div class="stat-value">{stats['total_notes']}</div>
                <p>{stats['notes_with_notifications']} with notifications</p>
            </div>
            
            <div class="stat-card">
                <h3>Hourly Reports</h3>
                <div class="stat-value">{'ON' if hourly_notifications else 'OFF'}</div>
                <p>Control via Telegram</p>
            </div>
        </div>
        
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">
                    <i class="fas fa-tasks"></i>
                    Tasks ({stats['total_tasks']})
                </h2>
                <button class="add-btn" onclick="openAddTaskModal()">
                    <i class="fas fa-plus"></i>
                    Add Task
                </button>
            </div>
            
            <div class="tasks-grid">
                {tasks_html if tasks_html else '''
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <i class="fas fa-clipboard-list"></i>
                    <p>No tasks yet. Add your first task!</p>
                </div>'''}
            </div>
        </div>
        
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">
                    <i class="fas fa-sticky-note"></i>
                    Notes ({stats['total_notes']})
                </h2>
                <button class="add-btn" onclick="openAddNoteModal()">
                    <i class="fas fa-plus"></i>
                    Add Note
                </button>
            </div>
            
            <div class="notes-grid">
                {notes_html if notes_html else '''
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <i class="fas fa-sticky-note"></i>
                    <p>No notes yet. Add your first note!</p>
                </div>'''}
            </div>
        </div>
    </div>
    
    <!-- Add Task Modal -->
    <div class="modal" id="addTaskModal">
        <div class="modal-content">
            <h3>Add New Task</h3>
            <form method="POST" action="/" style="margin-top: 20px;">
                <input type="hidden" name="action" value="add_task">
                
                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: 600;">Title</label>
                    <input type="text" name="title" required 
                           style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px;">
                </div>
                
                <div style="margin-bottom: 15px;">
                    <label style="display: block; margin-bottom: 5px; font-weight: 600;">Description</label>
                    <textarea name="description" rows="3"
                              style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px;"></textarea>
                </div>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;">
                    <div>
                        <label style="display: block; margin-bottom: 5px; font-weight: 600;">Date</label>
                        <input type="date" name="start_date" value="{datetime.now().strftime('%Y-%m-%d')}"
                               style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px;">
                    </div>
                    
                    <div>
                        <label style="display: block; margin-bottom: 5px; font-weight: 600;">Time</label>
                        <input type="time" name="start_time" value="{datetime.now().strftime('%H:%M')}"
                               style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px;">
                    </div>
                </div>
                
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button type="button" onclick="closeModal('addTaskModal')"
                            style="padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 6px; cursor: pointer; flex: 1;">
                        Cancel
                    </button>
                    <button type="submit"
                            style="padding: 10px 20px; background: var(--primary); color: white; border: none; border-radius: 6px; cursor: pointer; flex: 1;">
                        Add Task
                    </button>
                </div>
            </form>
        </div>
    </div>
    
    <script>
        function openAddTaskModal() {{
            document.getElementById('addTaskModal').style.display = 'flex';
        }}
        
        function closeModal(modalId) {{
            document.getElementById(modalId).style.display = 'none';
        }}
        
        // Close modal when clicking outside
        window.addEventListener('click', function(event) {{
            const modals = document.querySelectorAll('.modal');
            modals.forEach(modal => {{
                if (event.target === modal) {{
                    modal.style.display = 'none';
                }}
            }});
        }});
    </script>
</body>
</html>
"""

# ============= INITIALIZATION =============
def initialize():
    """Initialize the bot"""
    print("=" * 60)
    print("🤖 Task Tracker Bot - Initializing")
    print("=" * 60)
    
    try:
        # Initialize database
        init_database()
        print("✅ Database initialized")
        
        # Get bot info
        bot_info = bot.get_me()
        print(f"✅ Bot: @{bot_info.username} (ID: {bot_info.id})")
        
        # Load hourly notifications setting
        config = db_fetch_one("SELECT value FROM config WHERE key = 'hourly_report'")
        global hourly_notifications
        if config:
            hourly_notifications = config[0] == '1'
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()
        print("✅ Monitoring thread started")
        
        # Send startup message
        startup_msg = f"""
🚀 <b>Task Tracker Bot Started</b>

✅ <b>Bot is online!</b>
🤖 @{bot_info.username}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

<b>Features:</b>
• Task reminders (10 minutes before start)
• Note reminders (custom intervals)
• Hourly status reports
• Web interface for management

Send /start to begin!
"""
        send_telegram_message(USER_ID, startup_msg)
        print("✅ Startup message sent")
        
    except Exception as e:
        print(f"❌ Initialization error: {e}")
    
    print("=" * 60)
    print("✅ Bot initialized successfully")
    print("=" * 60)

# ============= MAIN =============
if __name__ == '__main__':
    # Initialize bot
    initialize()
    
    # Start Flask app
    port = int(os.getenv('PORT', 8000))
    print(f"🌐 Starting web server on port {port}...")
    
    # Use polling for Telegram updates
    try:
        polling_thread = threading.Thread(target=bot.polling, kwargs={'none_stop': True, 'interval': 1}, daemon=True)
        polling_thread.start()
        print("✅ Telegram polling started")
    except Exception as e:
        print(f"⚠️ Could not start polling: {e}")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
else:
    # For production deployment
    initialize()
