
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
import schedule
import time

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"
ADMIN_CODE = "1234"  # Default access code

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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('notify_interval', '30')")  # 30 minutes
    
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
        return True
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def send_task_notification(task):
    """Send task notification"""
    start_time = datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S')
    end_time = datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S')
    
    message = f"📋 <b>Task: {task['title']}</b>\n"
    message += f"⏰ {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}\n"
    message += f"📅 {start_time.strftime('%B %d, %Y')}\n"
    message += f"Status: {'✅ Completed' if task['completed'] else '⏳ Pending'}"
    
    return send_telegram_message(message)

# ============= NOTIFICATION SCHEDULER =============
def check_and_send_notifications():
    """Check and send notifications for upcoming tasks"""
    try:
        # Get current time and time 30 minutes from now
        now = datetime.now()
        future = now + timedelta(minutes=30)
        
        # Get tasks starting within next 30 minutes
        tasks = db_query('''
            SELECT * FROM tasks 
            WHERE completed = 0 
            AND notify_enabled = 1
            AND datetime(start_time) BETWEEN ? AND ?
        ''', (now.strftime('%Y-%m-%d %H:%M:%S'), future.strftime('%Y-%m-%d %H:%M:%S')))
        
        for task in tasks:
            message = f"🔔 <b>Task Starting Soon</b>\n"
            message += f"📝 {task['title']}\n"
            message += f"⏰ Starts at: {datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p')}\n"
            send_telegram_message(message)
            
    except Exception as e:
        print(f"Notification error: {e}")

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
        print(f"Summary error: {e}")

def scheduler_thread():
    """Run scheduler in background thread"""
    # Schedule notifications every 30 minutes
    schedule.every(30).minutes.do(check_and_send_notifications)
    
    # Schedule daily summary at 8 AM
    schedule.every().day.at("08:00").do(send_daily_summary)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

# Start scheduler thread
threading.Thread(target=scheduler_thread, daemon=True).start()

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
/help - Show this message

<b>Web Interface:</b>
Visit the web app to manage tasks:
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
    
    # Simple format: /add Title @ HH:MM-HH:MM
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
        bot.reply_to(message, f"✅ Task added: {title}\n⏰ {start_str}-{end_str}")
        
        # Send to Telegram
        task = {'title': title, 'start_time': start_time, 'end_time': end_time, 'completed': 0}
        send_task_notification(task)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['summary'])
