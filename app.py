"""
Simplified Telegram Bot for Task Tracker Notifications
Monitors JSON files and sends Telegram notifications
"""

import os
import json
import time
import threading
from datetime import datetime, timedelta
import telebot
from flask import Flask, request, jsonify

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"
ADMIN_PASSWORD = "admin123"

# File paths
TASKS_FILE = "tasks.json"
NOTES_FILE = "notes.json"
NOTIFICATIONS_FILE = "notifications.json"
TELEGRAM_LOG_FILE = "telegram_log.json"

# ============= INITIALIZE =============
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# Global variables
monitor_active = True
app_start_time = datetime.now()

# ============= HELPER FUNCTIONS =============
def load_json_file(filepath):
    """Load data from JSON file"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
    except:
        pass
    return []

def save_json_file(filepath, data):
    """Save data to JSON file"""
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except:
        return False

def log_telegram_notification(message, success=True):
    """Log Telegram notification"""
    logs = load_json_file(TELEGRAM_LOG_FILE)
    if not isinstance(logs, list):
        logs = []
    
    logs.append({
        'timestamp': datetime.now().isoformat(),
        'message': message[:100] + '...' if len(message) > 100 else message,
        'success': success
    })
    
    # Keep only last 50 logs
    if len(logs) > 50:
        logs = logs[-50:]
    
    save_json_file(TELEGRAM_LOG_FILE, logs)

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
        tasks = load_json_file(TASKS_FILE)
        if not tasks:
            return
        
        current_time = datetime.now()
        
        for task in tasks:
            # Skip if task is completed or notifications disabled
            if task.get('completed') or not task.get('notify_enabled'):
                continue
            
            task_id = task.get('id')
            task_title = task.get('title', 'Untitled Task')
            start_time_str = task.get('start_time')
            last_notified = task.get('last_notified')
            
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
                # Check if we need to send a reminder
                reminder_minutes = int(time_diff)
                
                # Send reminder if it's the right minute (1, 2, 3, ..., 10 minutes before)
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
                        task['last_notified'] = current_time.strftime('%Y-%m-%d %H:%M:%S')
                        save_json_file(TASKS_FILE, tasks)
            
    except Exception as e:
        print(f"Error checking task reminders: {e}")

def check_note_reminders():
    """Check and send note reminders"""
    try:
        notes = load_json_file(NOTES_FILE)
        if not notes:
            return
        
        current_time = datetime.now()
        
        for note in notes:
            # Skip if notifications disabled
            if not note.get('notify_enabled'):
                continue
            
            note_id = note.get('id')
            note_title = note.get('title', 'Untitled Note')
            interval_hours = note.get('notify_interval', 0)
            last_notified = note.get('last_notified')
            
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
            
            description = note.get('description', '')
            if description:
                # Strip HTML tags and limit length
                import re
                clean_desc = re.sub('<[^<]+?>', '', description)
                if len(clean_desc) > 200:
                    clean_desc = clean_desc[:200] + '...'
                message += f"\n{clean_desc}"
            
            if send_telegram_message(message):
                # Update last_notified time
                note['last_notified'] = current_time.strftime('%Y-%m-%d %H:%M:%S')
                save_json_file(NOTES_FILE, notes)
            
    except Exception as e:
        print(f"Error checking note reminders: {e}")

def send_hourly_report():
    """Send hourly task status report"""
    try:
        notification_settings = load_json_file(NOTIFICATIONS_FILE)
        if not isinstance(notification_settings, dict):
            notification_settings = {}
        
        # Check if hourly reports are enabled
        if not notification_settings.get('hourly_report', True):
            return
        
        tasks = load_json_file(TASKS_FILE)
        if not tasks:
            return
        
        current_time = datetime.now()
        current_date = current_time.date()
        
        # Filter tasks for today
        today_tasks = []
        for task in tasks:
            try:
                task_date = datetime.strptime(task.get('start_time', ''), '%Y-%m-%d %H:%M:%S').date()
                if task_date == current_date:
                    today_tasks.append(task)
            except:
                pass
        
        if not today_tasks:
            message = f"📊 <b>Hourly Task Report</b>\n"
            message += f"🕐 {current_time.strftime('%I:%M %p')}\n"
            message += f"📅 {current_time.strftime('%B %d, %Y')}\n"
            message += f"✅ No tasks for today!"
        else:
            completed_tasks = [t for t in today_tasks if t.get('completed')]
            pending_tasks = [t for t in today_tasks if not t.get('completed')]
            
            message = f"📊 <b>Hourly Task Report</b>\n"
            message += f"🕐 {current_time.strftime('%I:%M %p')}\n"
            message += f"📅 {current_time.strftime('%B %d, %Y')}\n"
            message += f"📋 Total: {len(today_tasks)} tasks\n\n"
            
            message += f"✅ <b>Completed ({len(completed_tasks)})</b>\n"
            for task in completed_tasks[:5]:  # Show first 5 completed
                message += f"   ✓ {task.get('title', 'Untitled')}\n"
            if len(completed_tasks) > 5:
                message += f"   ... and {len(completed_tasks) - 5} more\n"
            
            message += f"\n⏳ <b>Pending ({len(pending_tasks)})</b>\n"
            for task in pending_tasks[:5]:  # Show first 5 pending
                start_time = datetime.strptime(task.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
                time_str = start_time.strftime('%I:%M %p')
                message += f"   • {task.get('title', 'Untitled')} ({time_str})\n"
            if len(pending_tasks) > 5:
                message += f"   ... and {len(pending_tasks) - 5} more\n"
        
        send_telegram_message(message)
        
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
            
            time.sleep(10)  # Sleep for 10 seconds
            
        except Exception as e:
            print(f"Monitoring error: {e}")
            time.sleep(30)

# ============= TELEGRAM COMMANDS =============
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
/report - Get current task status
/test - Send test notification
/help - Show this message

<b>Features:</b>
• Task reminders (10 minutes before start)
• Note reminders (custom intervals)
• Hourly status reports
• Real-time monitoring
"""
    bot.reply_to(message, welcome_msg, parse_mode='HTML')

