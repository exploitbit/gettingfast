"""
Simplified Task Tracker with Telegram Bot - IST Timezone
"""

import os
import sqlite3
import threading
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, Response, render_template_string
import telebot
import time

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"
ADMIN_CODE = "1234"

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')

# Initialize Flask and Telegram bot
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# ============= DATABASE SETUP =============
def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect('tasks.db')
    c = conn.cursor()
    
    # Tasks table
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME NOT NULL,
            completed INTEGER DEFAULT 0,
            notify_enabled INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_notified_minute INTEGER DEFAULT -1
        )
    ''')
    
    # History table
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            title TEXT,
            completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks (id)
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
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('access_code', ?)", (ADMIN_CODE,))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('daily_summary', '1')")
    
    conn.commit()
    conn.close()

init_db()

# ============= DATABASE HELPER FUNCTIONS =============
def get_db():
    """Get database connection"""
    conn = sqlite3.connect('tasks.db')
    conn.row_factory = sqlite3.Row
    return conn

def db_query(query, params=(), fetch_one=False):
    """Execute database query"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    
    if query.strip().upper().startswith('SELECT'):
        if fetch_one:
            result = cursor.fetchone()
        else:
            result = cursor.fetchall()
    else:
        conn.commit()
        result = cursor.lastrowid
    
    conn.close()
    return result

# Helper to convert Row to dict
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
def send_telegram_message(text):
    """Send message to Telegram"""
    try:
        bot.send_message(USER_ID, text, parse_mode='HTML')
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
        
        # Get active tasks with notifications enabled
        tasks = db_query('''
            SELECT * FROM tasks 
            WHERE completed = 0 
            AND notify_enabled = 1
            AND datetime(start_time) > datetime('now', '-1 hour')
            ORDER BY start_time
        ''')
        
        print(f"📋 Found {len(tasks)} active tasks")
        
        for task_row in tasks:
            try:
                # Convert Row to dict
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
                        message = f"⏰ <b>Task Reminder</b>\n"
                        message += f"📝 {task_title}\n"
                        message += f"🕐 Starts in {minutes_until_start} minute"
                        if minutes_until_start > 1:
                            message += "s"
                        message += f"\n📅 {start_time.strftime('%I:%M %p')} IST"
                        
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

def send_daily_summary():
    """Send daily task summary"""
    try:
        now = get_ist_time()
        today = now.strftime('%Y-%m-%d')
        
        # Get today's tasks
        tasks = db_query('''
            SELECT * FROM tasks 
            WHERE date(start_time) = ?
            ORDER BY start_time
        ''', (today,))
        
        if not tasks:
            message = f"📅 <b>Daily Summary - {now.strftime('%B %d, %Y')}</b>\n"
            message += "No tasks for today! 🎉\n"
            message += f"⏰ {now.strftime('%I:%M %p')} IST"
            send_telegram_message(message)
            return
        
        completed = sum(1 for t in tasks if t['completed'])
        total = len(tasks)
        
        message = f"📅 <b>Daily Summary - {now.strftime('%B %d, %Y')}</b>\n"
        message += f"📊 {completed}/{total} tasks completed\n"
        message += f"⏰ {now.strftime('%I:%M %p')} IST\n\n"
        
        for task_row in tasks:
            task = row_to_dict(task_row)
            if not task:
                continue
            status = "✅" if task['completed'] else "❌"
            start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
            start_time = IST.localize(start_time)
            message += f"{status} {task['title']} ({start_time.strftime('%I:%M %p')})\n"
        
        send_telegram_message(message)
        
    except Exception as e:
        print(f"❌ Daily summary error: {e}")

def scheduler_thread():
    """Run scheduler in background thread"""
    print("🔄 Starting scheduler thread in IST...")
    
    while True:
        try:
            # Check notifications every minute
            check_and_send_notifications()
            
            # Check for daily summary at 8:00 AM IST
            now = get_ist_time()
            
            # Debug: Print current time
            if now.minute % 15 == 0:  # Every 15 minutes
                print(f"⏰ Current IST time: {now.strftime('%H:%M:%S')}")
            
            if now.hour == 8 and now.minute == 0:
                setting = db_query("SELECT value FROM settings WHERE key = 'daily_summary'", fetch_one=True)
                if setting and setting['value'] == '1':
                    print("📅 Sending daily summary...")
                    send_daily_summary()
                    time.sleep(120)  # Sleep 2 minutes to avoid duplicate
            
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
    """Send welcome message"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized")
        return
    
    now = get_ist_time()
    
    welcome = f"""
🤖 <b>Task Tracker Bot</b>
⏰ Time: {now.strftime('%I:%M %p')} IST
📅 Date: {now.strftime('%B %d, %Y')}

<b>Commands:</b>
/today - View today's tasks
/add - Add new task (format: /add Title @ HH:MM-HH:MM)
/summary - Get daily summary
/test - Test notification
/time - Check current IST time
/help - Show this message

<b>Notifications:</b>
• 1 notification per minute for 10 minutes before task starts
• All times in IST

<b>Web Interface:</b>
https://patient-maxie-sandip232-786edcb8.koyeb.app/
"""
    bot.reply_to(message, welcome, parse_mode='HTML')

@bot.message_handler(commands=['today'])
def send_today_tasks(message):
    """Send today's tasks"""
    if str(message.chat.id) != USER_ID:
        return
    
    now = get_ist_time()
    today = now.strftime('%Y-%m-%d')
    tasks = db_query('''
        SELECT * FROM tasks 
        WHERE date(start_time) = ?
        ORDER BY start_time
    ''', (today,))
    
    if not tasks:
        bot.reply_to(message, f"📅 No tasks for today ({now.strftime('%B %d')})")
        return
    
    response = f"📅 <b>Today's Tasks ({now.strftime('%B %d')})</b>\n"
    response += f"⏰ {now.strftime('%I:%M %p')} IST\n\n"
    
    for task_row in tasks:
        task = row_to_dict(task_row)
        if not task:
            continue
        status = "✅" if task['completed'] else "❌"
        start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
        start_time = IST.localize(start_time)
        end_time = datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S')
        end_time = IST.localize(end_time)
        
        response += f"{status} <b>{task['title']}</b>\n"
        response += f"   ⏰ {start_time.strftime('%I:%M')} - {end_time.strftime('%I:%M %p')}\n\n"
    
    bot.reply_to(message, response, parse_mode='HTML')

@bot.message_handler(commands=['add'])
def add_task_from_telegram(message):
    """Add task from Telegram"""
    if str(message.chat.id) != USER_ID:
        return
    
    try:
        parts = message.text.split(' ', 2)
        if len(parts) < 3:
            bot.reply_to(message, "Format: /add Title @ HH:MM-HH:MM\nExample: /add Meeting @ 14:00-15:00")
            return
        
        title = parts[1]
        time_part = parts[2].replace('@ ', '')
        
        if '-' not in time_part:
            bot.reply_to(message, "Format: /add Title @ HH:MM-HH:MM")
            return
        
        start_str, end_str = time_part.split('-')
        today = get_ist_time().strftime('%Y-%m-%d')
        
        # Convert to IST datetime
        start_dt = parse_ist_time(start_str, today)
        end_dt = parse_ist_time(end_str, today)
        
        start_time = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_time = end_dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Insert task
        task_id = db_query(
            "INSERT INTO tasks (title, start_time, end_time) VALUES (?, ?, ?)",
            (title, start_time, end_time)
        )
        
        # Calculate minutes until start
        now = get_ist_time()
        minutes_until = int((start_dt - now).total_seconds() / 60)
        
        # Send confirmation
        response = f"✅ <b>Task Added</b>\n"
        response += f"📝 {title}\n"
        response += f"⏰ {start_str} - {end_str} IST\n"
        response += f"📅 {today}\n"
        
        if 1 <= minutes_until <= 10:
            response += f"\n🔔 You'll get notifications starting in {minutes_until} minutes"
        
        bot.reply_to(message, response, parse_mode='HTML')
        
        # Send immediate notification if starting soon
        if 1 <= minutes_until <= 10:
            notif_msg = f"⏰ <b>New Task (starts in {minutes_until} min)</b>\n"
            notif_msg += f"📝 {title}\n"
            notif_msg += f"🕐 {start_str} - {end_str} IST"
            send_telegram_message(notif_msg)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['summary'])
def send_summary(message):
    """Send summary"""
    if str(message.chat.id) != USER_ID:
        return
    
    send_daily_summary()
    bot.reply_to(message, "📊 Summary sent!")

@bot.message_handler(commands=['test'])
def test_notification(message):
    """Test notification"""
    if str(message.chat.id) != USER_ID:
        return
    
    now = get_ist_time()
    test_msg = "🔔 <b>Test Notification</b>\n"
    test_msg += "✅ Bot is working!\n"
    test_msg += f"⏰ {now.strftime('%H:%M:%S')} IST\n"
    test_msg += f"📅 {now.strftime('%B %d, %Y')}"
    
    if send_telegram_message(test_msg):
        bot.reply_to(message, "✅ Test notification sent!")
    else:
        bot.reply_to(message, "❌ Failed to send test")

@bot.message_handler(commands=['time'])
def send_time(message):
    """Send current IST time"""
    if str(message.chat.id) != USER_ID:
        return
    
    now = get_ist_time()
    time_msg = f"⏰ <b>Current Time</b>\n"
    time_msg += f"IST: {now.strftime('%I:%M:%S %p')}\n"
    time_msg += f"Date: {now.strftime('%B %d, %Y')}\n"
    time_msg += f"Timezone: Asia/Kolkata"
    
    bot.reply_to(message, time_msg, parse_mode='HTML')

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

# ============= FLASK WEB APP =============
@app.route('/')
def index():
    """Main web interface"""
    # Check if logged in
    logged_in = request.cookies.get('logged_in') == 'true'
    
    if not logged_in:
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Task Tracker - Login</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    font-family: -apple-system, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .login-box {
                    background: white;
                    padding: 30px;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                    width: 100%;
                    max-width: 350px;
                }
                h1 {
                    color: #333;
                    text-align: center;
                    margin-bottom: 30px;
                    font-size: 24px;
                }
                .logo {
                    text-align: center;
                    font-size: 48px;
                    color: #667eea;
                    margin-bottom: 20px;
                }
                input {
                    width: 100%;
                    padding: 12px;
                    margin: 10px 0;
                    border: 2px solid #ddd;
                    border-radius: 8px;
                    font-size: 16px;
                }
                input:focus {
                    outline: none;
                    border-color: #667eea;
                }
                button {
                    width: 100%;
                    padding: 14px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    border-radius: 8px;
                    cursor: pointer;
                    font-size: 16px;
                    font-weight: 600;
                    margin-top: 10px;
                }
                .error {
                    color: #ff4757;
                    text-align: center;
                    margin: 10px 0;
                    font-size: 14px;
                }
                .info {
                    text-align: center;
                    color: #666;
                    font-size: 14px;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="login-box">
                <div class="logo">📱</div>
                <h1>Task Tracker</h1>
                <form method="POST" action="/login">
                    <input type="password" name="code" placeholder="Enter Access Code" required>
                    <button type="submit">Login</button>
                </form>
                {% if error %}
                <div class="error">{{ error }}</div>
                {% endif %}
                <div class="info">
                    Default code: 1234
                </div>
            </div>
        </body>
        </html>
        ''', error=request.args.get('error', ''))
    
    # Get current view
    view = request.args.get('view', 'tasks')
    
    # Get current IST time
    now = get_ist_time()
    today = now.strftime('%Y-%m-%d')
    
    # Get tasks for today
    tasks_rows = db_query('''
        SELECT * FROM tasks 
        WHERE date(start_time) = ?
        ORDER BY start_time
    ''', (today,))
    
    # Get history
    history = db_query('''
        SELECT h.*, t.title as task_title 
        FROM history h
        LEFT JOIN tasks t ON h.task_id = t.id
        ORDER BY h.completed_at DESC
        LIMIT 20
    ''')
    
    # Get settings
    settings = {}
    setting_rows = db_query("SELECT key, value FROM settings")
    for row in setting_rows:
        row_dict = row_to_dict(row)
        if row_dict:
            settings[row_dict['key']] = row_dict['value']
    
    # Calculate stats
    tasks = [row_to_dict(row) for row in tasks_rows if row_to_dict(row)]
    completed_today = sum(1 for t in tasks if t['completed'])
    pending_today = len(tasks) - completed_today
    
    # Process tasks for display
    processed_tasks = []
    for task in tasks:
        start_dt = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
        start_dt = IST.localize(start_dt)
        end_dt = datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S')
        end_dt = IST.localize(end_dt)
        
        minutes_until = int((start_dt - now).total_seconds() / 60) if not task['completed'] else None
        
        processed_tasks.append({
            'id': task['id'],
            'title': task['title'],
            'start_time': task['start_time'],
            'end_time': task['end_time'],
            'start_display': start_dt.strftime('%I:%M %p'),
            'end_display': end_dt.strftime('%I:%M %p'),
            'completed': task['completed'],
            'notify_enabled': task['notify_enabled'],
            'minutes_until': minutes_until,
            'is_upcoming': minutes_until is not None and 1 <= minutes_until <= 10
        })
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Task Tracker</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {
                --primary: #4361ee;
                --secondary: #3a0ca3;
                --success: #4cc9f0;
                --danger: #f72585;
                --warning: #f8961e;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, sans-serif;
                background: #f5f5f7;
                color: #333;
                padding-bottom: 80px;
            }
            
            /* Header */
            .header {
                background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                color: white;
                padding: 15px;
                position: sticky;
                top: 0;
                z-index: 100;
            }
            
            .header-top {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            
            .header h1 {
                font-size: 20px;
                font-weight: 600;
            }
            
            .time-display {
                font-size: 14px;
                background: rgba(255,255,255,0.2);
                padding: 4px 8px;
                border-radius: 12px;
            }
            
            /* Tabs */
            .tabs {
                display: flex;
                background: rgba(255,255,255,0.1);
                border-radius: 10px;
                padding: 3px;
            }
            
            .tab {
                flex: 1;
                text-align: center;
                padding: 8px;
                border-radius: 8px;
                font-size: 14px;
                cursor: pointer;
            }
            
            .tab.active {
                background: white;
                color: var(--primary);
            }
            
            /* Content */
            .content {
                padding: 15px;
            }
            
            .section {
                display: none;
            }
            
            .section.active {
                display: block;
            }
            
            /* Stats */
            .stats {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 10px;
                margin-bottom: 20px;
            }
            
            .stat-card {
                background: white;
                border-radius: 12px;
                padding: 15px;
                text-align: center;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            }
            
            .stat-number {
                font-size: 24px;
                font-weight: bold;
                color: var(--primary);
            }
            
            .stat-label {
                font-size: 12px;
                color: #666;
            }
            
            /* Forms */
            .form-card {
                background: white;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            }
            
            .form-title {
                font-size: 16px;
                font-weight: 600;
                margin-bottom: 15px;
                color: #333;
            }
            
            .form-group {
                margin-bottom: 15px;
            }
            
            .form-label {
                display: block;
                margin-bottom: 5px;
                font-size: 14px;
                font-weight: 500;
            }
            
            .form-input {
                width: 100%;
                padding: 12px;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                font-size: 16px;
            }
            
            .time-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
            }
            
            /* Buttons */
            .btn {
                padding: 14px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                width: 100%;
            }
            
            .btn-primary {
                background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                color: white;
            }
            
            /* Task Cards */
            .task-card {
                background: white;
                border-radius: 12px;
                padding: 15px;
                margin-bottom: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
                border-left: 4px solid var(--primary);
            }
            
            .task-card.completed {
                border-left-color: var(--success);
                opacity: 0.8;
            }
            
            .task-card.upcoming {
                border-left-color: var(--warning);
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.9; }
            }
            
            .task-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 10px;
            }
            
            .task-title {
                font-size: 16px;
                font-weight: 600;
            }
            
            .task-status {
                font-size: 12px;
                padding: 4px 8px;
                border-radius: 20px;
                font-weight: 600;
            }
            
            .status-pending {
                background: #fff3cd;
                color: #856404;
            }
            
            .status-completed {
                background: #d4edda;
                color: #155724;
            }
            
            .task-time {
                display: flex;
                align-items: center;
                gap: 8px;
                color: #666;
                font-size: 14px;
                margin: 8px 0;
            }
            
            .task-notice {
                font-size: 12px;
                color: var(--warning);
                margin: 5px 0;
            }
            
            .task-actions {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
                margin-top: 15px;
            }
            
            .action-btn {
                padding: 10px;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            }
            
            .btn-success {
                background: var(--success);
                color: white;
            }
            
            .btn-danger {
                background: var(--danger);
                color: white;
            }
            
            /* Notification Banner */
            .notification-banner {
                background: linear-gradient(135deg, var(--warning) 0%, #ff6b6b 100%);
                color: white;
                padding: 12px 15px;
                border-radius: 12px;
                margin-bottom: 20px;
            }
            
            /* FAB */
            .fab {
                position: fixed;
                bottom: 20px;
                right: 20px;
                width: 56px;
                height: 56px;
                background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                color: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
                cursor: pointer;
                box-shadow: 0 4px 15px rgba(67, 97, 238, 0.3);
                z-index: 100;
            }
        </style>
    </head>
    <body>
        <!-- Header -->
        <div class="header">
            <div class="header-top">
                <h1><i class="fas fa-tasks"></i> Task Tracker</h1>
                <div class="time-display">
                    {{ now.strftime('%I:%M %p') }} IST
                </div>
            </div>
            
            <div class="tabs">
                <div class="tab {{ 'active' if view == 'tasks' }}" onclick="switchView('tasks')">
                    <i class="fas fa-list"></i> Tasks
                </div>
                <div class="tab {{ 'active' if view == 'history' }}" onclick="switchView('history')">
                    <i class="fas fa-history"></i> History
                </div>
                <div class="tab {{ 'active' if view == 'settings' }}" onclick="switchView('settings')">
                    <i class="fas fa-cog"></i> Settings
                </div>
            </div>
        </div>
        
        <!-- Content -->
        <div class="content">
            <!-- Tasks View -->
            <div id="tasksView" class="section {{ 'active' if view == 'tasks' }}">
                <!-- Notification Banner -->
                <div class="notification-banner">
                    <div style="font-weight: 600; margin-bottom: 5px;">
                        <i class="fas fa-bell"></i> Notifications Active
                    </div>
                    <div style="font-size: 12px;">
                        You'll get 1 notification per minute for 10 minutes before each task starts
                    </div>
                </div>
                
                <!-- Stats -->
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-number">{{ tasks|length }}</div>
                        <div class="stat-label">Total</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{{ completed_today }}</div>
                        <div class="stat-label">Completed</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{{ pending_today }}</div>
                        <div class="stat-label">Pending</div>
                    </div>
                </div>
                
                <!-- Add Task Form -->
                <div class="form-card">
                    <div class="form-title">
                        <i class="fas fa-plus-circle"></i> Add New Task (IST)
                    </div>
                    <form method="POST" action="/add_task" id="taskForm">
                        <div class="form-group">
                            <label class="form-label">Task Title</label>
                            <input type="text" class="form-input" name="title" placeholder="What needs to be done?" required>
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Time (IST)</label>
                            <div class="time-row">
                                <div>
                                    <input type="time" class="form-input" name="start_time" id="startTime" required>
                                    <div style="font-size: 11px; color: #666; text-align: center; margin-top: 3px;">Start</div>
                                </div>
                                <div>
                                    <input type="time" class="form-input" name="end_time" id="endTime" required>
                                    <div style="font-size: 11px; color: #666; text-align: center; margin-top: 3px;">End</div>
                                </div>
                            </div>
                        </div>
                        
                        <div style="display: flex; align-items: center; gap: 10px; margin: 15px 0;">
                            <input type="checkbox" name="notify_enabled" id="notifyEnabled" checked style="width: 20px; height: 20px;">
                            <label for="notifyEnabled" style="font-size: 14px;">Enable notifications</label>
                        </div>
                        
                        <button type="submit" class="btn btn-primary">
                            <i class="fas fa-plus"></i> Add Task
                        </button>
                    </form>
                </div>
                
                <!-- Tasks List -->
                <div>
                    <div style="font-size: 16px; font-weight: 600; margin-bottom: 15px; color: #333;">
                        <i class="fas fa-calendar-day"></i> Today's Tasks
                        <span style="font-size: 12px; color: #666; font-weight: normal; margin-left: 8px;">
                            {{ now.strftime('%B %d') }} IST
                        </span>
                    </div>
                    
                    {% if not processed_tasks %}
                    <div style="text-align: center; padding: 40px 20px; color: #666;">
                        <i class="fas fa-clipboard-list" style="font-size: 48px; opacity: 0.5;"></i>
                        <p>No tasks for today</p>
                    </div>
                    {% endif %}
                    
                    {% for task in processed_tasks %}
                    <div class="task-card {{ 'completed' if task.completed }} {{ 'upcoming' if task.is_upcoming and not task.completed }}">
                        <div class="task-header">
                            <div class="task-title">{{ task.title }}</div>
                            <div class="task-status {{ 'status-completed' if task.completed else 'status-pending' }}">
                                {{ '✅ Completed' if task.completed else '⏳ Pending' }}
                            </div>
                        </div>
                        
                        <div class="task-time">
                            <i class="far fa-clock"></i>
                            {{ task.start_display }} - {{ task.end_display }} IST
                        </div>
                        
                        {% if task.is_upcoming and not task.completed %}
                        <div class="task-notice">
                            <i class="fas fa-bell"></i>
                            Notifications active: Starts in {{ task.minutes_until }} minute{{ 's' if task.minutes_until > 1 else '' }}
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
                            
                            <form method="POST" action="/delete_task" style="display: contents;">
                                <input type="hidden" name="task_id" value="{{ task.id }}">
                                <button type="submit" class="action-btn btn-danger" onclick="return confirm('Delete this task?')">
                                    <i class="fas fa-trash"></i> Delete
                                </button>
                            </form>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
            
            <!-- History View -->
            <div id="historyView" class="section {{ 'active' if view == 'history' }}">
                <div style="font-size: 16px; font-weight: 600; margin-bottom: 15px; color: #333;">
                    <i class="fas fa-history"></i> Task History
                </div>
                
                {% if not history %}
                <div style="text-align: center; padding: 40px 20px; color: #666;">
                    <i class="fas fa-history" style="font-size: 48px; opacity: 0.5;"></i>
                    <p>No completed tasks yet</p>
                </div>
                {% endif %}
                
                {% for item in history %}
                {% set item_dict = row_to_dict(item) %}
                {% if item_dict %}
                <div style="background: white; border-radius: 12px; padding: 15px; margin-bottom: 10px; border-left: 4px solid var(--success);">
                    <div style="font-weight: 600; margin-bottom: 5px;">
                        {{ item_dict.task_title or item_dict.title }}
                    </div>
                    <div style="font-size: 12px; color: #666;">
                        <i class="far fa-calendar-check"></i>
                        {{ datetime.strptime(item_dict.completed_at, '%Y-%m-%d %H:%M:%S').strftime('%B %d, %I:%M %p') }} IST
                    </div>
                </div>
                {% endif %}
                {% endfor %}
            </div>
            
            <!-- Settings View -->
            <div id="settingsView" class="section {{ 'active' if view == 'settings' }}">
                <div class="form-card">
                    <div class="form-title">
                        <i class="fas fa-bell"></i> Notifications
                    </div>
                    
                    <div style="margin-bottom: 20px; padding: 12px; background: #f8f9fa; border-radius: 8px;">
                        <div style="font-weight: 600; margin-bottom: 5px; color: var(--primary);">
                            <i class="fas fa-info-circle"></i> Notification Schedule
                        </div>
                        <div style="font-size: 14px;">
                            1 notification per minute for 10 minutes before each task starts
                        </div>
                    </div>
                    
                    <form method="POST" action="/toggle_setting">
                        <input type="hidden" name="key" value="daily_summary">
                        <div style="display: flex; justify-content: space-between; align-items: center; padding: 15px 0; border-bottom: 1px solid #eee;">
                            <div>
                                <div style="font-weight: 600; font-size: 15px;">Daily Summary</div>
                                <div style="font-size: 12px; color: #666;">Send daily summary at 8:00 AM IST</div>
                            </div>
                            <div style="position: relative; width: 50px; height: 24px;">
                                <input type="checkbox" name="enabled" {{ 'checked' if settings.get('daily_summary') == '1' }} 
                                       onchange="this.form.submit()" 
                                       style="position: absolute; opacity: 0; width: 0; height: 0;">
                                <span style="position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: {{ '#4cc9f0' if settings.get('daily_summary') == '1' else '#ccc' }}; border-radius: 24px; transition: .4s;"></span>
                                <span style="position: absolute; content: ''; height: 16px; width: 16px; left: {{ '26px' if settings.get('daily_summary') == '1' else '4px' }}; bottom: 4px; background-color: white; border-radius: 50%; transition: .4s;"></span>
                            </div>
                        </div>
                    </form>
                </div>
                
                <div class="form-card">
                    <div class="form-title">
                        <i class="fas fa-key"></i> Security
                    </div>
                    
                    <form method="POST" action="/change_code">
                        <div class="form-group">
                            <label class="form-label">New Access Code</label>
                            <input type="password" class="form-input" name="new_code" placeholder="Enter new code" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Confirm Code</label>
                            <input type="password" class="form-input" name="confirm_code" placeholder="Confirm new code" required>
                        </div>
                        <button type="submit" class="btn btn-primary">
                            <i class="fas fa-save"></i> Change Access Code
                        </button>
                    </form>
                </div>
                
                <div class="form-card">
                    <div class="form-title">
                        <i class="fab fa-telegram"></i> Telegram Bot
                    </div>
                    <div style="font-size: 14px; line-height: 1.5;">
                        <div style="margin-bottom: 10px;">
                            <strong>User ID:</strong> {{ USER_ID }}
                        </div>
                        <div style="margin-bottom: 10px;">
                            <strong>Status:</strong> 
                            <span style="color: var(--success);">✅ Connected</span>
                        </div>
                        <div style="font-size: 13px; color: #666;">
                            Send /start to your bot to get commands
                        </div>
                    </div>
                </div>
                
                <a href="/logout" style="display: block; background: var(--danger); color: white; padding: 14px; border-radius: 8px; text-align: center; text-decoration: none; margin-top: 20px; font-weight: 600;">
                    <i class="fas fa-sign-out-alt"></i> Logout
                </a>
            </div>
        </div>
        
        <!-- FAB -->
        <div class="fab" onclick="document.querySelector('#taskForm').scrollIntoView({behavior: 'smooth'})">
            <i class="fas fa-plus"></i>
        </div>
        
        <script>
            // Set default times
            document.addEventListener('DOMContentLoaded', function() {
                // Set start time to next hour in IST
                const now = new Date();
                const istOffset = 5.5 * 60 * 60 * 1000; // IST is UTC+5:30
                const istTime = new Date(now.getTime() + istOffset);
                
                // Round to next hour
                const nextHour = new Date(istTime);
                nextHour.setHours(nextHour.getHours() + 1, 0, 0, 0);
                
                const startTime = document.getElementById('startTime');
                const endTime = document.getElementById('endTime');
                
                if (startTime && !startTime.value) {
                    startTime.value = nextHour.toTimeString().slice(0,5);
                }
                
                if (endTime && !endTime.value) {
                    const start = new Date(`2000-01-01T${startTime.value}:00`);
                    start.setHours(start.getHours() + 1);
                    endTime.value = start.toTimeString().slice(0,5);
                }
                
                // Update time display
                function updateTime() {
                    const timeElements = document.querySelectorAll('.time-display');
                    const istTime = new Date(new Date().getTime() + (5.5 * 60 * 60 * 1000));
                    const timeString = istTime.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                    timeElements.forEach(el => {
                        el.textContent = timeString + ' IST';
                    });
                }
                
                updateTime();
                setInterval(updateTime, 60000);
            });
            
            function switchView(view) {
                window.location.href = '/?view=' + view;
            }
        </script>
    </body>
    </html>
    ''', 
    tasks=processed_tasks, 
    history=history, 
    settings=settings, 
    view=view, 
    datetime=datetime,
    now=now,
    USER_ID=USER_ID,
    completed_today=completed_today,
    pending_today=pending_today,
    row_to_dict=row_to_dict)

# ============= ACTION ROUTES =============
@app.route('/login', methods=['POST'])
def login():
    """Handle login"""
    code = request.form.get('code', '')
    
    setting = db_query("SELECT value FROM settings WHERE key = 'access_code'", fetch_one=True)
    setting_dict = row_to_dict(setting)
    correct_code = setting_dict['value'] if setting_dict else ADMIN_CODE
    
    if code == correct_code:
        resp = Response('', status=302)
        resp.headers['Location'] = '/'
        resp.set_cookie('logged_in', 'true', max_age=86400*30, httponly=True)
        return resp
    
    return Response('', status=302, headers={'Location': '/?error=Invalid+access+code'})

@app.route('/logout')
def logout():
    """Handle logout"""
    resp = Response('', status=302)
    resp.headers['Location'] = '/'
    resp.set_cookie('logged_in', '', expires=0)
    return resp

@app.route('/add_task', methods=['POST'])
def add_task():
    """Add a new task"""
    if request.cookies.get('logged_in') != 'true':
        return Response('Unauthorized', status=302, headers={'Location': '/'})
    
    title = request.form.get('title', '').strip()
    start_time_str = request.form.get('start_time', '')
    end_time_str = request.form.get('end_time', '')
    notify_enabled = 1 if request.form.get('notify_enabled') == 'on' else 0
    
    if not title or not start_time_str or not end_time_str:
        return Response('Missing required fields', status=302, headers={'Location': '/?view=tasks'})
    
    # Create datetime in IST
    today = get_ist_time().strftime('%Y-%m-%d')
    start_dt = parse_ist_time(start_time_str, today)
    end_dt = parse_ist_time(end_time_str, today)
    
    start_datetime = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_datetime = end_dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # Insert task
    task_id = db_query(
        "INSERT INTO tasks (title, start_time, end_time, notify_enabled) VALUES (?, ?, ?, ?)",
        (title, start_datetime, end_datetime, notify_enabled)
    )
    
    # Send immediate notification if task starts soon
    now = get_ist_time()
    minutes_until = int((start_dt - now).total_seconds() / 60)
    
    if 1 <= minutes_until <= 10:
        message = f"✅ <b>Task Added</b>\n"
        message += f"📝 {title}\n"
        message += f"🕐 Starts in {minutes_until} minute"
        if minutes_until > 1:
            message += "s"
        message += f"\n📅 {start_dt.strftime('%I:%M %p')} IST"
        send_telegram_message(message)
    
    return Response('', status=302, headers={'Location': '/?view=tasks'})

@app.route('/complete_task', methods=['POST'])
def complete_task():
    """Mark task as completed"""
    if request.cookies.get('logged_in') != 'true':
        return Response('Unauthorized', status=302, headers={'Location': '/'})
    
    task_id = request.form.get('task_id')
    
    if task_id:
        task_row = db_query("SELECT * FROM tasks WHERE id = ?", (task_id,), fetch_one=True)
        task = row_to_dict(task_row)
        
        if task and not task['completed']:
            db_query("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
            
            db_query(
                "INSERT INTO history (task_id, title) VALUES (?, ?)",
                (task_id, task['title'])
            )
            
            now = get_ist_time()
            message = f"🎉 <b>Task Completed!</b>\n"
            message += f"✅ {task['title']}\n"
            message += f"⏰ {now.strftime('%I:%M %p')} IST"
            send_telegram_message(message)
    
    return Response('', status=302, headers={'Location': '/?view=tasks'})

@app.route('/delete_task', methods=['POST'])
def delete_task():
    """Delete a task"""
    if request.cookies.get('logged_in') != 'true':
        return Response('Unauthorized', status=302, headers={'Location': '/'})
    
    task_id = request.form.get('task_id')
    
    if task_id:
        db_query("DELETE FROM tasks WHERE id = ?", (task_id,))
    
    return Response('', status=302, headers={'Location': '/?view=tasks'})

@app.route('/toggle_setting', methods=['POST'])
def toggle_setting():
    """Toggle a setting"""
    if request.cookies.get('logged_in') != 'true':
        return Response('Unauthorized', status=302, headers={'Location': '/'})
    
    key = request.form.get('key')
    enabled = '1' if request.form.get('enabled') == 'on' else '0'
    
    if key:
        db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, enabled))
    
    return Response('', status=302, headers={'Location': '/?view=settings'})

@app.route('/change_code', methods=['POST'])
def change_code():
    """Change access code"""
    if request.cookies.get('logged_in') != 'true':
        return Response('Unauthorized', status=302, headers={'Location': '/'})
    
    new_code = request.form.get('new_code', '')
    confirm_code = request.form.get('confirm_code', '')
    
    if new_code and new_code == confirm_code:
        db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('access_code', new_code))
    
    return Response('', status=302, headers={'Location': '/?view=settings'})

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
    print("=" * 60)
    
    # Start Telegram bot in background thread
    bot_thread = threading.Thread(target=start_bot_polling, daemon=True)
    bot_thread.start()
    
    # Start Flask app
    port = int(os.getenv('PORT', 8000))
    print(f"🌐 Web server: http://0.0.0.0:{port}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