def send_summary(message):
    """Send summary"""
    if str(message.chat.id) != USER_ID:
        return
    
    send_daily_summary()
    bot.reply_to(message, "📊 Summary sent!")

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
                    font-family: Arial, sans-serif;
                    max-width: 400px;
                    margin: 50px auto;
                    padding: 20px;
                    background: #f5f5f5;
                }
                .login-box {
                    background: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                h1 {
                    color: #333;
                    text-align: center;
                    margin-bottom: 30px;
                }
                input {
                    width: 100%;
                    padding: 10px;
                    margin: 10px 0;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    box-sizing: border-box;
                }
                button {
                    width: 100%;
                    padding: 12px;
                    background: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    font-size: 16px;
                }
                button:hover {
                    background: #45a049;
                }
                .error {
                    color: red;
                    text-align: center;
                    margin: 10px 0;
                }
            </style>
        </head>
        <body>
            <div class="login-box">
                <h1>🔐 Task Tracker</h1>
                <form method="POST" action="/login">
                    <input type="password" name="code" placeholder="Enter Access Code" required>
                    <button type="submit">Login</button>
                </form>
                {% if error %}
                <div class="error">{{ error }}</div>
                {% endif %}
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
    
    # Get all tasks for history
    all_tasks = db_query('SELECT * FROM tasks ORDER BY start_time DESC LIMIT 50')
    
    # Get history
    history = db_query('''
        SELECT h.*, t.title as task_title 
        FROM history h
        LEFT JOIN tasks t ON h.task_id = t.id
        ORDER BY h.completed_at DESC
        LIMIT 50
    ''')
    
    # Get settings
    settings = {}
    setting_rows = db_query("SELECT key, value FROM settings")
    for row in setting_rows:
        settings[row['key']] = row['value']
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Task Tracker</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            :root {
                --primary: #4CAF50;
                --secondary: #2196F3;
                --danger: #f44336;
                --light: #f5f5f5;
                --dark: #333;
                --gray: #666;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            
            body {
                background: var(--light);
                color: var(--dark);
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }
            
            /* Header */
            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 15px 0;
                margin-bottom: 20px;
                border-bottom: 2px solid var(--primary);
            }
            
            .header h1 {
                color: var(--primary);
                font-size: 24px;
            }
            
            .nav {
                display: flex;
                gap: 10px;
            }
            
            .nav-btn {
                padding: 8px 16px;
                background: var(--primary);
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                text-decoration: none;
                font-size: 14px;
            }
            
            .nav-btn:hover {
                opacity: 0.9;
            }
            
            .nav-btn.active {
                background: var(--secondary);
            }
            
            /* Content Sections */
            .content-section {
                display: none;
                animation: fadeIn 0.3s;
            }
            
            .content-section.active {
                display: block;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            /* Task Cards */
            .task-card {
                background: white;
                border-radius: 10px;
                padding: 15px;
                margin-bottom: 15px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            
            .task-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            
            .task-title {
                font-size: 18px;
                font-weight: 600;
                color: var(--dark);
            }
            
            .task-time {
                color: var(--gray);
                font-size: 14px;
                margin: 5px 0;
            }
            
            .task-actions {
                display: flex;
                gap: 10px;
                margin-top: 10px;
            }
            
            .btn {
                padding: 6px 12px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 13px;
            }
            
            .btn-complete {
                background: var(--primary);
                color: white;
            }
            
            .btn-delete {
                background: var(--danger);
                color: white;
            }
            
            .btn-edit {
                background: var(--secondary);
                color: white;
            }
            
            /* Forms */
            .form-box {
                background: white;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            
            .form-group {
                margin-bottom: 15px;
            }
            
            .form-label {
                display: block;
                margin-bottom: 5px;
                font-weight: 500;
                color: var(--dark);
            }
            
            .form-input {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 14px;
            }
            
            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
            }
            
            /* Stats */
            .stats {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 15px;
                margin-bottom: 20px;
            }
            
            .stat-card {
                background: white;
                border-radius: 10px;
                padding: 15px;
                text-align: center;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }
            
            .stat-number {
                font-size: 24px;
                font-weight: bold;
                color: var(--primary);
            }
            
            .stat-label {
                font-size: 14px;
                color: var(--gray);
                margin-top: 5px;
            }
            
            /* History */
            .history-item {
                background: white;
                border-radius: 10px;
                padding: 15px;
                margin-bottom: 10px;
                border-left: 4px solid var(--primary);
            }
            
            .history-time {
                font-size: 12px;
                color: var(--gray);
                margin-top: 5px;
            }
            
            /* Settings */
            .setting-item {
                background: white;
                border-radius: 10px;
                padding: 15px;
                margin-bottom: 10px;
                display: flex;
                justify-content: space-between;
                align-items: center;
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
                background-color: #ccc;
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
                background-color: var(--primary);
            }
            
            input:checked + .toggle-slider:before {
                transform: translateX(26px);
            }
            
            /* Modal */
            .modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
                z-index: 1000;
                align-items: center;
                justify-content: center;
            }
            
            .modal-content {
                background: white;
                border-radius: 10px;
                padding: 20px;
                width: 90%;
                max-width: 500px;
            }
            
            /* Empty States */
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
            
            /* FAB */
            .fab {
                position: fixed;
                bottom: 30px;
                right: 30px;
                width: 60px;
                height: 60px;
                background: var(--primary);
                color: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
                cursor: pointer;
                box-shadow: 0 4px 10px rgba(0,0,0,0.2);
                z-index: 100;
            }
            
            .fab:hover {
                transform: scale(1.1);
            }
            
            /* Responsive */
            @media (max-width: 768px) {
                body {
                    padding: 10px;
                }
                
                .header {
                    flex-direction: column;
                    gap: 15px;
                }
                
                .nav {
                    width: 100%;
                    justify-content: center;
                }
                
                .form-row {
                    grid-template-columns: 1fr;
                }
                
                .stats {
                    grid-template-columns: 1fr;
                }
                
                .fab {
                    bottom: 20px;
                    right: 20px;
                    width: 50px;
                    height: 50px;
                    font-size: 20px;
                }
            }
        </style>
    </head>
    <body>
        <!-- Header -->
        <div class="header">
            <h1><i class="fas fa-tasks"></i> Task Tracker</h1>
            <div class="nav">
                <a href="?view=tasks" class="nav-btn {{ 'active' if view == 'tasks' }}">Tasks</a>
                <a href="?view=history" class="nav-btn {{ 'active' if view == 'history' }}">History</a>
                <a href="?view=settings" class="nav-btn {{ 'active' if view == 'settings' }}">Settings</a>
                <a href="/logout" class="nav-btn" style="background: var(--danger);">Logout</a>
            </div>
        </div>
        
        <!-- Stats -->
        {% if view == 'tasks' %}
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{{ tasks|length }}</div>
                <div class="stat-label">Total Tasks</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ tasks|selectattr('completed')|list|length }}</div>
                <div class="stat-label">Completed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{{ tasks|rejectattr('completed')|list|length }}</div>
                <div class="stat-label">Pending</div>
            </div>
        </div>
        {% endif %}
        
        <!-- Tasks View -->
        <div id="tasksView" class="content-section {{ 'active' if view == 'tasks' }}">
            <!-- Add Task Form -->
            <div class="form-box">
                <h3 style="margin-bottom: 15px; color: var(--primary);">
                    <i class="fas fa-plus-circle"></i> Add New Task
                </h3>
                <form method="POST" action="/add_task">
                    <div class="form-group">
                        <label class="form-label">Task Title</label>
                        <input type="text" class="form-input" name="title" placeholder="Enter task title" required>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label class="form-label">Start Time</label>
                            <input type="time" class="form-input" name="start_time" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">End Time</label>
                            <input type="time" class="form-input" name="end_time" required>
                        </div>
                    </div>
                    <div class="form-group">
                        <label style="display: flex; align-items: center; gap: 10px;">
                            <input type="checkbox" name="notify_enabled" checked>
                            <span>Enable notifications</span>
                        </label>
                    </div>
                    <button type="submit" class="btn btn-complete" style="width: 100%; padding: 12px;">
                        <i class="fas fa-save"></i> Add Task
                    </button>
                </form>
            </div>
            
            <!-- Tasks List -->
            <h3 style="margin: 20px 0 10px; color: var(--primary);">
                <i class="fas fa-list"></i> Today's Tasks
                <small style="color: var(--gray); font-weight: normal; margin-left: 10px;">
                    {{ datetime.now().strftime('%B %d, %Y') }}
                </small>
            </h3>
            
            {% if not tasks %}
            <div class="empty-state">
                <i class="fas fa-clipboard-list"></i>
                <p>No tasks for today. Add one above!</p>
            </div>
            {% endif %}
            
            {% for task in tasks %}
            <div class="task-card">
                <div class="task-header">
                    <h3 class="task-title">{{ task['title'] }}</h3>
                    <span style="color: {{ 'var(--primary)' if task['completed'] else 'var(--danger)' }}; font-weight: bold;">
                        {{ '✅ Completed' if task['completed'] else '❌ Pending' }}
                    </span>
                </div>
                <div class="task-time">
                    <i class="far fa-clock"></i> 
                    {{ datetime.strptime(task['start_time'], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p') }} 
                    - 
                    {{ datetime.strptime(task['end_time'], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p') }}
                </div>
                <div class="task-actions">
                    {% if not task['completed'] %}
                    <form method="POST" action="/complete_task" style="display: inline;">
                        <input type="hidden" name="task_id" value="{{ task['id'] }}">
                        <button type="submit" class="btn btn-complete">
                            <i class="fas fa-check"></i> Complete
                        </button>
                    </form>
                    {% endif %}
                    <form method="POST" action="/delete_task" style="display: inline;">
                        <input type="hidden" name="task_id" value="{{ task['id'] }}">
                        <button type="submit" class="btn btn-delete" onclick="return confirm('Delete this task?')">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </form>
                </div>
            </div>
            {% endfor %}
        </div>
        
        <!-- History View -->
        <div id="historyView" class="content-section {{ 'active' if view == 'history' }}">
            <h3 style="margin-bottom: 15px; color: var(--primary);">
                <i class="fas fa-history"></i> Task History
            </h3>
            
            {% if not history %}
            <div class="empty-state">
                <i class="fas fa-history"></i>
                <p>No history yet. Complete some tasks!</p>
            </div>
            {% endif %}
            
            {% for item in history %}
            <div class="history-item">
                <div style="font-weight: bold; margin-bottom: 5px;">
                    {{ item['task_title'] or item['title'] }}
                </div>
                <div class="history-time">
                    <i class="far fa-calendar-check"></i> 
                    {{ datetime.strptime(item['completed_at'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y %I:%M %p') }}
                </div>
            </div>
            {% endfor %}
        </div>
        
        <!-- Settings View -->
        <div id="settingsView" class="content-section {{ 'active' if view == 'settings' }}">
            <h3 style="margin-bottom: 20px; color: var(--primary);">
                <i class="fas fa-cog"></i> Settings
            </h3>
            
            <!-- Notification Settings -->
            <div class="form-box">
                <h4 style="margin-bottom: 15px; color: var(--dark);">
                    <i class="fas fa-bell"></i> Notification Settings
                </h4>
                
                <form method="POST" action="/update_settings">
                    <div class="setting-item">
                        <div>
                            <div style="font-weight: 500;">Notification Interval</div>
                            <div style="font-size: 13px; color: var(--gray);">
                                Send notifications before task starts
                            </div>
                        </div>
                        <div>
                            <select name="notify_interval" class="form-input" style="width: auto;">
                                <option value="15" {{ 'selected' if settings.get('notify_interval') == '15' }}>15 minutes</option>
                                <option value="30" {{ 'selected' if settings.get('notify_interval') == '30' }}>30 minutes</option>
                                <option value="60" {{ 'selected' if settings.get('notify_interval') == '60' }}>1 hour</option>
                                <option value="120" {{ 'selected' if settings.get('notify_interval') == '120' }}>2 hours</option>
                            </select>
                        </div>
                    </div>
                    
                    <div class="setting-item">
                        <div>
                            <div style="font-weight: 500;">Daily Summary</div>
                            <div style="font-size: 13px; color: var(--gray);">
                                Send daily summary at 8 AM
                            </div>
                        </div>
                        <div>
                            <label class="toggle-switch">
                                <input type="checkbox" name="daily_summary" {{ 'checked' if settings.get('daily_summary') == '1' }}>
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                    </div>
                    
                    <button type="submit" class="btn btn-complete" style="width: 100%; margin-top: 15px; padding: 12px;">
                        <i class="fas fa-save"></i> Save Settings
                    </button>
                </form>
            </div>
            
            <!-- Change Access Code -->
            <div class="form-box">
                <h4 style="margin-bottom: 15px; color: var(--dark);">
                    <i class="fas fa-key"></i> Security
                </h4>
                
                <form method="POST" action="/change_code">
                    <div class="form-group">
                        <label class="form-label">New Access Code</label>
                        <input type="password" class="form-input" name="new_code" placeholder="Enter new code" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Confirm Code</label>
                        <input type="password" class="form-input" name="confirm_code" placeholder="Confirm new code" required>
                    </div>
                    <button type="submit" class="btn btn-edit" style="width: 100%; padding: 12px;">
                        <i class="fas fa-key"></i> Change Access Code
                    </button>
                </form>
            </div>
            
            <!-- Telegram Info -->
            <div class="form-box">
                <h4 style="margin-bottom: 15px; color: var(--dark);">
                    <i class="fab fa-telegram"></i> Telegram Integration
                </h4>
                <div style="color: var(--gray); font-size: 14px; line-height: 1.5;">
                    <p><strong>User ID:</strong> {{ USER_ID }}</p>
                    <p><strong>Bot Status:</strong> <span style="color: var(--primary);">✅ Connected</span></p>
                    <p>Send /start to the bot to get started with commands.</p>
                </div>
            </div>
        </div>
        
        <!-- FAB for Mobile -->
        <div class="fab" onclick="document.querySelector('#tasksView .form-box').scrollIntoView({behavior: 'smooth'})">
            <i class="fas fa-plus"></i>
        </div>
        
        <script>
            // Simple view switching
            document.addEventListener('DOMContentLoaded', function() {
                // Handle form submissions
                document.querySelectorAll('form').forEach(form => {
                    form.addEventListener('submit', function(e) {
                        if(this.action.includes('/delete_task')) {
                            if(!confirm('Are you sure you want to delete this task?')) {
                                e.preventDefault();
                            }
                        }
                    });
                });
                
                // Auto set times
                const now = new Date();
                const startTime = document.querySelector('input[name="start_time"]');
                const endTime = document.querySelector('input[name="end_time"]');
                
                if(startTime && !startTime.value) {
                    // Set start time to next hour
                    const nextHour = new Date(now.getTime() + 60 * 60 * 1000);
                    startTime.value = nextHour.toTimeString().slice(0,5);
                }
                
                if(endTime && !endTime.value) {
                    // Set end time to 1 hour after start
                    const start = new Date(`2000-01-01T${startTime.value}:00`);
                    start.setHours(start.getHours() + 1);
                    endTime.value = start.toTimeString().slice(0,5);
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
    today=datetime.now().strftime('%B %d, %Y'))

# ============= ACTION ROUTES =============
@app.route('/login', methods=['POST'])
def login():
    """Handle login"""
    code = request.form.get('code', '')
    
    # Get access code from database
    setting = db_query("SELECT value FROM settings WHERE key = 'access_code'", fetch_one=True)
    correct_code = setting['value'] if setting else ADMIN_CODE
    
    if code == correct_code:
        resp = Response('', status=302)
        resp.headers['Location'] = '/'
        resp.set_cookie('logged_in', 'true', max_age=86400*30)  # 30 days
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
    
    # Send Telegram notification
    task = {
        'title': title,
        'start_time': start_datetime,
        'end_time': end_datetime,
        'completed': 0
    }
    send_task_notification(task)
    
    return Response('', status=302, headers={'Location': '/?view=tasks'})

@app.route('/complete_task', methods=['POST'])
def complete_task():
    """Mark task as completed"""
    if request.cookies.get('logged_in') != 'true':
        return Response('Unauthorized', status=302, headers={'Location': '/'})
    
    task_id = request.form.get('task_id')
    
    if task_id:
        # Get task details
        task = db_query("SELECT * FROM tasks WHERE id = ?", (task_id,), fetch_one=True)
        
        if task:
            # Update task
            db_query("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
            
            # Add to history
            db_query(
                "INSERT INTO history (task_id, title) VALUES (?, ?)",
                (task_id, task['title'])
            )
            
            # Send completion notification
            message = f"✅ <b>Task Completed!</b>\n📝 {task['title']}\n⏰ {datetime.now().strftime('%I:%M %p')}"
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

@app.route('/update_settings', methods=['POST'])
def update_settings():
    """Update settings"""
    if request.cookies.get('logged_in') != 'true':
        return Response('Unauthorized', status=302, headers={'Location': '/'})
    
    notify_interval = request.form.get('notify_interval', '30')
    daily_summary = '1' if request.form.get('daily_summary') == 'on' else '0'
    
    # Update settings
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('notify_interval', notify_interval))
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('daily_summary', daily_summary))
    
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
    print("🤖 Starting Telegram bot...")
    bot.polling(none_stop=True, interval=1)

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Task Tracker Starting...")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🤖 Telegram User ID: {USER_ID}")
    print("=" * 50)
    
    # Start Telegram bot in background thread
    bot_thread = threading.Thread(target=start_bot_polling, daemon=True)
    bot_thread.start()
    
    # Start Flask app
    port = int(os.getenv('PORT', 8000))
    print(f"🌐 Web server: http://0.0.0.0:{port}")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