@bot.message_handler(commands=['status'])
def send_status(message):
    """Send bot status"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    uptime = datetime.now() - app_start_time
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds % 3600) // 60
    
    tasks = load_json_file(TASKS_FILE)
    notes = load_json_file(NOTES_FILE)
    
    status_msg = f"""
📊 <b>Bot Status</b>

✅ <b>Online</b>
⏰ Uptime: {uptime.days}d {hours}h {minutes}m
📅 Started: {app_start_time.strftime('%Y-%m-%d %H:%M')}

<b>Statistics:</b>
📋 Tasks: {len(tasks) if tasks else 0}
📝 Notes: {len(notes) if notes else 0}
🔔 Monitor: {'Active' if monitor_active else 'Paused'}

<b>Last Check:</b> {datetime.now().strftime('%H:%M:%S')}
"""
    bot.reply_to(message, status_msg, parse_mode='HTML')

@bot.message_handler(commands=['report'])
def send_report(message):
    """Send current task report"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    send_hourly_report()
    bot.reply_to(message, "📊 Report sent!")

@bot.message_handler(commands=['test'])
def send_test(message):
    """Send test notification"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    test_msg = f"""
✅ <b>Test Notification</b>

Time: {datetime.now().strftime('%H:%M:%S')}
Date: {datetime.now().strftime('%Y-%m-%d')}
Status: Bot is working correctly!

