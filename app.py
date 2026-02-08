
"""
Task Tracker with Telegram Notifications
Combines PHP functionality with Python monitoring and SQLite database
"""

import os
import json
import time
import sqlite3
import threading
from datetime import datetime, timedelta
import telebot
from flask import Flask, request, Response
import re

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"

# Initialize Flask app
app = Flask(__name__)

# Initialize Telegram bot
bot = telebot.TeleBot(BOT_TOKEN)

# Initialize SQLite database
def init_db():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect('task_tracker.db')
    cursor = conn.cursor()
    
    # Tasks table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT,
        bucket TEXT DEFAULT 'today',
        repeat TEXT DEFAULT 'none',
        repeat_day TEXT,
        repeat_end_date TEXT,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        completed INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        next_occurrence TEXT,
        priority INTEGER DEFAULT 15,
        notify_enabled INTEGER DEFAULT 1,
        last_notified TEXT
    )
    ''')
    
    # Subtasks table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subtasks (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        completed INTEGER DEFAULT 0,
        priority INTEGER DEFAULT 1,
        FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
    )
    ''')
    
    # Notes table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notes (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT,
        priority INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        notify_enabled INTEGER DEFAULT 0,
        notify_interval INTEGER DEFAULT 12,
        last_notified TEXT
    )
    ''')
    
    # History table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        type TEXT DEFAULT 'task',
        bucket TEXT,
        repeat TEXT,
        completed_at TEXT NOT NULL,
        time_range TEXT,
        priority INTEGER
    )
    ''')
    
    # Config table (for access code)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    # Insert default access code if not exists
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('access_code', '1234')")
    
    # Notification settings
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notification_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    cursor.execute("INSERT OR IGNORE INTO notification_settings (key, value) VALUES ('hourly_report', 'true')")
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

# ============= DATABASE HELPER FUNCTIONS =============
def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect('task_tracker.db')
    conn.row_factory = sqlite3.Row
    return conn

def db_execute(query, params=()):
    """Execute SQL query and return results"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    
    if query.strip().upper().startswith('SELECT'):
        results = cursor.fetchall()
        conn.close()
        return [dict(row) for row in results]
    
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id

# ============= TELEGRAM NOTIFICATION FUNCTIONS =============
def log_telegram_notification(message, success=True):
    """Log Telegram notification"""
    try:
        logs = []
        if os.path.exists('telegram_log.json'):
            try:
                with open('telegram_log.json', 'r') as f:
                    logs = json.load(f)
            except:
                logs = []
        
        if not isinstance(logs, list):
            logs = []
        
        logs.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message': message[:100] + '...' if len(message) > 100 else message,
            'success': success
        })
        
        # Keep only last 100 logs
        if len(logs) > 100:
            logs = logs[-100:]
        
        with open('telegram_log.json', 'w') as f:
            json.dump(logs, f, indent=2)
    except Exception as e:
        print(f"Error logging notification: {e}")

def send_telegram_message(text):
    """Send message to Telegram"""
    try:
        bot.send_message(USER_ID, text, parse_mode='HTML')
        log_telegram_notification(text, True)
        return True
    except Exception as e:
        log_telegram_notification(f"Error: {str(e)}", False)
        return False

# ============= MONITORING FUNCTIONS =============
def check_task_reminders():
    """Check and send task reminders"""
    try:
        tasks = db_execute("SELECT * FROM tasks WHERE completed = 0 AND notify_enabled = 1")
        
        current_time = datetime.now()
        
        for task in tasks:
            task_id = task['id']
            task_title = task['title']
            start_time_str = task['start_time']
            last_notified = task['last_notified']
            
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
                
                if reminder_minutes in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
                    # Check if we already sent this reminder
                    if last_notified:
                        try:
                            last_time = datetime.strptime(last_notified, '%Y-%m-%d %H:%M:%S')
                            minutes_since_last = (current_time - last_time).total_seconds() / 60
                            if minutes_since_last < 1:  # Less than 1 minute ago
                                continue
                        except:
                            pass
                    
                    # Send reminder
                    message = f"⏰ <b>Task Reminder</b>\n"
                    message += f"📝 <b>{task_title}</b>\n"
                    message += f"🕐 Starts in {reminder_minutes} minute{'s' if reminder_minutes > 1 else ''}\n"
                    message += f"📅 {start_time.strftime('%I:%M %p')}\n"
                    
                    if send_telegram_message(message):
                        # Update last_notified time
                        db_execute(
                            "UPDATE tasks SET last_notified = ? WHERE id = ?",
                            (current_time.strftime('%Y-%m-%d %H:%M:%S'), task_id)
                        )
            
    except Exception as e:
        print(f"Error checking task reminders: {e}")

def check_note_reminders():
    """Check and send note reminders"""
    try:
        notes = db_execute("SELECT * FROM notes WHERE notify_enabled = 1")
        
        current_time = datetime.now()
        
        for note in notes:
            note_id = note['id']
            note_title = note['title']
            interval_hours = note['notify_interval'] or 12
            last_notified = note['last_notified']
            
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
            message += f"📌 <b>{note_title}</b>\n"
            message += f"🕐 Interval: Every {interval_hours} hours\n"
            message += f"⏰ {current_time.strftime('%I:%M %p')}\n"
            
            description = note['description'] or ''
            if description:
                # Strip HTML tags and limit length
                clean_desc = re.sub('<[^<]+?>', '', description)
                if len(clean_desc) > 200:
                    clean_desc = clean_desc[:200] + '...'
                message += f"\n{clean_desc}"
            
            if send_telegram_message(message):
                # Update last_notified time
                db_execute(
                    "UPDATE notes SET last_notified = ? WHERE id = ?",
                    (current_time.strftime('%Y-%m-%d %H:%M:%S'), note_id)
                )
            
    except Exception as e:
        print(f"Error checking note reminders: {e}")

def send_daily_report():
    """Send daily task status report"""
    try:
        current_time = datetime.now()
        current_date = current_time.strftime('%Y-%m-%d')
        
        # Get today's tasks
        tasks = db_execute('''
            SELECT * FROM tasks 
            WHERE date(start_time) = ? 
            ORDER BY start_time
        ''', (current_date,))
        
        if not tasks:
            message = f"📊 <b>Daily Task Report</b>\n"
            message += f"📅 {current_time.strftime('%B %d, %Y')}\n"
            message += f"🕐 {current_time.strftime('%I:%M %p')}\n"
            message += f"✅ No tasks for today!"
        else:
            completed_tasks = [t for t in tasks if t['completed']]
            pending_tasks = [t for t in tasks if not t['completed']]
            
            message = f"📊 <b>Daily Task Report</b>\n"
            message += f"📅 {current_time.strftime('%B %d, %Y')}\n"
            message += f"🕐 {current_time.strftime('%I:%M %p')}\n"
            message += f"📋 Total: {len(tasks)} tasks\n\n"
            
            message += f"<b>Today's Tasks:</b>\n"
            
            for task in tasks:
                task_status = "✅" if task['completed'] else "❌"
                start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
                time_str = start_time.strftime('%I:%M %p')
                
                # Get subtask completion
                subtasks = db_execute(
                    "SELECT * FROM subtasks WHERE task_id = ? ORDER BY priority",
                    (task['id'],)
                )
                
                if subtasks:
                    completed_subtasks = sum(1 for st in subtasks if st['completed'])
                    total_subtasks = len(subtasks)
                    subtask_info = f" ({completed_subtasks}/{total_subtasks} subtasks)"
                else:
                    subtask_info = ""
                
                message += f"{task_status} <b>{task['title']}</b> ({time_str}){subtask_info}\n"
            
            message += f"\n<b>Summary:</b>\n"
            message += f"✅ Completed: {len(completed_tasks)}\n"
            message += f"❌ Pending: {len(pending_tasks)}"
        
        send_telegram_message(message)
        
    except Exception as e:
        print(f"Error sending daily report: {e}")

def monitoring_loop():
    """Main monitoring loop"""
    last_minute_check = datetime.now()
    last_daily_report_sent = None
    
    while True:
        try:
            current_time = datetime.now()
            
            # Check reminders every minute
            if (current_time - last_minute_check).total_seconds() >= 60:
                check_task_reminders()
                check_note_reminders()
                last_minute_check = current_time
            
            # Send daily report at 8 AM
            if current_time.hour == 8 and current_time.minute == 0:
                if last_daily_report_sent != current_time.date():
                    send_daily_report()
                    last_daily_report_sent = current_time.date()
            
            time.sleep(30)  # Sleep for 30 seconds
            
        except Exception as e:
            print(f"Monitoring error: {e}")
            time.sleep(60)

# ============= TELEGRAM COMMAND HANDLERS =============
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Send welcome message"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    welcome_msg = """
🤖 <b>Task Tracker Bot</b>

I monitor your tasks and notes, sending reminders and reports.

<b>Commands:</b>
/status - Check bot status
/report - Get today's task status
/today - See today's tasks
/help - Show this message

<b>Features:</b>
• Task reminders (10 minutes before start)
• Note reminders (custom intervals)
• Daily task reports (8 AM)
• Real-time monitoring
"""
    bot.reply_to(message, welcome_msg, parse_mode='HTML')

@bot.message_handler(commands=['status'])
def send_status(message):
    """Send bot status"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    # Get counts
    tasks_count = len(db_execute("SELECT id FROM tasks WHERE completed = 0"))
    notes_count = len(db_execute("SELECT id FROM notes"))
    
    status_msg = f"""
📊 <b>Bot Status</b>

✅ <b>Online</b>
📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}

<b>Statistics:</b>
📋 Active Tasks: {tasks_count}
📝 Notes: {notes_count}

<b>Last Check:</b> {datetime.now().strftime('%H:%M:%S')}
"""
    bot.reply_to(message, status_msg, parse_mode='HTML')

@bot.message_handler(commands=['report', 'today'])
def send_report(message):
    """Send today's task report"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    send_daily_report()
    bot.reply_to(message, "📊 Today's report sent!")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle other messages"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    response = f"""
Echo: <b>{message.text}</b>

