
"""
Simplified Task Tracker with Telegram Bot
"""

import os
import json
import sqlite3
import threading
from datetime import datetime, timedelta
from flask import Flask, request, Response, render_template_string
import telebot
import time

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"
ADMIN_CODE = "1234"  # Default access code

# Initialize Flask and Telegram bot
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# Store notification timers
notification_timers = {}

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
            last_notified_minute INTEGER DEFAULT 0
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

# ============= TELEGRAM FUNCTIONS =============
def send_telegram_message(text):
    """Send message to Telegram"""
    try:
        bot.send_message(USER_ID, text, parse_mode='HTML')
        print(f"📨 Message sent: {text[:50]}...")
        return True
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False

# ============= NOTIFICATION SYSTEM =============
def check_and_send_notifications():
    """Check and send notifications for tasks starting in 10 minutes"""
    try:
        now = datetime.now()
        print(f"⏰ Checking notifications at {now.strftime('%H:%M:%S')}")
        
        # Get all active tasks with notifications enabled
        tasks = db_query('''
            SELECT * FROM tasks 
            WHERE completed = 0 
            AND notify_enabled = 1
            AND datetime(start_time) > datetime('now')
            ORDER BY start_time
        ''')
        
        print(f"📋 Found {len(tasks)} active tasks")
        
        for task in tasks:
            try:
                task_id = task['id']
                task_title = task['title']
                start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
                
                # Calculate minutes until task starts
                minutes_until_start = int((start_time - now).total_seconds() / 60)
                
                print(f"   Task '{task_title}': {minutes_until_start} minutes until start")
                
                # If task starts in 1-10 minutes, send notification
                if 1 <= minutes_until_start <= 10:
                    # Check if we've already sent a notification for this minute
                    last_notified = task.get('last_notified_minute', 0)
                    
                    if last_notified != minutes_until_start:
                        # Send notification
                        message = f"⏰ <b>Task Reminder</b>\n"
                        message += f"📝 {task_title}\n"
                        message += f"🕐 Starts in {minutes_until_start} minute"
                        if minutes_until_start > 1:
                            message += "s"
                        message += f"\n📅 {start_time.strftime('%I:%M %p')}"
                        
                        if send_telegram_message(message):
                            # Update last notified minute
                            db_query('''
                                UPDATE tasks 
                                SET last_notified_minute = ? 
                                WHERE id = ?
                            ''', (minutes_until_start, task_id))
                            print(f"   ✅ Sent notification for {minutes_until_start} minutes before")
                
                # Reset notification counter if task has passed
                elif minutes_until_start < 0:
                    db_query('''
                        UPDATE tasks 
                        SET last_notified_minute = 0 
                        WHERE id = ?
                    ''', (task_id,))
                    
            except Exception as e:
                print(f"   ❌ Error processing task {task.get('id')}: {e}")
        
    except Exception as e:
        print(f"❌ Notification check error: {e}")

def send_daily_summary():
    """Send daily task summary"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Get today's tasks
        tasks = db_query('''
            SELECT * FROM tasks 
            WHERE date(start_time) = ?
            ORDER BY start_time
        ''', (today,))
        
        if not tasks:
            message = f"📅 <b>Daily Summary - {datetime.now().strftime('%B %d, %Y')}</b>\n"
            message += "No tasks for today! 🎉"
            send_telegram_message(message)
            return
        
        completed = sum(1 for t in tasks if t['completed'])
        total = len(tasks)
        
        message = f"📅 <b>Daily Summary - {datetime.now().strftime('%B %d, %Y')}</b>\n"
        message += f"📊 {completed}/{total} tasks completed\n\n"
        
        for task in tasks:
            status = "✅" if task['completed'] else "❌"
            start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
            message += f"{status} {task['title']} ({start_time.strftime('%I:%M %p')})\n"
        
        send_telegram_message(message)
        
    except Exception as e:
        print(f"❌ Summary error: {e}")

def scheduler_thread():
    """Run scheduler in background thread"""
    print("🔄 Starting scheduler thread...")
    
    while True:
        try:
            # Check every minute
            check_and_send_notifications()
            
            # Check if it's 8:00 AM for daily summary
            now = datetime.now()
            if now.hour == 8 and now.minute == 0:
                # Check if daily summary is enabled
                setting = db_query("SELECT value FROM settings WHERE key = 'daily_summary'", fetch_one=True)
                if setting and setting['value'] == '1':
                    send_daily_summary()
                    # Wait 2 minutes to avoid sending multiple times
                    time.sleep(120)
            
            # Wait for next minute
            seconds_until_next_minute = 60 - now.second
            time.sleep(seconds_until_next_minute)
            
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
    
    welcome = """