This is a test message to verify Telegram notifications are working.
"""
    if send_telegram_message(test_msg):
        bot.reply_to(message, "✅ Test message sent!")
    else:
        bot.reply_to(message, "❌ Failed to send test message")

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

# ============= WEB ROUTES =============
@app.route('/')
def home():
    """Home page"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Task Tracker Bot</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .container {
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
                border-bottom: 2px solid #4CAF50;
                padding-bottom: 10px;
            }
            .status {
                padding: 15px;
                background: #e8f5e9;
                border-radius: 5px;
                margin: 20px 0;
            }
            .btn {
                display: inline-block;
                background: #4CAF50;
                color: white;
                padding: 10px 20px;
                text-decoration: none;
                border-radius: 5px;
                margin: 5px;
            }
            .btn:hover {
                background: #45a049;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Task Tracker Bot</h1>
            
            <div class="status">
                <h3>✅ Bot Status: Online</h3>
                <p><strong>Uptime:</strong> """ + str(datetime.now() - app_start_time).split('.')[0] + """</p>
                <p><strong>Started:</strong> """ + app_start_time.strftime('%Y-%m-%d %H:%M:%S') + """</p>
                <p><strong>Monitoring:</strong> """ + ("Active" if monitor_active else "Paused") + """</p>
            </div>
            
            <h3>📊 Statistics</h3>
            <p><strong>Tasks:</strong> """ + str(len(load_json_file(TASKS_FILE))) + """</p>
            <p><strong>Notes:</strong> """ + str(len(load_json_file(NOTES_FILE))) + """</p>
            
            <h3>⚡ Quick Actions</h3>
            <a href="/send_test" class="btn">Send Test Message</a>
            <a href="/send_report" class="btn">Send Hourly Report</a>
            <a href="/status" class="btn">Bot Status</a>
            
            <h3>📱 Telegram Commands</h3>
            <p>Send these commands to the bot:</p>
            <ul>
                <li><code>/start</code> - Welcome message</li>
                <li><code>/status</code> - Bot status</li>
                <li><code>/report</code> - Task report</li>
                <li><code>/test</code> - Test notification</li>
                <li><code>/help</code> - Help menu</li>
            </ul>
            
            <h3>🔔 Features</h3>
            <ul>
                <li>Task reminders (10 minutes before start)</li>
                <li>Note reminders (custom intervals)</li>
                <li>Hourly status reports (24x per day)</li>
                <li>Real-time monitoring</li>
            </ul>
            
            <p style="margin-top: 30px; color: #666; font-size: 0.9em;">
                Bot User ID: """ + USER_ID + """<br>
                Last updated: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
            </p>
        </div>
    </body>
    </html>
    """

@app.route('/send_test')
def web_send_test():
    """Send test message via web"""
    test_msg = f"""
✅ <b>Test from Web Interface</b>

Time: {datetime.now().strftime('%H:%M:%S')}
Interface: Web Browser
Status: Working correctly!
"""
    if send_telegram_message(test_msg):
        return "<h1>✅ Test message sent!</h1><p><a href='/'>← Back</a></p>"
    else:
        return "<h1>❌ Failed to send message</h1><p><a href='/'>← Back</a></p>"

@app.route('/send_report')
def web_send_report():
    """Send report via web"""
    send_hourly_report()
    return "<h1>✅ Hourly report sent!</h1><p><a href='/'>← Back</a></p>"

@app.route('/status')
def web_status():
    """Web status API"""
    uptime = datetime.now() - app_start_time
    
    return jsonify({
        "status": "online",
        "monitor_active": monitor_active,
        "uptime": str(uptime).split('.')[0],
        "started": app_start_time.isoformat(),
        "tasks": len(load_json_file(TASKS_FILE)),
        "notes": len(load_json_file(NOTES_FILE)),
        "timestamp": datetime.now().isoformat()
    })

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
            return 'Error', 500
    return 'Bad Request', 400

# ============= INITIALIZATION =============
def initialize():
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
• Hourly status reports (24x per day)

Send /help for commands.
"""
        send_telegram_message(startup_msg)
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
    
    # Use polling for development, webhook for production
    try:
        # Start polling in separate thread
        polling_thread = threading.Thread(target=bot.polling, kwargs={'none_stop': True, 'interval': 1}, daemon=True)
        polling_thread.start()
        print("✅ Telegram polling started")
    except:
        print("⚠️ Could not start polling, using webhook only")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
else:
    # For production deployment
    initialize()