Send /help for available commands.
"""
    bot.reply_to(message, response, parse_mode='HTML')

# ============= FLASK ROUTES =============
@app.route('/')
def index():
    """Serve the main PHP application"""
    # Get current session from cookies
    session_id = request.cookies.get('session_id', '')
    
    # Load all data from database
    tasks = db_execute("SELECT * FROM tasks ORDER BY priority, start_time")
    notes = db_execute("SELECT * FROM notes ORDER BY priority")
    history = db_execute("SELECT * FROM history ORDER BY completed_at DESC")
    
    # Get config
    config_rows = db_execute("SELECT * FROM config")
    config = {row['key']: row['value'] for row in config_rows}
    
    # Get notification settings
    settings_rows = db_execute("SELECT * FROM notification_settings")
    notification_settings = {row['key']: row['value'] for row in settings_rows}
    
    # Load subtasks for each task
    for task in tasks:
        task['subtasks'] = db_execute(
            "SELECT * FROM subtasks WHERE task_id = ? ORDER BY priority",
            (task['id'],)
        )
    
    # Convert database rows to proper format for the PHP template
    processed_tasks = []
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    for task in tasks:
        # Calculate status
        start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
        end_time = datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S')
        current_time = datetime.now()
        
        task_date = start_time.strftime('%Y-%m-%d')
        
        # Convert to minutes for comparison
        current_minutes = current_time.hour * 60 + current_time.minute
        start_minutes = start_time.hour * 60 + start_time.minute
        end_minutes = end_time.hour * 60 + end_time.minute
        two_hours = 120
        
        if task_date < current_date and not task['completed'] and task['repeat'] == 'none':
            status = 'expired'
            time_display = 'expired'
            is_active = False
        else:
            if current_minutes < (start_minutes - two_hours):
                status = 'upcoming'
                time_display = 'upcoming'
                is_active = not task['completed']
            elif current_minutes >= (start_minutes - two_hours) and current_minutes < start_minutes:
                status = 'starting_soon'
                time_display = 'starting_soon'
                is_active = not task['completed']
            elif current_minutes >= start_minutes and current_minutes <= end_minutes:
                status = 'active'
                time_display = 'active'
                is_active = not task['completed']
            elif current_minutes > end_minutes and current_minutes <= (end_minutes + two_hours):
                status = 'due'
                time_display = 'due'
                is_active = not task['completed']
            else:
                status = 'overdue'
                time_display = 'overdue'
                is_active = not task['completed']
        
        # For completed repeating tasks
        is_completed_repeating = (task['repeat'] != 'none' and task['completed'])
        
        processed_tasks.append({
            'id': task['id'],
            'title': task['title'],
            'description': task['description'] or '',
            'bucket': task['bucket'],
            'repeat': task['repeat'],
            'repeat_day': task['repeat_day'],
            'repeat_end_date': task['repeat_end_date'],
            'start_time': task['start_time'],
            'end_time': task['end_time'],
            'completed': bool(task['completed']),
            'createdAt': task['created_at'],
            'nextOccurrence': task['next_occurrence'],
            'subtasks': task['subtasks'],
            'priority': task['priority'],
            'notify_enabled': bool(task['notify_enabled']),
            'last_notified': task['last_notified'],
            'start_timestamp': int(start_time.timestamp()),
            'end_timestamp': int(end_time.timestamp()),
            'status': status,
            'time_display': time_display,
            'is_active': is_active,
            'is_completed_repeating': is_completed_repeating
        })
    
    # Filter active tasks
    filtered_tasks = []
    for task in processed_tasks:
        if task['repeat'] == 'none' and not task['completed']:
            filtered_tasks.append(task)
        elif task['repeat'] != 'none':
            if task['is_completed_repeating']:
                filtered_tasks.append(task)
            else:
                # Check if task is active today
                task_date = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d')
                if task_date == current_date and not task['completed']:
                    filtered_tasks.append(task)
    
    # Sort tasks
    filtered_tasks.sort(key=lambda x: (not x['is_active'], x['priority']))
    
    # Process notes
    processed_notes = []
    for note in notes:
        processed_notes.append({
            'id': note['id'],
            'title': note['title'],
            'description': note['description'] or '',
            'priority': note['priority'],
            'createdAt': note['created_at'],
            'updatedAt': note['updated_at'],
            'notify_enabled': bool(note['notify_enabled']),
            'notify_interval': note['notify_interval'],
            'last_notified': note['last_notified']
        })
    
    # Process history
    processed_history = []
    for item in history:
        processed_history.append({
            'id': item['id'],
            'title': item['title'],
            'description': item['description'] or '',
            'type': item['type'],
            'bucket': item['bucket'],
            'repeat': item['repeat'],
            'completedAt': item['completed_at'],
            'time_range': item['time_range'],
            'priority': item['priority']
        })
    
    # Generate CSRF token
    import random
    import string
    csrf_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    
    # Check if user is logged in (simplified for demo)
    is_logged_in = session_id == 'authenticated' or request.args.get('login') == 'true'
    
    # Get current view
    current_view = request.args.get('view', 'tasks')
    
    # Here we embed the complete PHP HTML code
    # This is the exact PHP code converted to work with Python/Flask
    return Response(f'''
<!DOCTYPE html>
<html lang="en" id="theme-element">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Task Tracker</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{
            --primary: #4361ee; --primary-light: #4895ef; --secondary: #3f37c9; --success: #4cc9f0; --danger: #f72585; --warning: #f8961e; --info: #4895ef; --light: #f8f9fa; --dark: #212529; --gray: #6c757d; --gray-light: #adb5bd; --border-radius: 12px; --shadow: 0 4px 6px rgba(0, 0, 0, 0.1); --transition: all 0.3s ease;
            --pink-bg: rgba(255, 182, 193, 0.1); --blue-bg: rgba(173, 216, 230, 0.15); --blue-bg-hover: rgba(173, 216, 230, 0.25);
            --note-bg: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            --note-shadow: 0 8px 32px rgba(31, 38, 135, 0.1);
            --completed-bg: rgba(108, 117, 125, 0.1);
            --completed-text: #6c757d;
            --notify-bg: rgba(248, 150, 30, 0.1);
            --notify-color: #f8961e;
        }}
        
        @media (prefers-color-scheme: dark) {{
            :root {{
                --primary: #5a6ff0; --primary-light: #6a80f2; --secondary: #4f46e5; --success: #5fd3f0; --danger: #ff2d8e; --warning: #ffa94d; --info: #6a80f2; --light: #121212; --dark: #ffffff; --gray: #94a3b8; --gray-light: #475569; --shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
                --pink-bg: rgba(255, 182, 193, 0.05); --blue-bg: rgba(173, 216, 230, 0.08); --blue-bg-hover: rgba(173, 216, 230, 0.15);
                --note-bg: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                --note-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                --completed-bg: rgba(108, 117, 125, 0.2);
                --completed-text: #94a3b8;
                --notify-bg: rgba(248, 150, 30, 0.2);
                --notify-color: #ffa94d;
            }}
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
        body {{ background-color: var(--light); color: var(--dark); transition: var(--transition); min-height: 100vh; display: flex; flex-direction: column; font-size: 14px; }}
        
        /* Header Styles */
        .header {{ 
            background-color: var(--light); 
            padding: 8px 16px; 
            display: flex; 
            align-items: center; 
            justify-content: space-around; 
            box-shadow: var(--shadow); 
            position: sticky; 
            top: 0; 
            z-index: 100; 
            gap: 8px;
            flex-wrap: wrap;
        }}
        
        .header-action-btn {{
            display: flex;
            flex-direction: row;
            align-items: center;
            justify-content: center;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 20px;
            padding: 8px 16px;
            cursor: pointer;
            transition: var(--transition);
            box-shadow: var(--shadow);
            gap: 8px;
            flex: 1;
            max-width: 120px;
            margin: 0 4px;
        }}
        
        .header-action-btn i {{ font-size: 1rem; }}
        .header-action-btn span {{ font-size: 0.8rem; font-weight: 600; }}
        .header-action-btn:hover {{ background: var(--primary-light); transform: translateY(-2px); }}
        .header-action-btn:active, .action-btn:active, .btn:active, button:active {{ transform: none !important; box-shadow: var(--shadow) !important; }}
        
        .settings-btn {{
            position: static;
            margin-left: auto;
            background: var(--info);
            color: white;
            border: none;
            border-radius: 50%;
            width: 36px;
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }}

        @media (max-width: 768px) {{
            .header {{ padding: 8px; gap: 4px; }}
            .header-action-btn {{ 
                width: 100%;
                max-width: none;
                padding: 10px;
                margin: 2px;
                border-radius: 12px;
            }}
            .header-action-btn span {{ display: block; font-size: 0.75rem; }}
            .header-action-btn i {{ margin-right: 4px; font-size: 0.9rem; }}
            .settings-btn {{ position: static; margin-left: auto; }}
        }}

        /* Floating Action Buttons */
        .fab {{
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
        }}
        
        .fab:hover {{
            background-color: var(--primary-light);
            transform: scale(1.1);
            box-shadow: 0 6px 16px rgba(0, 0, 0, 0.3);
        }}
        
        .fab-tasks {{
            bottom: 30px;
            right: 30px;
        }}
        
        .fab-notes {{
            bottom: 30px;
            right: 30px;
        }}
        
        @media (max-width: 768px) {{
            .fab {{
                width: 50px;
                height: 50px;
                font-size: 1.3rem;
            }}
            
            .fab-tasks {{
                bottom: 20px;
                right: 20px;
            }}
            
            .fab-notes {{
                bottom: 20px;
                right: 20px;
            }}
        }}

        .login-container {{ display: flex; justify-content: center; align-items: center; min-height: 80vh; padding: 20px; }}
        .auth-section {{ background-color: var(--light); padding: 30px; border-radius: var(--border-radius); box-shadow: var(--shadow); border-bottom: 4px solid var(--danger); width: 100%; max-width: 400px; }}
        .auth-container {{ margin: 0 auto; }}
        .auth-message {{ padding: 10px; margin-bottom: 15px; border-radius: 6px; text-align: center; font-weight: 600; }}
        .auth-message.success {{ background-color: rgba(76, 201, 240, 0.2); color: var(--success); border: 1px solid var(--success); }}
        .auth-message.error {{ background-color: rgba(247, 37, 133, 0.2); color: var(--danger); border: 1px solid var(--danger); }}
        .tab-buttons {{ display: flex; margin-bottom: 20px; border-bottom: 1px solid var(--gray-light); }}
        .tab-button {{ flex: 1; padding: 12px; background: none; border: none; cursor: pointer; font-weight: 600; color: var(--gray); transition: var(--transition); border-bottom: 3px solid transparent; }}
        .tab-button.active {{ color: var(--primary); border-bottom: 3px solid var(--primary); }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        
        .main-content {{ flex-grow: 1; padding: 16px; overflow-y: auto; padding-bottom: 100px; }}
        .view-content {{ display: none; }}
        .view-content.active {{ display: block; animation: fadeIn 0.5s ease; }}
        .content-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }}
        .page-title {{ font-size: 1.5rem; font-weight: 700; color: var(--dark); }}
        
        .bucket-header {{ display: flex; align-items: center; margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--gray-light); flex-wrap: wrap; gap: 10px;}}
        .bucket-title {{ font-size: 1.2rem; font-weight: 600; color: var(--dark); display: flex; align-items: center; gap: 8px; }}
        .bucket-count {{ background-color: var(--primary); color: white; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-size: 0.8rem; }}
        
        .items-container {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; width: 100%; }}
        @media (max-width: 1200px) {{ .items-container {{ grid-template-columns: repeat(2, 1fr) !important; }} }}
        @media (max-width: 768px) {{ .items-container {{ grid-template-columns: 1fr !important; }} }}
        
        .task-card {{ 
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
        }}
        
        .task-card.completed-repeating {{
            background-color: var(--completed-bg);
            opacity: 0.8;
        }}
        
        .task-card.completed-repeating .task-title,
        .task-card.completed-repeating .task-description,
        .task-card.completed-repeating .task-date-range,
        .task-card.completed-repeating .task-time-range,
        .task-card.completed-repeating .repeat-badge,
        .task-card.completed-repeating .priority-badge {{
            color: var(--completed-text);
        }}
        
        .task-card.completed-repeating .action-btn {{
            background-color: var(--completed-text);
        }}
        
        .task-card.completed-repeating .action-btn:hover {{
            background-color: var(--completed-text);
            transform: scale(1);
        }}
        
        .notify-badge {{
            background-color: var(--notify-bg);
            color: var(--notify-color);
            padding: 2px 8px;
            border-radius: 20px;
            font-size: 0.65rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 4px;
        }}
        
        .next-occurrence-info {{
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
        }}
        
        .next-occurrence-info i {{
            font-size: 0.9rem;
        }}
        
        @media (prefers-color-scheme: dark) {{
            .task-card {{
                box-shadow: rgba(255, 255, 255, 0.05) 0px -23px 25px 0px inset, rgba(255, 255, 255, 0.04) 0px -36px 30px 0px inset, rgba(255, 255, 255, 0.03) 0px -79px 40px 0px inset, rgba(255, 255, 255, 0.02) 0px 2px 1px, rgba(255, 255, 255, 0.02) 0px 4px 2px, rgba(255, 255, 255, 0.02) 0px 8px 4px, rgba(255, 255, 255, 0.02) 0px 16px 8px, rgba(255, 255, 255, 0.02) 0px 32px 16px;
            }}
        }}
        
        .task-card:hover {{ transform: translateY(-5px); box-shadow: 0 10px 15px rgba(0, 0, 0, 0.1); }}
        
        .task-header {{ display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 8px; }}
        .task-title {{ font-size: 1rem !important; font-weight: 600; color: var(--dark); margin-bottom: 4px; line-height: 1.4 !important; }}
        .task-description {{ font-size: 0.8rem !important; color: var(--gray); margin-bottom: 12px; line-height: 1.4 !important; flex-grow: 1; }}
        .task-description:empty {{ display: none !important; margin-bottom: 0 !important; }}
        
        .task-actions {{ display: flex; gap: 8px; }}
        .action-btn {{ background-color: var(--primary); color: white; border: none; border-radius: 50%; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: var(--transition); font-size: 0.8rem; }}
        .action-btn:hover {{ background-color: var(--primary); transform: scale(1.1); }}
        
        .action-btn.disabled {{
            background-color: var(--gray-light);
            cursor: not-allowed;
            opacity: 0.6;
        }}
        
        .action-btn.disabled:hover {{
            transform: none;
            background-color: var(--gray-light);
        }}
        
        .task-meta {{ display: flex; align-items: center; justify-content: space-between; font-size: 0.75rem; color: var(--gray); margin-top: auto; padding-top: 12px; }}
        .repeat-badge {{ background-color: rgba(67, 97, 238, 0.1); color: var(--primary); padding: 2px 8px; border-radius: 20px; font-size: 0.65rem; font-weight: 600; display: flex; align-items: center; gap: 4px; }}
        .priority-badge {{ background-color: rgba(108, 117, 125, 0.2); color: var(--gray); padding: 2px 8px; border-radius: 20px; font-size: 0.65rem; font-weight: 600; display: flex; align-items: center; gap: 4px; }}
        
        .task-date-range {{ font-size: 0.75rem; color: var(--gray); margin-right: 8px; }}
        .task-time-range {{ font-size: 0.75rem; color: var(--gray); font-weight: 500; }}
        
        .subtask-number-badge {{ width: 22px; height: 22px; border-radius: 50%; background-color: var(--gray-light); color: var(--dark); display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: bold; transition: var(--transition); }}
        .subtask-number-badge.completed {{ background-color: var(--primary); color: white; }}
        .subtask-complete-btn {{ background: none; border: none; cursor: pointer; padding: 0; margin-right: 8px;}}
        .edit-subtask-btn, .delete-subtask-btn {{ background: none; border: none; color: var(--primary); cursor: pointer; font-size: 0.7rem; opacity: 0.7; transition: var(--transition); padding: 2px 4px; }}
        .edit-subtask-btn:hover, .delete-subtask-btn:hover {{ opacity: 1; transform: scale(1.1); }}
        .delete-subtask-btn {{ color: var(--danger); }}

        .subtasks-details {{ margin-top: 12px; border-top: 1px solid var(--gray-light); padding-top: 12px; }}
        .subtasks-details summary {{ cursor: pointer; display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 0.85rem; color: var(--primary); padding: 4px 0; transition: var(--transition); }}
        .subtasks-details summary:hover {{ color: var(--primary-light); }}
        .details-toggle {{ margin-left: auto; transition: var(--transition); }}
        .subtasks-details[open] .details-toggle {{ transform: rotate(90deg); }}
        .subtasks-content {{ margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(0,0,0,0.05); }}
        @media (prefers-color-scheme: dark) {{
            .subtasks-content {{ border-top-color: rgba(255,255,255,0.05); }}
        }}
        .subtask-item {{ display: flex; align-items: flex-start; margin-bottom: 8px; padding: 8px; background: rgba(0,0,0,0.03); border-radius: 6px; }}
        @media (prefers-color-scheme: dark) {{
            .subtask-item {{ background: rgba(255,255,255,0.05); }}
        }}
        .subtask-details-container {{ flex: 1; margin-right: 8px;}}
        .subtask-title {{ font-size: 0.85rem; color: var(--dark); cursor: pointer; }}
        .subtask-completed {{ text-decoration: line-through; color: var(--gray); }}
        .subtask-description {{ font-size: 0.75rem; color: var(--gray); margin-top: 4px; padding-left: 8px; border-left: 2px solid var(--primary-light); line-height: 1.4; }}
        .subtask-actions {{ display: flex; align-items: center; margin-left: auto; }}
        
        .progress-display-container {{ display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }}
        .progress-bar-container {{ flex: 1; background: var(--gray-light); border-radius: 20px; height: 10px; overflow: hidden; }}
        .progress-bar-fill {{ height: 100%; background: var(--primary); transition: width 0.3s ease; }}
        .progress-circle {{ width: 36px; height: 36px; border-radius: 50%; background: conic-gradient(var(--primary) 0%, var(--gray-light) 0%); display: flex; align-items: center; justify-content: center; position: relative; flex-shrink: 0; }}
        .progress-circle::before {{ content: ''; position: absolute; width: 26px; height: 26px; background-color: var(--light); border-radius: 50%; }}
        .progress-text {{ font-size: 0.75rem; color: var(--gray); }}
        
        .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.5); z-index: 1000; align-items: center; justify-content: center; animation: fadeIn 0.3s ease; }}
        .modal-content {{ background-color: var(--light); border-radius: var(--border-radius); width: 90%; max-width: 500px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2); animation: scaleIn 0.3s ease; overflow: hidden; max-height: 90vh; overflow-y: auto; }}
        .modal-header {{ padding: 16px; border-bottom: 1px solid var(--gray-light); display: flex; align-items: center; justify-content: space-between; }}
        .modal-title {{ font-size: 1.2rem; font-weight: 600; color: var(--dark); }}
        .close-modal {{ background: none; border: none; font-size: 1.3rem; color: var(--gray); cursor: pointer; transition: var(--transition); }}
        .close-modal:hover {{ color: var(--danger); }}
        .modal-body {{ padding: 16px; }}
        .form-group {{ margin-bottom: 12px; }}
        .form-label {{ display: block; margin-bottom: 4px; font-weight: 600; color: var(--dark); font-size: 0.9rem; }}
        .form-input, .form-select, .form-textarea {{ width: 100%; padding: 8px; border: 1px solid var(--gray-light); border-radius: 6px; background-color: var(--light); color: var(--dark); transition: var(--transition); font-size: 0.9rem; }}
        .form-input:focus, .form-select:focus, .form-textarea:focus {{ outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2); }}
        .form-textarea {{ min-height: 80px; resize: vertical; line-height: 1.4; }}
        .form-actions {{ display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }}
        .btn {{ padding: 8px 16px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; transition: var(--transition); font-size: 0.9rem; }}
        .btn-primary {{ background-color: var(--primary); color: white; }}
        .btn-primary:hover {{ background-color: var(--secondary); }}
        .btn-secondary {{ background-color: var(--gray-light); color: white; }}
        .btn-secondary:hover {{ background-color: var(--gray); }}
        .time-input-group {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }}
        .date-input-group {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }}
        
        .checkbox-group {{ display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }}
        .checkbox-label {{ font-weight: 500; color: var(--dark); }}
        .form-checkbox {{ width: 18px; height: 18px; }}
        
        /* History styles */
        .history-date-details {{ margin-bottom: 15px; }}
        .history-date-summary {{ padding: 12px 16px; background-color: var(--blue-bg); border-radius: var(--border-radius); cursor: pointer; font-weight: 600; display: flex; align-items: center; gap: 10px; transition: var(--transition); border: 1px solid transparent; }}
        .history-date-summary:hover {{ background-color: var(--blue-bg-hover); border-color: var(--primary-light); }}
        .history-date-content {{ padding: 10px 0 0 15px; }}
        .history-items-container {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; margin: 10px 0; }}
        .history-card {{ background-color: var(--blue-bg); border-radius: var(--border-radius); padding: 16px; box-shadow: var(--shadow); transition: var(--transition); border: 1px solid rgba(0,0,0,0.05); border-left: 4px solid var(--success); }}
        .history-card:hover {{ transform: translateY(-3px); box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15); }}
        .history-card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }}
        .history-card-title {{ font-weight: 600; color: var(--dark); font-size: 0.8rem; display: flex; align-items: center; gap: 8px; flex: 1; }}
        .history-card-title i {{ color: var(--primary); font-size: 0.9rem; }}
        .history-card-time {{ font-size: 0.75rem; color: var(--gray); background: rgba(0,0,0,0.05); padding: 3px 8px; border-radius: 12px; white-space: nowrap; margin-left: 10px; }}
        .history-card-description {{ font-size: 0.8rem; color: var(--gray); margin-bottom: 12px; line-height: 1.4; }}
        .history-card-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
        .history-meta-item {{ background: rgba(0,0,0,0.05); color: var(--gray); padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 500; }}
        .history-subitems {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(0,0,0,0.1); }}
        .history-stage-item {{ font-size: 0.8rem; color: var(--gray); margin-bottom: 8px; padding: 8px; background: rgba(0,0,0,0.03); border-radius: 6px; }}
        .history-stage-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }}
        .history-stage-title {{ font-weight: 600; color: var(--dark); flex: 1; }}
        .history-stage-description {{ font-size: 0.75rem; color: var(--gray); margin-top: 4px; padding-left: 8px; border-left: 2px solid var(--success); line-height: 1.4; }}
        
        @media (prefers-color-scheme: dark) {{
            .history-card {{ background-color: rgba(173, 216, 230, 0.08); border: 1px solid rgba(255,255,255,0.05); }}
            .history-card-time, .history-meta-item {{ background: rgba(255,255,255,0.1); }}
            .history-subitems {{ border-top-color: rgba(255,255,255,0.1); }}
            .history-stage-item {{ background: rgba(255,255,255,0.05); }}
        }}
        
        /* Notes Styles */
        .notes-container {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }}
        .note-card {{
            background: var(--note-bg);
            border-radius: var(--border-radius);
            padding: 0;
            box-shadow: var(--note-shadow);
            transition: var(--transition);
            border: 1px solid rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
        }}
        
        .note-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15);
        }}
        
        .note-details {{
            width: 100%;
        }}
        
        .note-summary {{
            list-style: none;
            padding: 20px;
            cursor: pointer;
        }}
        
        .note-summary::-webkit-details-marker {{
            display: none;
        }}
        
        .note-header {{
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }}
        
        .note-title {{
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--dark);
            margin-bottom: 4px;
            line-height: 1.3;
        }}
        
        .note-date {{
            font-size: 0.75rem;
            color: var(--gray);
            font-weight: 500;
        }}
        
        .note-content {{
            padding: 0 20px 20px 20px;
        }}
        
        .note-description {{
            font-size: 0.9rem;
            color: var(--dark);
            line-height: 1.5;
            margin-bottom: 16px;
        }}
        
        .note-description strong {{
            font-weight: 700;
            color: var(--primary);
        }}
        
        .note-description em {{
            font-style: italic;
            color: var(--secondary);
        }}
        
        .note-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: auto;
            padding-top: 12px;
            border-top: 1px solid rgba(0,0,0,0.05);
        }}
        
        @media (prefers-color-scheme: dark) {{
            .note-footer {{
                border-top-color: rgba(255,255,255,0.05);
            }}
        }}
        
        .note-meta {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .note-date-badge {{
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.7rem;
            font-weight: 500;
        }}
        
        .note-actions {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        
        .note-action-btn, .note-move-btn {{
            background: none;
            border: none;
            color: var(--primary);
            cursor: pointer;
            font-size: 0.9rem;
            transition: var(--transition);
            opacity: 0.7;
            padding: 4px;
            border-radius: 4px;
        }}
        
        .note-action-btn:hover, .note-move-btn:hover {{
            opacity: 1;
            transform: scale(1.1);
            background: rgba(67, 97, 238, 0.1);
        }}
        
        .note-action-btn.delete {{
            color: var(--danger);
        }}
        
        .note-action-btn.delete:hover {{
            background: rgba(247, 37, 133, 0.1);
        }}
        
        /* Settings View */
        .settings-card {{
            background: var(--blue-bg);
            border-radius: var(--border-radius);
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
        }}
        
        .settings-title {{
            font-size: 1.2rem;
            font-weight: 600;
            color: var(--dark);
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .settings-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid rgba(0,0,0,0.1);
        }}
        
        .settings-item:last-child {{
            border-bottom: none;
        }}
        
        .settings-label {{
            font-weight: 500;
            color: var(--dark);
        }}
        
        .toggle-switch {{
            position: relative;
            display: inline-block;
            width: 50px;
            height: 24px;
        }}
        
        .toggle-switch input {{
            opacity: 0;
            width: 0;
            height: 0;
        }}
        
        .toggle-slider {{
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: var(--gray-light);
            transition: .4s;
            border-radius: 24px;
        }}
        
        .toggle-slider:before {{
            position: absolute;
            content: "";
            height: 16px;
            width: 16px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }}
        
        input:checked + .toggle-slider {{
            background-color: var(--success);
        }}
        
        input:checked + .toggle-slider:before {{
            transform: translateX(26px);
        }}
        
        .empty-state {{ text-align: center; padding: 32px 16px; color: var(--gray); }}
        .empty-state i {{ font-size: 2.5rem; margin-bottom: 12px; opacity: 0.5; }}
        
        .time-remaining-badge {{ background-color: rgba(67, 97, 238, 0.1); color: var(--primary); padding: 4px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: 600; }}
        .time-remaining-badge.upcoming {{ background-color: rgba(108, 117, 125, 0.2); color: var(--gray); }}
        .time-remaining-badge.starting_soon {{ background-color: rgba(248, 150, 30, 0.1); color: var(--warning); }}
        .time-remaining-badge.active {{ background-color: rgba(76, 201, 240, 0.2); color: var(--success); }}
        .time-remaining-badge.due {{ background-color: rgba(248, 150, 30, 0.1); color: var(--warning); }}
        .time-remaining-badge.overdue {{ background-color: rgba(247, 37, 133, 0.1); color: var(--danger); }}
        .time-remaining-badge.expired {{ background-color: rgba(108, 117, 125, 0.2); color: var(--gray); }}
        
        @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
        @keyframes scaleIn {{ from {{ opacity: 0; transform: scale(0.9); }} to {{ opacity: 1; transform: scale(1); }} }}
        @keyframes slideIn {{ from {{ opacity: 0; transform: translateY(20px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        
        @media (max-width: 768px) {{
            .history-items-container {{ grid-template-columns: 1fr; }}
            .notes-container {{ grid-template-columns: 1fr; }}
            .task-description, .history-card-description {{ font-size: 0.75rem; }}
            .task-card {{ min-height: 120px !important; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        {'<button class="header-action-btn" onclick="switchView(\'tasks\')" title="Tasks">
                <i class="fas fa-tasks"></i>
                <span>Tasks</span>
            </button>
            <button class="header-action-btn" onclick="switchView(\'notes\')" title="Notes">
                <i class="fas fa-wand-magic-sparkles"></i>
                <span>Notes</span>
            </button>
            <button class="header-action-btn" onclick="switchView(\'history\')" title="History">
                <i class="fas fa-history"></i>
                <span>History</span>
            </button>
            <button class="settings-btn" onclick="switchView(\'settings\')" title="Settings">
                <i class="fas fa-cog"></i>
            </button>' if is_logged_in else ''}
    </div>

    {f'''
        <!-- Show FAB based on current view -->
        <div id="fabContainer">
            {f'''
            {'<button class="fab fab-tasks" onclick="openAddTaskModal()" title="Add Task"><i class="fas fa-plus"></i></button>' if current_view == "tasks" else ''}
            {'<button class="fab fab-notes" onclick="openAddNoteModal()" title="Add Note"><i class="fas fa-plus"></i></button>' if current_view == "notes" else ''}
            '''}
        </div>
    ''' if is_logged_in else ''}

    {f'''
    <div class="login-container">
        <div class="auth-section">
            <div class="auth-container">
                <div class="tab-buttons">
                    <button class="tab-button active" onclick="switchTab(\'login\')">Login</button>
                    <button class="tab-button" onclick="switchTab(\'changeCode\')">Change Code</button>
                </div>
                
                <div class="tab-content active" id="loginTab">
                    <form method="POST" action="/login" class="auth-form">
                        <input type="hidden" name="action" value="login">
                        <input type="hidden" name="csrf_token" value="{csrf_token}">
                        <div class="form-group">
                            <label class="form-label">Access Code</label>
                            <input type="password" class="form-input" name="access_code" required placeholder="Enter access code">
                        </div>
                        <div class="form-actions">
                            <button type="submit" class="btn btn-primary">Access System</button>
                        </div>
                    </form>
                </div>
                
                <div class="tab-content" id="changeCodeTab">
                    <form method="POST" action="/change_code" class="auth-form">
                        <input type="hidden" name="action" value="change_code">
                        <input type="hidden" name="csrf_token" value="{csrf_token}">
                        <div class="form-group">
                            <label class="form-label">Current Access Code</label>
                            <input type="password" class="form-input" name="current_code" required placeholder="Enter current code">
                        </div>
                        <div class="form-group">
                            <label class="form-label">New Access Code</label>
                            <input type="password" class="form-input" name="new_code" required placeholder="Enter new code">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Confirm New Code</label>
                            <input type="password" class="form-input" name="confirm_code" required placeholder="Confirm new code">
                        </div>
                        <div class="form-actions">
                            <button type="submit" class="btn btn-primary">Change Access Code</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
    ''' if not is_logged_in else f'''
    <div class="main-content">
        <!-- Tasks View -->
        <div class="view-content {'active' if current_view == 'tasks' else ''}" id="tasksView">
            <div class="content-header">
                <h1 class="page-title">Tasks</h1>
            </div>
            
            <div class="bucket-header">
                <h2 class="bucket-title">
                    <i class="fas fa-tasks"></i>
                    Active Tasks
                    <span class="bucket-count">{len([t for t in filtered_tasks if t["is_active"]])}</span>
                </h2>
            </div>
            
            <div class="items-container">
                {'''
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <i class="fas fa-clipboard-list"></i>
                    <p>No tasks for today. Add a new one to get started!</p>
                </div>''' if not filtered_tasks else ''.join([render_task_card(task) for task in filtered_tasks])}
            </div>
        </div>

        <!-- Notes View -->
        <div class="view-content {'active' if current_view == 'notes' else ''}" id="notesView">
            <div class="content-header">
                <h1 class="page-title">Notes</h1>
            </div>
            <div class="notes-container">
                {'''
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <i class="fas fa-wand-magic-sparkles"></i>
                    <p>No notes yet. Add one to get started!</p>
                </div>''' if not processed_notes else ''.join([render_note_card(note) for note in processed_notes])}
            </div>
        </div>

        <!-- History View -->
        <div class="view-content {'active' if current_view == 'history' else ''}" id="historyView">
            <div class="content-header">
                <h1 class="page-title">History</h1>
            </div>
            
            <div id="historyContainer">
                {'''
                <div class="empty-state">
                    <i class="fas fa-history"></i>
                    <p>No completed items yet. Complete some items to see them here!</p>
                </div>''' if not processed_history else render_history_view(processed_history)}
            </div>
        </div>
        
        <!-- Settings View -->
        <div class="view-content {'active' if current_view == 'settings' else ''}" id="settingsView">
            <div class="content-header">
                <h1 class="page-title">Settings</h1>
            </div>
            
            <div class="settings-card">
                <h2 class="settings-title">
                    <i class="fas fa-bell"></i>
                    Notification Settings
                </h2>
                
                <div class="settings-item">
                    <span class="settings-label">Daily Task Status Reports (8 AM)</span>
                    <form method="POST" action="/toggle_daily_report" id="dailyReportForm">
                        <input type="hidden" name="action" value="toggle_daily_report">
                        <input type="hidden" name="csrf_token" value="{csrf_token}">
                        <label class="toggle-switch">
                            <input type="checkbox" name="enabled" {'checked' if notification_settings.get('daily_report', 'true') == 'true' else ''} onchange="this.form.submit()">
                            <span class="toggle-slider"></span>
                        </label>
                    </form>
                </div>
                
                <p style="margin-top: 16px; color: var(--gray); font-size: 0.85rem;">
                    <i class="fas fa-info-circle"></i> 
                    Daily reports send task status updates (completed/pending) to Telegram at 8 AM.
                </p>
            </div>
            
            <div class="settings-card">
                <h2 class="settings-title">
                    <i class="fas fa-info-circle"></i>
                    System Information
                </h2>
                
                <div class="settings-item">
                    <span class="settings-label">Server Time</span>
                    <span class="settings-value">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
                </div>
                
                <div class="settings-item">
                    <span class="settings-label">Total Tasks</span>
                    <span class="settings-value">{len(tasks)}</span>
                </div>
                
                <div class="settings-item">
                    <span class="settings-label">Total Notes</span>
                    <span class="settings-value">{len(notes)}</span>
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
                    Telegram User ID: {USER_ID}
                </p>
            </div>
            
            <div class="settings-card">
                <h2 class="settings-title">
                    <i class="fas fa-door-open"></i>
                    Session
                </h2>
                
                <div class="settings-item">
                    <form method="POST" action="/logout" style="width: 100%;">
                        <input type="hidden" name="csrf_token" value="{csrf_token}">
                        <button type="submit" class="btn btn-danger" style="width: 100%;">
                            <i class="fas fa-sign-out-alt"></i> Logout
                        </button>
                    </form>
                </div>
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
                    <input type="hidden" name="action" value="add_task">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
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
                            {''.join([f'<option value="{i}" {"selected" if i==15 else ""}>{i}</option>' for i in range(1, 16)])}
                        </select>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" class="form-checkbox" name="notify_enabled" id="notifyEnabled" checked>
                        <label class="checkbox-label" for="notifyEnabled">Enable Telegram notifications (10 reminders before start time)</label>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Repeat</label>
                        <select class="form-select" name="repeat" id="repeatSelect">
                            <option value="none">None</option>
                            <option value="daily">Daily</option>
                            <option value="weekly">Weekly</option>
                        </select>
                    </div>
                    <div class="date-input-group">
                        <div class="form-group">
                            <label class="form-label">Start Date</label>
                            <input type="date" class="form-input" name="start_date" id="startDate" value="{datetime.now().strftime('%Y-%m-%d')}">
                        </div>
                        <div class="form-group">
                            <label class="form-label">End Date</label>
                            <input type="date" class="form-input" name="end_date" id="endDate" value="{datetime.now().strftime('%Y-%m-%d')}">
                        </div>
                    </div>
                    <div class="time-input-group">
                        <div class="form-group">
                            <label class="form-label">Start Time</label>
                            <input type="time" class="form-input" name="start_time" id="startTime" value="{datetime.now().strftime('%H:%M')}">
                        </div>
                        <div class="form-group">
                            <label class="form-label">End Time</label>
                            <input type="time" class="form-input" name="end_time" id="endTime" value="{(datetime.now() + timedelta(hours=1)).strftime('%H:%M')}">
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
                    <input type="hidden" name="action" value="add_note">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
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
                    <input type="hidden" name="action" value="update_note">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
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
                    <input type="hidden" name="action" value="add_subtask">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
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
                    <input type="hidden" name="action" value="update_task">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
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
                            {''.join([f'<option value="{i}">{i}</option>' for i in range(1, 16)])}
                        </select>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" class="form-checkbox" name="notify_enabled" id="editTaskNotifyEnabled">
                        <label class="checkbox-label" for="editTaskNotifyEnabled">Enable Telegram notifications (10 reminders before start time)</label>
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
                    <input type="hidden" name="action" value="update_subtask">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
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
                            {''.join([f'<option value="{i}">{i}</option>' for i in range(1, 16)])}
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
    '''}

    <script>
        function switchTab(tabName) {{
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-button').forEach(button => button.classList.remove('active'));
            document.getElementById(tabName + 'Tab').classList.add('active');
            event.target.classList.add('active');
        }}

        function switchView(viewName) {{
            window.location.href = '/?view=' + viewName;
        }}
        
        function updateFAB(viewName) {{
            const fabContainer = document.getElementById('fabContainer');
            if (fabContainer) {{
                if (viewName === 'tasks') {{
                    fabContainer.innerHTML = '<button class="fab fab-tasks" onclick="openAddTaskModal()" title="Add Task"><i class="fas fa-plus"></i></button>';
                }} else if (viewName === 'notes') {{
                    fabContainer.innerHTML = '<button class="fab fab-notes" onclick="openAddNoteModal()" title="Add Note"><i class="fas fa-plus"></i></button>';
                }} else {{
                    fabContainer.innerHTML = '';
                }}
            }}
        }}

        function openModal(modalId) {{ document.getElementById(modalId).style.display = 'flex'; }}
        function closeModal(modalId) {{ document.getElementById(modalId).style.display = 'none'; }}

        function openAddTaskModal() {{ 
            // Set default date and time
            const now = new Date();
            const today = now.toISOString().split('T')[0];
            const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000);
            const endTime = oneHourLater.toTimeString().split(':').slice(0, 2).join(':');
            
            document.getElementById('startDate').value = today;
            document.getElementById('endDate').value = today;
            document.getElementById('startTime').value = now.toTimeString().split(':').slice(0, 2).join(':');
            document.getElementById('endTime').value = endTime;
            
            openModal('addTaskModal'); 
        }}
        
        function closeAddTaskModal() {{ closeModal('addTaskModal'); }}
        function closeEditTaskModal() {{ closeModal('editTaskModal'); }}
        function closeEditSubtaskModal() {{ closeModal('editSubtaskModal'); }}
        
        function openAddNoteModal() {{ 
            openModal('addNoteModal'); 
            // Show/hide interval input based on checkbox
            const checkbox = document.getElementById('noteNotifyEnabled');
            const intervalGroup = document.getElementById('noteIntervalGroup');
            checkbox.addEventListener('change', function() {{
                intervalGroup.style.display = this.checked ? 'block' : 'none';
            }});
        }}
        
        function closeAddNoteModal() {{ closeModal('addNoteModal'); }}
        function closeEditNoteModal() {{ closeModal('editNoteModal'); }}
        
        function openAddSubtaskModal(taskId) {{
            document.getElementById('addSubtaskTaskId').value = taskId;
            openModal('addSubtaskModal');
        }}
        function closeAddSubtaskModal() {{ closeModal('addSubtaskModal'); }}

        function openEditTaskModal(taskId) {{
            // This would be populated with actual task data via API
            fetch('/get_task/' + taskId)
                .then(response => response.json())
                .then(taskData => {{
                    if (taskData) {{
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
                        if (taskData.repeat_end_date) {{
                            const repeatEndDate = new Date(taskData.repeat_end_date);
                            document.getElementById('editRepeatEndDate').value = repeatEndDate.toISOString().split('T')[0];
                        }} else {{
                            document.getElementById('editRepeatEndDate').value = '';
                        }}
                        
                        openModal('editTaskModal');
                    }}
                }});
        }}
        
        function openEditNoteModal(noteId) {{
            // This would be populated with actual note data via API
            fetch('/get_note/' + noteId)
                .then(response => response.json())
                .then(noteData => {{
                    if (noteData) {{
                        document.getElementById('editNoteId').value = noteId;
                        document.getElementById('editNoteTitle').value = noteData.title || '';
                        document.getElementById('editNoteDescription').value = noteData.description || '';
                        document.getElementById('editNoteNotifyEnabled').checked = noteData.notify_enabled || false;
                        document.getElementById('editNoteInterval').value = noteData.notify_interval || 12;
                        
                        const intervalGroup = document.getElementById('editNoteIntervalGroup');
                        intervalGroup.style.display = noteData.notify_enabled ? 'block' : 'none';
                        
                        openModal('editNoteModal');
                        
                        // Add change event for checkbox
                        document.getElementById('editNoteNotifyEnabled').addEventListener('change', function() {{
                            intervalGroup.style.display = this.checked ? 'block' : 'none';
                        }});
                    }}
                }});
        }}

        function openEditSubtaskModal(taskId, subtaskId) {{
            // This would be populated with actual subtask data via API
            fetch('/get_subtask/' + taskId + '/' + subtaskId)
                .then(response => response.json())
                .then(subtaskData => {{
                    if (subtaskData) {{
                        document.getElementById('editSubtaskTaskId').value = taskId;
                        document.getElementById('editSubtaskId').value = subtaskId;
                        document.getElementById('editSubtaskTitle').value = subtaskData.title || '';
                        document.getElementById('editSubtaskDescription').value = subtaskData.description || '';
                        document.getElementById('editSubtaskPriority').value = subtaskData.priority || 15;
                        openModal('editSubtaskModal');
                    }}
                }});
        }}

        {'function calculateTimeDisplay(startTime, endTime, isActive) {{
            if (!isActive) {{
                return {{
                    text: 'Completed',
                    status: 'completed',
                    class: 'upcoming'
                }};
            }}
            
            const now = new Date();
            const start = new Date(startTime * 1000);
            const end = new Date(endTime * 1000);
            
            // Convert to minutes for easier comparison
            const currentMinutes = now.getHours() * 60 + now.getMinutes();
            const startMinutes = start.getHours() * 60 + start.getMinutes();
            const endMinutes = end.getHours() * 60 + end.getMinutes();
            
            const twoHours = 120; // 2 hours in minutes
            
            if (currentMinutes < (startMinutes - twoHours)) {{
                // More than 2 hours before start
                return {{
                    text: 'Upcoming',
                    status: 'upcoming',
                    class: 'upcoming'
                }};
            }} else if (currentMinutes >= (startMinutes - twoHours) && currentMinutes < startMinutes) {{
                // Within 2 hours of start
                const minutesBefore = startMinutes - currentMinutes;
                const hours = Math.floor(minutesBefore / 60);
                const minutes = minutesBefore % 60;
                
                if (hours > 0) {{
                    return {{
                        text: `Starts in ${{hours}}h ${{minutes}}m`,
                        status: 'starting_soon',
                        class: 'starting_soon'
                    }};
                }} else {{
                    return {{
                        text: `Starts in ${{minutes}}m`,
                        status: 'starting_soon',
                        class: 'starting_soon'
                    }};
                }}
            }} else if (currentMinutes >= startMinutes && currentMinutes <= endMinutes) {{
                // During task time
                const minutesLeft = endMinutes - currentMinutes;
                const hours = Math.floor(minutesLeft / 60);
                const minutes = minutesLeft % 60;
                
                if (hours > 0) {{
                    return {{
                        text: `${{hours}}h ${{minutes}}m left`,
                        status: 'active',
                        class: 'active'
                    }};
                }} else {{
                    return {{
                        text: `${{minutes}}m left`,
                        status: 'active',
                        class: 'active'
                    }};
                }}
            }} else if (currentMinutes > endMinutes && currentMinutes <= (endMinutes + twoHours)) {{
                // Within 2 hours after end
                const minutesOver = currentMinutes - endMinutes;
                const hours = Math.floor(minutesOver / 60);
                const minutes = minutesOver % 60;
                
                if (hours > 0) {{
                    return {{
                        text: `Due by ${{hours}}h ${{minutes}}m`,
                        status: 'due',
                        class: 'due'
                    }};
                }} else {{
                    return {{
                        text: `Due by ${{minutes}}m`,
                        status: 'due',
                        class: 'due'
                    }};
                }}
            }} else {{
                // More than 2 hours after end
                return {{
                    text: 'Overdue',
                    status: 'overdue',
                    class: 'overdue'
                }};
            }}
        }}

        function updateTimeRemaining() {{
            const now = Date.now();
            
            document.querySelectorAll('.task-time-display').forEach(el => {{
                const startTime = parseInt(el.dataset.startTime);
                const endTime = parseInt(el.dataset.endTime);
                const isActive = el.dataset.isActive === 'true';
                
                const timeInfo = calculateTimeDisplay(startTime, endTime, isActive);
                el.innerHTML = timeInfo.text;
                el.className = 'task-time-display time-remaining-badge ' + timeInfo.class;
            }});
        }}
        
        document.addEventListener('DOMContentLoaded', () => {{
            updateTimeRemaining();
            setInterval(updateTimeRemaining, 60000); // Update every minute
            
            // Initialize FAB for current view
            updateFAB('{current_view}');
            
            // Date validation for add task form
            const startDateInput = document.getElementById('startDate');
            const endDateInput = document.getElementById('endDate');
            const startTimeInput = document.getElementById('startTime');
            const endTimeInput = document.getElementById('endTime');
            const repeatSelect = document.getElementById('repeatSelect');
            const repeatEndDateGroup = document.getElementById('repeatEndDateGroup');
            
            if (startDateInput && endDateInput) {{
                startDateInput.addEventListener('change', function() {{
                    const startDate = new Date(this.value);
                    const endDate = new Date(endDateInput.value);
                    const maxEndDate = new Date(startDate);
                    maxEndDate.setDate(maxEndDate.getDate() + 1);
                    
                    if (endDate > maxEndDate) {{
                        endDateInput.value = maxEndDate.toISOString().split('T')[0];
                    }}
                    
                    // Ensure end date is not before start date
                    if (endDate < startDate) {{
                        endDateInput.value = this.value;
                    }}
                }});
                
                endDateInput.addEventListener('change', function() {{
                    const startDate = new Date(startDateInput.value);
                    const endDate = new Date(this.value);
                    const maxEndDate = new Date(startDate);
                    maxEndDate.setDate(maxEndDate.getDate() + 1);
                    
                    if (endDate > maxEndDate) {{
                        this.value = maxEndDate.toISOString().split('T')[0];
                    }}
                    
                    // Ensure end date is not before start date
                    if (endDate < startDate) {{
                        this.value = startDateInput.value;
                    }}
                }});
            }}
            
            // Time validation
            if (startTimeInput && endTimeInput) {{
                startTimeInput.addEventListener('change', function() {{
                    const startTime = this.value;
                    const endTime = endTimeInput.value;
                    
                    if (startDateInput.value === endDateInput.value && startTime >= endTime) {{
                        // If same day and start time is after end time, add 1 hour to end time
                        const start = new Date(`2000-01-01T${{startTime}}`);
                        start.setHours(start.getHours() + 1);
                        endTimeInput.value = start.toTimeString().slice(0,5);
                    }}
                }});
                
                endTimeInput.addEventListener('change', function() {{
                    const startTime = startTimeInput.value;
                    const endTime = this.value;
                    
                    if (startDateInput.value === endDateInput.value && endTime <= startTime) {{
                        // If same day and end time is before start time, add 1 hour to start time
                        const end = new Date(`2000-01-01T${{endTime}}`);
                        if (end.getHours() === 0) {{
                            // If end time is midnight, make start time 11 PM
                            startTimeInput.value = '23:00';
                        }} else {{
                            const start = new Date(`2000-01-01T${{endTime}}`);
                            start.setHours(start.getHours() - 1);
                            startTimeInput.value = start.toTimeString().slice(0,5);
                        }}
                    }}
                }});
            }}
            
            // Show/hide repeat end date based on repeat selection
            if (repeatSelect && repeatEndDateGroup) {{
                repeatSelect.addEventListener('change', function() {{
                    if (this.value === 'none') {{
                        repeatEndDateGroup.style.display = 'none';
                    }} else {{
                        repeatEndDateGroup.style.display = 'block';
                    }}
                }});
                
                // Initial state
                if (repeatSelect.value === 'none') {{
                    repeatEndDateGroup.style.display = 'none';
                }}
            }}
            
            // Similar for edit form
            const editRepeatSelect = document.getElementById('editTaskRepeat');
            const editRepeatEndDateGroup = document.getElementById('editRepeatEndDateGroup');
            
            if (editRepeatSelect && editRepeatEndDateGroup) {{
                editRepeatSelect.addEventListener('change', function() {{
                    if (this.value === 'none') {{
                        editRepeatEndDateGroup.style.display = 'none';
                    }} else {{
                        editRepeatEndDateGroup.style.display = 'block';
                    }}
                }});
                
                // Initial state for edit form
                if (editRepeatSelect.value === 'none') {{
                    editRepeatEndDateGroup.style.display = 'none';
                }}
            }}
            
            // Handle note notification checkbox
            const noteNotifyCheckbox = document.getElementById('noteNotifyEnabled');
            const noteIntervalGroup = document.getElementById('noteIntervalGroup');
            
            if (noteNotifyCheckbox && noteIntervalGroup) {{
                noteNotifyCheckbox.addEventListener('change', function() {{
                    noteIntervalGroup.style.display = this.checked ? 'block' : 'none';
                }});
            }}
        }});' if is_logged_in else ''}
    </script>
</body>
</html>
''', mimetype='text/html')

# ============= HELPER FUNCTIONS FOR RENDERING =============
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

def render_task_card(task):
    """Render a task card"""
    repeat_text = ''
    if task['repeat'] != 'none':
        if task['repeat'] == 'daily':
            repeat_text = 'Daily'
        elif task['repeat'] == 'weekly':
            day = task.get('repeat_day', 'Sunday')
            repeat_text = f"Weekly on {day}"
    else:
        repeat_text = 'None'
    
    repeat_badge = f"<span class='repeat-badge'><i class='fas fa-repeat'></i> {repeat_text}</span>"
    
    priority = task.get('priority', 15)
    priority_badge = f"<span class='priority-badge'>P{priority}</span>"
    
    notify_badge = ""
    if task.get('notify_enabled'):
        notify_badge = "<span class='notify-badge'><i class='fas fa-bell'></i> Notify</span>"
    
    # Get CSRF token
    import random
    import string
    csrf_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    
    edit_button = f"<button class='action-btn' onclick='openEditTaskModal(\"{task['id']}\")' title='Edit Task'><i class='fas fa-edit'></i></button>"
    
    add_subtask_button = f"<button class='action-btn' onclick='openAddSubtaskModal(\"{task['id']}\")' title='Add Subtask'><i class='fas fa-plus'></i></button>"
    
    complete_button = ''
    if task.get('is_active', True):
        complete_button = f"""
        <form method='POST' action='/complete_task' style='display:inline;'>
            <input type='hidden' name='task_id' value='{task['id']}'>
            <input type='hidden' name='csrf_token' value='{csrf_token}'>
            <button type='submit' class='action-btn' title='Complete'>
                <i class='fas fa-check'></i>
            </button>
        </form>"""
    else:
        complete_button = "<button class='action-btn disabled' title='Already Completed' disabled><i class='fas fa-check'></i></button>"
    
    delete_button = f"""
    <form method='POST' action='/delete_task' style='display:inline;'>
        <input type='hidden' name='task_id' value='{task['id']}'>
        <input type='hidden' name='csrf_token' value='{csrf_token}'>
        <button type='submit' class='action-btn' title='Delete'>
            <i class='fas fa-trash'></i>
        </button>
    </form>"""
    
    start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
    end_time = datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S')
    
    time_range = f"{start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"
    date_range = start_time.strftime('%b %d')
    end_date = end_time.strftime('%b %d')
    if date_range != end_date:
        date_range += ' - ' + end_date
    
    # Calculate subtask progress
    subtasks = task.get('subtasks', [])
    completed_subtasks = sum(1 for st in subtasks if st['completed'])
    total_subtasks = len(subtasks)
    progress_percentage = round((completed_subtasks / total_subtasks * 100)) if total_subtasks > 0 else 0
    
    subtasks_html = ""
    if subtasks:
        # Sort subtasks by priority
        subtasks.sort(key=lambda x: x.get('priority', 1))
        
        subtasks_list_html = ""
        for subtask in subtasks:
            completed_class = 'subtask-completed' if subtask['completed'] else ''
            subtask_number = subtask.get('priority', 1)
            
            subtask_number_badge = f"<span class='subtask-number-badge {'completed' if subtask['completed'] else ''}'>{subtask_number}</span>"
            
            subtask_edit_button = f"<button class='edit-subtask-btn' onclick='openEditSubtaskModal(\"{task['id']}\", \"{subtask['id']}\")' title='Edit Subtask'><i class='fas fa-edit'></i></button>"
            
            subtask_delete_button = f"""
            <form method='POST' action='/delete_subtask' style='display:inline;'>
                <input type='hidden' name='task_id' value='{task['id']}'>
                <input type='hidden' name='subtask_id' value='{subtask['id']}'>
                <input type='hidden' name='csrf_token' value='{csrf_token}'>
                <button type='submit' class='delete-subtask-btn' title='Delete Subtask'>
                    <i class='fas fa-trash'></i>
                </button>
            </form>"""
            
            subtask_description = f"<div class='subtask-description'>{format_text(subtask.get('description', ''))}</div>" if subtask.get('description') else ""
            
            complete_form = f"""
            <form method='POST' action='/complete_subtask' style='display:inline;'>
                <input type='hidden' name='task_id' value='{task['id']}'>
                <input type='hidden' name='subtask_id' value='{subtask['id']}'>
                <input type='hidden' name='csrf_token' value='{csrf_token}'>
                <button type='submit' class='subtask-complete-btn' title='Toggle Complete'>
                    {subtask_number_badge}
                </button>
            </form>"""
            
            subtasks_list_html += f"""
            <div class='subtask-item'>
                {complete_form}
                <details class='subtask-details-container'>
                    <summary class='subtask-title {completed_class}'>{subtask['title']}</summary>
                    {subtask_description}
                </details>
                <div class='subtask-actions'>
                    {subtask_edit_button}
                    {subtask_delete_button}
                </div>
            </div>"""
        
        subtasks_html = f"""
        <details class='subtasks-details'>
            <summary>
                <i class='fas fa-tasks'></i>
                Subtasks ({completed_subtasks}/{total_subtasks})
                <span class='details-toggle'></span>
            </summary>
            <div class='subtasks-content'>
                {subtasks_list_html}
            </div>
        </details>"""
    
    progress_html = ""
    if total_subtasks > 0:
        progress_html = f"""
        <div class='progress-display-container'>
            <div class='progress-circle' style='background: conic-gradient(var(--primary) {progress_percentage}%, var(--gray-light) 0%);'>
                <span style='font-size: 0.65rem; z-index: 1;'>{progress_percentage}%</span>
            </div>
            <div class='progress-text' style='margin-left: 8px; flex: 1;'>
                {completed_subtasks} of {total_subtasks} subtasks completed
            </div>
        </div>"""
    
    description = format_text(task.get('description', ''))
    
    # Check if this is a completed repeating task
    is_completed_repeating = task.get('is_completed_repeating', False)
    card_class = 'completed-repeating' if is_completed_repeating else ''
    
    next_occurrence_html = ''
    if is_completed_repeating and task.get('nextOccurrence'):
        next_date = datetime.strptime(task['nextOccurrence'], '%Y-%m-%d %H:%M:%S').strftime('%b %d, %Y')
        next_day = datetime.strptime(task['nextOccurrence'], '%Y-%m-%d %H:%M:%S').strftime('%A')
        next_time = f"{start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"
        next_occurrence_html = f"""
        <div class='next-occurrence-info'>
            <i class='fas fa-calendar-alt'></i>
            Next: {next_date} ({next_day}) at {next_time}
        </div>"""
    
    return f"""
    <div class='task-card consistent-card {card_class}'>
        <div class='task-header'>
            <div style='flex: 1;'>
                <div style='display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;'>
                    <h3 class='task-title'>{task['title']}</h3>
                    <div class='task-actions'>
                        {add_subtask_button}
                        {edit_button}
                        {complete_button}
                        {delete_button}
                    </div>
                </div>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <div>
                        <span class='task-date-range'>{date_range}</span>
                        <span class='task-time-range'>{time_range}</span>
                    </div>
                    <div class='task-time-display' 
                         data-start-time='{task["start_timestamp"]}' 
                         data-end-time='{task["end_timestamp"]}'
                         data-status='{task["status"]}'
                         data-time-display='{task["time_display"]}'
                         data-is-active='{'true' if task.get('is_active', True) else 'false'}'></div>
                </div>
            </div>
        </div>
        {'<p class="task-description">' + description + '</p>' if description else ''}
        
        {next_occurrence_html}
        
        {progress_html if progress_html else ''}
        
        {subtasks_html if subtasks_html else ''}
        
        <div class='task-meta'>
            {repeat_badge}
            {priority_badge}
            {notify_badge}
        </div>
    </div>"""

def render_note_card(note):
    """Render a note card"""
    note_id = note['id']
    
    # Get CSRF token
    import random
    import string
    csrf_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    
    created_at = datetime.strptime(note['createdAt'], '%Y-%m-%d %H:%M:%S').strftime('%b %d, %Y')
    updated_at = datetime.strptime(note['updatedAt'], '%Y-%m-%d %H:%M:%S').strftime('%b %d, %Y')
    
    notify_badge = ""
    if note.get('notify_enabled'):
        interval = note.get('notify_interval', 0)
        notify_badge = f"<span class='notify-badge'><i class='fas fa-bell'></i> Every {interval}h</span>"
    
    edit_button = f"<button class='note-action-btn' onclick='openEditNoteModal(\"{note_id}\")' title='Edit Note'><i class='fas fa-edit'></i></button>"

    delete_button = f"""
    <form method='POST' action='/delete_note' style='display:inline;'>
        <input type='hidden' name='note_id' value='{note_id}'>
        <input type='hidden' name='csrf_token' value='{csrf_token}'>
        <button type='submit' class='note-action-btn delete' title='Delete Note'>
            <i class='fas fa-trash'></i>
        </button>
    </form>"""

    move_up_button = f"""
    <form method='POST' action='/move_note' style='display:inline;'>
        <input type='hidden' name='direction' value='up'>
        <input type='hidden' name='note_id' value='{note_id}'>
        <input type='hidden' name='csrf_token' value='{csrf_token}'>
        <button type='submit' class='note-move-btn' title='Move Up' style='margin-left: 6px;'>
            <i class='fas fa-arrow-up'></i>
        </button>
    </form>"""

    move_down_button = f"""
    <form method='POST' action='/move_note' style='display:inline;'>
        <input type='hidden' name='direction' value='down'>
        <input type='hidden' name='note_id' value='{note_id}'>
        <input type='hidden' name='csrf_token' value='{csrf_token}'>
        <button type='submit' class='note-move-btn' title='Move Down'>
            <i class='fas fa-arrow-down'></i>
        </button>
    </form>"""

    description = f"<div class='note-description'>{format_text(note.get('description', ''))}</div>" if note.get('description') else ""

    return f"""
    <div class='note-card'>
        <details class='note-details'>
            <summary class='note-summary'>
                <div class='note-header'>
                    <h3 class='note-title'>{note['title']}</h3>
                    <div class='note-date'>Updated: {updated_at}</div>
                </div>
            </summary>
            <div class='note-content'>
                {description}
                <div class='note-footer'>
                    <div class='note-meta'>
                        <span class='note-date-badge'>Created: {created_at}</span>
                        {notify_badge}
                    </div>
                    <div class='note-actions'>
                        {move_down_button}
                        {move_up_button}
                        {edit_button}
                        {delete_button}
                    </div>
                </div>
            </div>
        </details>
    </div>"""

def render_history_view(history_items):
    """Render history view"""
    # Group history by date
    from collections import defaultdict
    grouped_history = defaultdict(list)
    
    for item in history_items:
        date = datetime.strptime(item['completedAt'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y')
        grouped_history[date].append(item)
    
    # Sort dates newest first
    sorted_dates = sorted(grouped_history.keys(), key=lambda x: datetime.strptime(x, '%B %d, %Y'), reverse=True)
    
    html_parts = []
    for date in sorted_dates:
        items = grouped_history[date]
        
        date_html = f"""
        <div class='history-date-group'>
            <details class='history-date-details'>
                <summary class='history-date-summary'>
                    <i class='fas fa-calendar'></i>{date}
                    <span class='details-toggle'>▼</span>
                </summary>
                <div class='history-date-content'>
                    <div class='history-items-container'>
        """
        
        for item in items:
            completion_details = datetime.strptime(item['completedAt'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y, %I:%M %p')
            description = format_text(item.get('description', ''))
            
            date_html += f"""
            <div class='history-card'>
                <div class='history-card-header'>
                    <div class='history-card-title'>
                        <i class='fas fa-tasks'></i>
                        {item['title']}
                    </div>
                    <div class='history-card-time'>{completion_details}</div>
                </div>
                {'<div class="history-card-description">' + description + '</div>' if description else ''}
                <div class='history-card-meta'>
                    <span class='history-meta-item'>Bucket: {item.get('bucket', 'today').capitalize()}</span>
                    <span class='history-meta-item'>Repeat: {'No' if item.get('repeat') == 'none' else item.get('repeat').capitalize()}</span>
                    <span class='history-meta-item'>Time: {item.get('time_range', '')}</span>
                    <span class='history-meta-item'>Priority: P{item.get('priority', 15)}</span>
                </div>
            </div>
            """
        
        date_html += """
                    </div>
                </div>
            </details>
        </div>
        """
        
        html_parts.append(date_html)
    
    return ''.join(html_parts)

# ============= ACTION ROUTES =============
@app.route('/login', methods=['POST'])
def login():
    """Handle login"""
    access_code = request.form.get('access_code', '').strip()
    config = db_execute("SELECT * FROM config WHERE key = 'access_code'")
    
    if config and config[0]['value'] == access_code:
        resp = Response('Login successful', status=302)
        resp.headers['Location'] = '/?login=true'
        resp.set_cookie('session_id', 'authenticated', max_age=86400)  # 24 hours
        return resp
    
    return Response('Invalid access code', status=302, headers={'Location': '/'})

@app.route('/logout', methods=['POST'])
def logout():
    """Handle logout"""
    resp = Response('Logged out', status=302, headers={'Location': '/'})
    resp.set_cookie('session_id', '', expires=0)
    return resp

@app.route('/change_code', methods=['POST'])
def change_code():
    """Change access code"""
    current_code = request.form.get('current_code', '').strip()
    new_code = request.form.get('new_code', '').strip()
    confirm_code = request.form.get('confirm_code', '').strip()
    
    config = db_execute("SELECT * FROM config WHERE key = 'access_code'")
    
    if not config or config[0]['value'] != current_code:
        return Response('Current access code is incorrect', status=302, headers={'Location': '/'})
    
    if new_code != confirm_code:
        return Response('New access codes do not match', status=302, headers={'Location': '/'})
    
    db_execute("UPDATE config SET value = ? WHERE key = 'access_code'", (new_code,))
    
    return Response('Access code changed successfully', status=302, headers={'Location': '/'})

@app.route('/add_task', methods=['POST'])
def add_task():
    """Add a new task"""
    # Check if user is logged in
    if request.cookies.get('session_id') != 'authenticated':
        return Response('Unauthorized', status=401)
    
    import uuid
    import html
    
    task_id = f"task_{uuid.uuid4().hex}_{int(time.time())}"
    title = html.escape(request.form.get('title', '').strip())
    description = html.escape(request.form.get('description', '').strip())
    priority = int(request.form.get('priority', 15))
    repeat = request.form.get('repeat', 'none')
    notify_enabled = 1 if request.form.get('notify_enabled') == 'on' else 0
    
    # Start date and time
    start_date = request.form.get('start_date', datetime.now().strftime('%Y-%m-%d'))
    start_time = request.form.get('start_time', datetime.now().strftime('%H:%M'))
    start_datetime = f"{start_date} {start_time}:00"
    
    # End date and time
    end_date = request.form.get('end_date', start_date)
    end_time = request.form.get('end_time', (datetime.now() + timedelta(hours=1)).strftime('%H:%M'))
    end_datetime = f"{end_date} {end_time}:00"
    
    repeat_day = None
    if repeat == 'weekly':
        repeat_day = datetime.now().strftime('%A')
    
    repeat_end_date = request.form.get('repeat_end_date')
    if repeat_end_date:
        repeat_end_date = f"{repeat_end_date} 23:59:59"
    
    # Insert task
    db_execute('''
        INSERT INTO tasks (id, title, description, priority, repeat, repeat_day, repeat_end_date,
                          start_time, end_time, notify_enabled, created_at, next_occurrence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, title, description, priority, repeat, repeat_day, repeat_end_date,
          start_datetime, end_datetime, notify_enabled, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
          datetime.now().strftime('%Y-%m-%d 00:00:00') if repeat != 'none' else None))
    
    # Send Telegram notification
    if notify_enabled:
        notification_message = f"""