🤖 <b>Task Tracker Bot</b>

<b>Commands:</b>
/today - View today's tasks
/add - Add new task
/summary - Get daily summary
/test - Test notification
/help - Show this message

<b>Notifications:</b>
• 1 notification per minute for 10 minutes before task starts
• Daily summary at 8 AM

<b>Web Interface:</b>
https://patient-maxie-sandip232-786edcb8.koyeb.app/
"""
    bot.reply_to(message, welcome, parse_mode='HTML')

@bot.message_handler(commands=['today'])
def send_today_tasks(message):
    """Send today's tasks"""
    if str(message.chat.id) != USER_ID:
        return
    
    today = datetime.now().strftime('%Y-%m-%d')
    tasks = db_query('''
        SELECT * FROM tasks 
        WHERE date(start_time) = ?
        ORDER BY start_time
    ''', (today,))
    
    if not tasks:
        bot.reply_to(message, "📅 No tasks for today!")
        return
    
    response = f"📅 <b>Today's Tasks ({datetime.now().strftime('%B %d')})</b>\n\n"
    
    for task in tasks:
        status = "✅" if task['completed'] else "❌"
        start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
        end_time = datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S')
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
        today = datetime.now().strftime('%Y-%m-%d')
        
        start_time = f"{today} {start_str}:00"
        end_time = f"{today} {end_str}:00"
        
        # Insert task
        task_id = db_query(
            "INSERT INTO tasks (title, start_time, end_time) VALUES (?, ?, ?)",
            (title, start_time, end_time)
        )
        
        # Send confirmation
        response = f"✅ <b>Task Added</b>\n"
        response += f"📝 {title}\n"
        response += f"⏰ {start_str} - {end_str}\n"
        response += f"📅 {datetime.now().strftime('%B %d')}"
        
        bot.reply_to(message, response, parse_mode='HTML')
        
        # Send immediate notification
        start_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        minutes_until = int((start_dt - now).total_seconds() / 60)
        
        if 1 <= minutes_until <= 10:
            notif_msg = f"⏰ <b>Task Added (starts in {minutes_until} min)</b>\n"
            notif_msg += f"📝 {title}\n"
            notif_msg += f"🕐 {start_str} - {end_str}"
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
    
    test_msg = "🔔 <b>Test Notification</b>\n"
    test_msg += "✅ Bot is working!\n"
    test_msg += f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    
    if send_telegram_message(test_msg):
        bot.reply_to(message, "✅ Test notification sent!")
    else:
        bot.reply_to(message, "❌ Failed to send test")

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
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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
                    transition: border 0.3s;
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
                button:active {
                    transform: scale(0.98);
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
                    <input type="password" name="code" placeholder="Enter Access Code" required autocomplete="off">
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
    
    # Get tasks for today
    today = datetime.now().strftime('%Y-%m-%d')
    tasks = db_query('''
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
        settings[row['key']] = row['value']
    
    # Calculate stats
    completed_today = sum(1 for t in tasks if t['completed'])
    pending_today = len(tasks) - completed_today
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Task Tracker</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {
                --primary: #4361ee;
                --secondary: #3a0ca3;
                --success: #4cc9f0;
                --danger: #f72585;
                --warning: #f8961e;
                --light: #f8f9fa;
                --dark: #212529;
                --gray: #6c757d;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                -webkit-tap-highlight-color: transparent;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f5f5f7;
                color: #333;
                line-height: 1.6;
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
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
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
                opacity: 0.9;
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
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s;
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
                animation: fadeIn 0.3s;
            }
            
            .section.active {
                display: block;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
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
                margin-bottom: 5px;
            }
            
            .stat-label {
                font-size: 12px;
                color: var(--gray);
            }
            
            /* Add Task Form */
            .add-form {
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
                color: var(--dark);
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .form-group {
                margin-bottom: 15px;
            }
            
            .form-label {
                display: block;
                margin-bottom: 5px;
                font-size: 14px;
                color: var(--dark);
                font-weight: 500;
            }
            
            .form-input {
                width: 100%;
                padding: 12px;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                font-size: 16px;
                transition: border 0.3s;
            }
            
            .form-input:focus {
                outline: none;
                border-color: var(--primary);
            }
            
            .time-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
            }
            
            .checkbox {
                display: flex;
                align-items: center;
                gap: 10px;
                margin: 15px 0;
            }
            
            .checkbox input {
                width: 20px;
                height: 20px;
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
                transition: all 0.3s;
            }
            
            .btn-primary {
                background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                color: white;
            }
            
            .btn-primary:active {
                transform: scale(0.98);
            }
            
            .btn-danger {
                background: var(--danger);
                color: white;
            }
            
            .btn-success {
                background: var(--success);
                color: white;
            }
            
            /* Task List */
            .tasks-list {
                margin-top: 20px;
            }
            
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
            
            .task-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 10px;
            }
            
            .task-title {
                font-size: 16px;
                font-weight: 600;
                color: var(--dark);
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
                color: var(--gray);
                font-size: 14px;
                margin: 8px 0;
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
                font-weight: 500;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            }
            
            /* History */
            .history-item {
                background: white;
                border-radius: 12px;
                padding: 15px;
                margin-bottom: 10px;
                border-left: 4px solid var(--success);
            }
            
            .history-title {
                font-weight: 600;
                margin-bottom: 5px;
            }
            
            .history-time {
                font-size: 12px;
                color: var(--gray);
            }
            
            /* Settings */
            .settings-card {
                background: white;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 15px;
            }
            
            .setting-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 15px 0;
                border-bottom: 1px solid #eee;
            }
            
            .setting-item:last-child {
                border-bottom: none;
            }
            
            .setting-info h4 {
                font-size: 16px;
                margin-bottom: 5px;
            }
            
            .setting-info p {
                font-size: 12px;
                color: var(--gray);
            }
            
            .toggle {
                position: relative;
                display: inline-block;
                width: 50px;
                height: 24px;
            }
            
            .toggle input {
                opacity: 0;
                width: 0;
                height: 0;
            }
            
            .slider {
                position: absolute;
                cursor: pointer;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: #ccc;
                transition: .4s;
                border-radius: 24px;
            }
            
            .slider:before {
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
            
            input:checked + .slider {
                background-color: var(--success);
            }
            
            input:checked + .slider:before {
                transform: translateX(26px);
            }
            
            /* Empty State */
            .empty-state {
                text-align: center;
                padding: 40px 20px;
                color: var(--gray);
            }
            
            .empty-state i {
                font-size: 48px;
                margin-bottom: 15px;
                opacity: 0.5;
            }
            
            /* Logout */
            .logout-btn {
                background: var(--danger);
                color: white;
                padding: 14px;
                border-radius: 8px;
                text-align: center;
                text-decoration: none;
                display: block;
                margin-top: 20px;
                font-weight: 600;
            }
            
            /* Notification Banner */
            .notification {
                background: linear-gradient(135deg, var(--warning) 0%, #ff6b6b 100%);
                color: white;
                padding: 12px 15px;
                border-radius: 12px;
                margin-bottom: 20px;
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.8; }
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
                transition: all 0.3s;
            }
            
            .fab:active {
                transform: scale(0.9);
            }
        </style>
    </head>
    <body>
        <!-- Header -->
        <div class="header">
            <div class="header-top">
                <h1><i class="fas fa-tasks"></i> Task Tracker</h1>
                <div class="time-display">
                    {{ datetime.now().strftime('%I:%M %p') }}
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
                <div class="notification">
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
                <div class="add-form">
                    <div class="form-title">
                        <i class="fas fa-plus-circle"></i> Add New Task
                    </div>
                    <form method="POST" action="/add_task" id="taskForm">
                        <div class="form-group">
                            <label class="form-label">Task Title</label>
                            <input type="text" class="form-input" name="title" placeholder="What needs to be done?" required autocomplete="off">
                        </div>
                        
                        <div class="form-group">
                            <label class="form-label">Time</label>
                            <div class="time-row">
                                <div>
                                    <input type="time" class="form-input" name="start_time" id="startTime" required>
                                    <div style="font-size: 11px; color: var(--gray); text-align: center; margin-top: 3px;">Start</div>
                                </div>
                                <div>
                                    <input type="time" class="form-input" name="end_time" id="endTime" required>
                                    <div style="font-size: 11px; color: var(--gray); text-align: center; margin-top: 3px;">End</div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="checkbox">
                            <input type="checkbox" name="notify_enabled" id="notifyEnabled" checked>
                            <label for="notifyEnabled" style="font-size: 14px;">Enable notifications</label>
                        </div>
                        
                        <button type="submit" class="btn btn-primary">
                            <i class="fas fa-plus"></i> Add Task
                        </button>
                    </form>
                </div>
                
                <!-- Tasks List -->
                <div class="tasks-list">
                    <div style="font-size: 16px; font-weight: 600; margin-bottom: 15px; color: var(--dark);">
                        <i class="fas fa-calendar-day"></i> Today's Tasks
                        <span style="font-size: 12px; color: var(--gray); font-weight: normal; margin-left: 8px;">
                            {{ datetime.now().strftime('%B %d') }}
                        </span>
                    </div>
                    
                    {% if not tasks %}
                    <div class="empty-state">
                        <i class="fas fa-clipboard-list"></i>
                        <p>No tasks for today</p>
                        <p style="font-size: 12px; margin-top: 5px;">Add your first task above!</p>
                    </div>
                    {% endif %}
                    
                    {% for task in tasks %}
                    <div class="task-card {{ 'completed' if task['completed'] }}">
                        <div class="task-header">
                            <div class="task-title">{{ task['title'] }}</div>
                            <div class="task-status {{ 'status-completed' if task['completed'] else 'status-pending' }}">
                                {{ '✅ Completed' if task['completed'] else '⏳ Pending' }}
                            </div>
                        </div>
                        
                        <div class="task-time">
                            <i class="far fa-clock"></i>
                            {{ datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p') }}
                            -
                            {{ datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p') }}
                        </div>
                        
                        {% if not task['completed'] %}
                        {% set start_dt = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S') %}
                        {% set minutes_left = (start_dt - datetime.now()).total_seconds() / 60 %}
                        {% if 0 < minutes_left <= 60 %}
                        <div style="font-size: 12px; color: var(--warning); margin: 5px 0;">
                            <i class="fas fa-hourglass-half"></i>
                            Starts in {{ minutes_left|int }} minute{{ 's' if minutes_left|int > 1 else '' }}
                        </div>
                        {% endif %}
                        {% endif %}
                        
                        <div class="task-actions">
                            {% if not task['completed'] %}
                            <form method="POST" action="/complete_task" style="display: contents;">
                                <input type="hidden" name="task_id" value="{{ task['id'] }}">
                                <button type="submit" class="action-btn btn-success">
                                    <i class="fas fa-check"></i> Complete
                                </button>
                            </form>
                            {% endif %}
                            
                            <form method="POST" action="/delete_task" style="display: contents;">
                                <input type="hidden" name="task_id" value="{{ task['id'] }}">
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
                <div style="font-size: 16px; font-weight: 600; margin-bottom: 15px; color: var(--dark);">
                    <i class="fas fa-history"></i> Task History
                </div>
                
                {% if not history %}
                <div class="empty-state">
                    <i class="fas fa-history"></i>
                    <p>No completed tasks yet</p>
                </div>
                {% endif %}
                
                {% for item in history %}
                <div class="history-item">
                    <div class="history-title">{{ item['task_title'] or item['title'] }}</div>
                    <div class="history-time">
                        <i class="far fa-calendar-check"></i>
                        {{ datetime.strptime(item['completed_at'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %I:%M %p') }}
                    </div>
                </div>
                {% endfor %}
            </div>
            
            <!-- Settings View -->
            <div id="settingsView" class="section {{ 'active' if view == 'settings' }}">
                <div class="settings-card">
                    <div style="font-size: 16px; font-weight: 600; margin-bottom: 20px; color: var(--dark);">
                        <i class="fas fa-bell"></i> Notifications
                    </div>
                    
                    <div class="setting-item">
                        <div class="setting-info">
                            <h4>Daily Summary</h4>
                            <p>Send daily task summary at 8:00 AM</p>
                        </div>
                        <form method="POST" action="/toggle_setting" style="display: inline;">
                            <input type="hidden" name="key" value="daily_summary">
                            <label class="toggle">
                                <input type="checkbox" name="enabled" {{ 'checked' if settings.get('daily_summary') == '1' }} onchange="this.form.submit()">
                                <span class="slider"></span>
                            </label>
                        </form>
                    </div>
                    
                    <div style="margin-top: 15px; padding: 12px; background: #f8f9fa; border-radius: 8px; font-size: 13px;">
                        <div style="font-weight: 600; margin-bottom: 5px; color: var(--primary);">
                            <i class="fas fa-info-circle"></i> Notification Schedule
                        </div>
                        <div>You'll receive 1 notification per minute for 10 minutes before each task starts</div>
                    </div>
                </div>
                
                <div class="settings-card">
                    <div style="font-size: 16px; font-weight: 600; margin-bottom: 20px; color: var(--dark);">
                        <i class="fas fa-key"></i> Security
                    </div>
                    
                    <form method="POST" action="/change_code">
                        <div class="form-group">
                            <label class="form-label">New Access Code</label>
                            <input type="password" class="form-input" name="new_code" placeholder="Enter new code" required autocomplete="new-password">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Confirm Code</label>
                            <input type="password" class="form-input" name="confirm_code" placeholder="Confirm new code" required autocomplete="new-password">
                        </div>
                        <button type="submit" class="btn btn-primary">
                            <i class="fas fa-save"></i> Change Access Code
                        </button>
                    </form>
                </div>
                
                <div class="settings-card">
                    <div style="font-size: 16px; font-weight: 600; margin-bottom: 15px; color: var(--dark);">
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
                        <div style="font-size: 13px; color: var(--gray);">
                            Send /start to your bot to get commands
                        </div>
                    </div>
                </div>
                
                <a href="/logout" class="logout-btn">
                    <i class="fas fa-sign-out-alt"></i> Logout
                </a>
            </div>
        </div>
        
        <!-- FAB -->
        <div class="fab" onclick="document.querySelector('#taskForm').scrollIntoView({behavior: 'smooth'})">
            <i class="fas fa-plus"></i>
        </div>
        
        <script>
            // Switch views
            function switchView(view) {
                window.location.href = '/?view=' + view;
            }
            
            // Set default times
            document.addEventListener('DOMContentLoaded', function() {
                // Set start time to next hour
                const now = new Date();
                const nextHour = new Date(now.getTime() + 60 * 60 * 1000);
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
                
                // Auto-update time display
                function updateTime() {
                    const now = new Date();
                    const timeElements = document.querySelectorAll('.time-display');
                    timeElements.forEach(el => {
                        el.textContent = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
                    });
                }
                
                updateTime();
                setInterval(updateTime, 60000);
                
                // Handle form submissions
                document.querySelectorAll('form').forEach(form => {
                    if (form.action.includes('/delete_task')) {
                        form.addEventListener('submit', function(e) {
                            if (!confirm('Are you sure you want to delete this task?')) {
                                e.preventDefault();
                            }
                        });
                    }
                });
            });
            
            // Add swipe support for mobile
            let startX = 0;
            let endX = 0;
            
            document.addEventListener('touchstart', function(e) {
                startX = e.changedTouches[0].screenX;
            });
            
            document.addEventListener('touchend', function(e) {
                endX = e.changedTouches[0].screenX;
                const diff = startX - endX;
                
                if (Math.abs(diff) > 50) {
                    const views = ['tasks', 'history', 'settings'];
                    const currentView = '{{ view }}';
                    const currentIndex = views.indexOf(currentView);
                    
                    if (diff > 0 && currentIndex < views.length - 1) {
                        // Swipe left
                        switchView(views[currentIndex + 1]);
                    } else if (diff < 0 && currentIndex > 0) {
                        // Swipe right
                        switchView(views[currentIndex - 1]);
                    }
                }
            });
        </script>
    </body>
    </html>
    ''', 
    tasks=tasks, 
    history=history, 
    settings=settings, 
    view=view, 
    datetime=datetime,
    USER_ID=USER_ID,
    completed_today=completed_today,
    pending_today=pending_today)

# ============= ACTION ROUTES =============
@app.route('/login', methods=['POST'])
def login():
    """Handle login"""
    code = request.form.get('code', '')
    
    setting = db_query("SELECT value FROM settings WHERE key = 'access_code'", fetch_one=True)
    correct_code = setting['value'] if setting else ADMIN_CODE
    
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
    start_time = request.form.get('start_time', '')
    end_time = request.form.get('end_time', '')
    notify_enabled = 1 if request.form.get('notify_enabled') == 'on' else 0
    
    if not title or not start_time or not end_time:
        return Response('Missing required fields', status=302, headers={'Location': '/?view=tasks'})
    
    # Create datetime strings
    today = datetime.now().strftime('%Y-%m-%d')
    start_datetime = f"{today} {start_time}:00"
    end_datetime = f"{today} {end_time}:00"
    
    # Insert task
    task_id = db_query(
        "INSERT INTO tasks (title, start_time, end_time, notify_enabled) VALUES (?, ?, ?, ?)",
        (title, start_datetime, end_datetime, notify_enabled)
    )
    
    # Send immediate notification if task starts soon
    start_dt = datetime.strptime(start_datetime, '%Y-%m-%d %H:%M:%S')
    now = datetime.now()
    minutes_until = int((start_dt - now).total_seconds() / 60)
    
    if 1 <= minutes_until <= 10:
        message = f"✅ <b>Task Added</b>\n"
        message += f"📝 {title}\n"
        message += f"🕐 Starts in {minutes_until} minute"
        if minutes_until > 1:
            message += "s"
        message += f"\n📅 {start_dt.strftime('%I:%M %p')}"
        send_telegram_message(message)
    
    return Response('', status=302, headers={'Location': '/?view=tasks'})

@app.route('/complete_task', methods=['POST'])
def complete_task():
    """Mark task as completed"""
    if request.cookies.get('logged_in') != 'true':
        return Response('Unauthorized', status=302, headers={'Location': '/'})
    
    task_id = request.form.get('task_id')
    
    if task_id:
        task = db_query("SELECT * FROM tasks WHERE id = ?", (task_id,), fetch_one=True)
        
        if task and not task['completed']:
            # Update task
            db_query("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
            
            # Add to history
            db_query(
                "INSERT INTO history (task_id, title) VALUES (?, ?)",
                (task_id, task['title'])
            )
            
            # Send completion notification
            message = f"🎉 <b>Task Completed!</b>\n"
            message += f"✅ {task['title']}\n"
            message += f"⏰ {datetime.now().strftime('%I:%M %p')}"
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
    bot.remove_webhook()
    time.sleep(1)
    bot.polling(none_stop=True, interval=1, timeout=30)

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Task Tracker Starting...")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