✅ <b>New Task Added</b>
📝 <b>{title}</b>
📅 Date: {datetime.strptime(start_date, '%Y-%m-%d').strftime('%B %d, %Y')}
🕐 Time: {datetime.strptime(start_time, '%H:%M').strftime('%I:%M %p')}
🔔 Notifications: Enabled (10 reminders before start)
"""
        send_telegram_message(notification_message)
    
    return Response('Task added', status=302, headers={'Location': '/?view=tasks'})

@app.route('/add_note', methods=['POST'])
def add_note():
    """Add a new note"""
    # Check if user is logged in
    if request.cookies.get('session_id') != 'authenticated':
        return Response('Unauthorized', status=401)
    
    import uuid
    import html
    
    note_id = f"note_{uuid.uuid4().hex}_{int(time.time())}"
    title = html.escape(request.form.get('title', 'Untitled Note').strip())
    description = html.escape(request.form.get('description', '').strip())
    notify_enabled = 1 if request.form.get('notify_enabled') == 'on' else 0
    notify_interval = int(request.form.get('notify_interval', 12))
    
    # Get max priority
    notes = db_execute("SELECT MAX(priority) as max_priority FROM notes")
    max_priority = notes[0]['max_priority'] if notes and notes[0]['max_priority'] else 0
    
    # Insert note
    db_execute('''
        INSERT INTO notes (id, title, description, priority, created_at, updated_at,
                          notify_enabled, notify_interval)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (note_id, title, description, max_priority + 1,
          datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
          datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
          notify_enabled, notify_interval))
    
    # Send Telegram notification
    if notify_enabled and notify_interval > 0:
        notification_message = f"""
📝 <b>New Note Added</b>
📌 <b>{title}</b>
🔄 Interval: Every {notify_interval} hours
🔔 You'll receive regular reminders
"""
        send_telegram_message(notification_message)
    
    return Response('Note added', status=302, headers={'Location': '/?view=notes'})

@app.route('/complete_task', methods=['POST'])
def complete_task():
    """Complete a task"""
    task_id = request.form.get('task_id')
    
    # Get task
    task = db_execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        return Response('Task not found', status=302, headers={'Location': '/?view=tasks'})
    
    task = task[0]
    
    # Update task as completed
    db_execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
    
    # Add to history
    start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
    end_time = datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S')
    time_range = f"{start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"
    
    db_execute('''
        INSERT INTO history (task_id, title, description, type, bucket, repeat,
                            completed_at, time_range, priority)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, task['title'], task['description'], 'task', task['bucket'],
          task['repeat'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
          time_range, task['priority']))
    
    # Send completion notification
    notification_message = f"""
✅ <b>Task Completed!</b>
📝 <b>{task['title']}</b>
⏰ Time: {datetime.now().strftime('%I:%M %p')}
📅 Date: {datetime.now().strftime('%B %d, %Y')}
"""
    send_telegram_message(notification_message)
    
    return Response('Task completed', status=302, headers={'Location': '/?view=tasks'})

# Additional routes would be added here for other actions...

# ============= INITIALIZE AND START =============
def initialize_bot():
    """Initialize the bot"""
    print("=" * 60)
    print("🤖 Task Tracker Bot - Initializing")
    print("=" * 60)
    
    try:
        # Get bot info
        bot_info = bot.get_me()
        print(f"✅ Bot: @{bot_info.username} (ID: {bot_info.id})")
        
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

<b>Features activated:</b>
• Task reminders (10 minutes before start)
• Note reminders (custom intervals)
• Daily task reports (8 AM)

Send /help for commands.
"""
        send_telegram_message(startup_msg)
        print("✅ Startup message sent")
        
    except Exception as e:
        print(f"❌ Initialization error: {e}")
    
    print("=" * 60)
    print("✅ Bot initialized successfully")
    print("=" * 60)

if __name__ == '__main__':
    # Initialize bot
    initialize_bot()
    
    # Start Flask app
    port = int(os.getenv('PORT', 8000))
    print(f"🌐 Starting web server on port {port}...")
    
    # Start Telegram polling in separate thread
    try:
        polling_thread = threading.Thread(target=bot.polling, kwargs={'none_stop': True, 'interval': 1}, daemon=True)
        polling_thread.start()
        print("✅ Telegram polling started")
    except Exception as e:
        print(f"⚠️ Could not start polling: {e}")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
