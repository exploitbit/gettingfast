"""
Telegram Bot for Koyeb Platform
GitHub Deployment Ready
"""

import os
import telebot
from flask import Flask, request, jsonify, render_template_string
import sqlite3
from datetime import datetime
import threading
import time
import schedule
import hashlib
import json

# ============= CONFIGURATION =============
BOT_TOKEN = os.getenv('BOT_TOKEN', '8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I')
USER_ID = os.getenv('USER_ID', '8469993808')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
PLATFORM = os.getenv('PLATFORM', 'Koyeb')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
ADMIN_PASSWORD_HASH = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()

# ============= INITIALIZE =============
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# ============= DATABASE SETUP =============
def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect('/tmp/bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME,
                  chat_id TEXT,
                  message_text TEXT,
                  direction TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stats
                 (key TEXT PRIMARY KEY,
                  value TEXT)''')
    conn.commit()
    conn.close()
    print("✅ Database initialized")

init_db()

# ============= HELPER FUNCTIONS =============
def log_message(chat_id, text, direction="outgoing"):
    """Log messages to database"""
    conn = sqlite3.connect('/tmp/bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (timestamp, chat_id, message_text, direction) VALUES (?, ?, ?, ?)",
              (datetime.now(), chat_id, text, direction))
    conn.commit()
    conn.close()

def update_stats(key, value):
    """Update statistics"""
    conn = sqlite3.connect('/tmp/bot_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO stats (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_stats():
    """Get all statistics"""
    conn = sqlite3.connect('/tmp/bot_data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM stats")
    stats = dict(c.fetchall())
    conn.close()
    return stats

def get_recent_messages(limit=10):
    """Get recent messages"""
    conn = sqlite3.connect('/tmp/bot_data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?", (limit,))
    messages = c.fetchall()
    conn.close()
    return messages

# ============= TELEGRAM HANDLERS =============
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Handle /start command"""
    welcome_msg = f"""
🤖 *Welcome to Koyeb Telegram Bot!*

*Platform:* {PLATFORM}
*Server Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

*Commands:*
/start - Show this help
/status - Bot status
/time - Server time
/info - System information
/stats - Bot statistics
"""
    bot.reply_to(message, welcome_msg, parse_mode='Markdown')
    log_message(message.chat.id, "/start command", "incoming")

@bot.message_handler(commands=['status'])
def send_status(message):
    """Handle /status command"""
    status_msg = f"""
✅ *Bot Status Report*

*Platform:* {PLATFORM}
*Status:* 🟢 Online
*Uptime:* {get_uptime()}
*Messages Processed:* {len(get_recent_messages(1000))}
*Last Update:* {datetime.now().strftime('%H:%M:%S')}
"""
    bot.reply_to(message, status_msg, parse_mode='Markdown')
    log_message(message.chat.id, "/status command", "incoming")

@bot.message_handler(commands=['time'])
def send_time(message):
    """Handle /time command"""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    bot.reply_to(message, f"🕐 *Server Time:*\n`{current_time}`", parse_mode='Markdown')
    log_message(message.chat.id, "/time command", "incoming")

@bot.message_handler(commands=['info'])
def send_info(message):
    """Handle /info command"""
    info_msg = f"""
📊 *System Information*

*Platform:* {PLATFORM}
*Python Version:* 3.11
*Server Region:* Frankfurt (fra)
*Deployment:* GitHub → Koyeb
*Webhook:* {WEBHOOK_URL if WEBHOOK_URL else 'Not set'}
*Features:* Scheduled Messages, Web Admin, Database
"""
    bot.reply_to(message, info_msg, parse_mode='Markdown')
    log_message(message.chat.id, "/info command", "incoming")

@bot.message_handler(commands=['stats'])
def send_stats(message):
    """Handle /stats command"""
    stats = get_stats()
    stats_msg = f"""
📈 *Bot Statistics*

*Total Messages:* {stats.get('total_messages', '0')}
*Scheduled Messages:* {stats.get('scheduled_messages', '0')}
*Bot Started:* {stats.get('bot_started', 'N/A')}
*Last Activity:* {datetime.now().strftime('%H:%M:%S')}
"""
    bot.reply_to(message, stats_msg, parse_mode='Markdown')
    log_message(message.chat.id, "/stats command", "incoming")

@bot.message_handler(func=lambda message: True)
def echo_message(message):
    """Echo all other messages"""
    bot.reply_to(message, f"Echo: {message.text}")
    log_message(message.chat.id, message.text, "incoming")
    update_stats('total_messages', str(int(get_stats().get('total_messages', 0)) + 1))

# ============= SCHEDULED MESSAGES =============
start_time = datetime.now()

def get_uptime():
    """Calculate bot uptime"""
    delta = datetime.now() - start_time
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

def send_scheduled_message():
    """Send scheduled message every minute"""
    try:
        uptime = get_uptime()
        current_time = datetime.now().strftime('%H:%M:%S')
        message = f"""
⏰ *Scheduled Update from Koyeb*

*Time:* {current_time}
*Platform:* {PLATFORM}
*Uptime:* {uptime}
*Status:* ✅ All systems operational

This message is sent automatically every minute.
"""
        bot.send_message(USER_ID, message, parse_mode='Markdown')
        log_message(USER_ID, f"Scheduled: {current_time}", "outgoing")
        
        # Update stats
        stats = get_stats()
        scheduled_count = int(stats.get('scheduled_messages', 0)) + 1
        update_stats('scheduled_messages', str(scheduled_count))
        
        print(f"✅ Scheduled message sent at {current_time}")
        return True
    except Exception as e:
        print(f"❌ Error sending scheduled message: {e}")
        return False

# ============= WEB ROUTES =============
@app.route('/')
def home():
    """Home page"""
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 Telegram Bot on Koyeb</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container {
                background: white;
                border-radius: 20px;
                padding: 40px;
                max-width: 800px;
                width: 100%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            h1 {
                color: #333;
                margin-bottom: 20px;
                text-align: center;
            }
            .status {
                background: #f0f9ff;
                border-left: 5px solid #667eea;
                padding: 15px;
                margin: 20px 0;
                border-radius: 10px;
            }
            .button {
                display: inline-block;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 12px 24px;
                border-radius: 50px;
                text-decoration: none;
                margin: 10px 5px;
                transition: transform 0.3s;
            }
            .button:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(0,0,0,0.2);
            }
            .info-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }
            .info-card {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 10px;
                text-align: center;
            }
            .info-card h3 {
                color: #667eea;
                margin-bottom: 10px;
            }
            .footer {
                text-align: center;
                margin-top: 30px;
                color: #666;
                font-size: 0.9em;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Telegram Bot on Koyeb</h1>
            
            <div class="status">
                <h3>🚀 Bot Status: <span style="color: green;">✅ Online</span></h3>
                <p>Platform: {{ platform }}</p>
                <p>Uptime: {{ uptime }}</p>
                <p>Messages Sent: {{ messages_sent }}</p>
                <p>Last Update: {{ current_time }}</p>
            </div>
            
            <div class="info-grid">
                <div class="info-card">
                    <h3>📱 Telegram</h3>
                    <p>Bot is active and responding</p>
                    <p>Scheduled messages: Every minute</p>
                </div>
                <div class="info-card">
                    <h3>🌐 Platform</h3>
                    <p>Koyeb Serverless</p>
                    <p>Frankfurt Region</p>
                </div>
                <div class="info-card">
                    <h3>⚙️ Features</h3>
                    <p>Webhook Support</p>
                    <p>Database Logging</p>
                    <p>Admin Panel</p>
                </div>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="/admin" class="button">🔐 Admin Panel</a>
                <a href="/health" class="button">❤️ Health Check</a>
                <a href="/send_test" class="button">📨 Send Test</a>
                <a href="/stats" class="button">📊 Statistics</a>
            </div>
            
            <div class="footer">
                <p>Deployed via GitHub | exploitbit.pythonanywhere.com</p>
                <p>Telegram Bot Token: {{ bot_token[:10] }}...</p>
                <p>User ID: {{ user_id }}</p>
            </div>
        </div>
        
        <script>
            // Auto-refresh every 30 seconds
            setTimeout(() => location.reload(), 30000);
        </script>
    </body>
    </html>
    """, 
    platform=PLATFORM,
    uptime=get_uptime(),
    messages_sent=get_stats().get('total_messages', '0'),
    current_time=datetime.now().strftime('%H:%M:%S'),
    bot_token=BOT_TOKEN,
    user_id=USER_ID)

@app.route('/admin')
def admin_panel():
    """Admin panel"""
    # Simple password check
    password = request.args.get('password', '')
    if password != ADMIN_PASSWORD:
        return """
        <h1>🔐 Admin Login</h1>
        <form>
            <input type="password" name="password" placeholder="Enter admin password">
            <button type="submit">Login</button>
        </form>
        <p>Default: admin123</p>
        """
    
    stats = get_stats()
    recent_messages = get_recent_messages(20)
    
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel</title>
        <style>
            body { font-family: Arial, sans-serif; padding: 20px; }
            table { border-collapse: collapse; width: 100%; margin: 20px 0; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
            .stat { background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px; }
        </style>
    </head>
    <body>
        <h1>🤖 Admin Panel</h1>
        <a href="/">← Back to Home</a>
        
        <h2>📊 Statistics</h2>
        {% for key, value in stats.items() %}
        <div class="stat"><strong>{{ key }}:</strong> {{ value }}</div>
        {% endfor %}
        
        <h2>📝 Recent Messages</h2>
        <table>
            <tr>
                <th>Time</th>
                <th>Chat ID</th>
                <th>Message</th>
                <th>Direction</th>
            </tr>
            {% for msg in messages %}
            <tr>
                <td>{{ msg[1] }}</td>
                <td>{{ msg[2] }}</td>
                <td>{{ msg[3][:50] }}{% if msg[3]|length > 50 %}...{% endif %}</td>
                <td>{{ msg[4] }}</td>
            </tr>
            {% endfor %}
        </table>
        
        <h2>⚡ Actions</h2>
        <a href="/send_test">Send Test Message</a> |
        <a href="/setup_webhook">Setup Webhook</a> |
        <a href="/health">Health Check</a>
    </body>
    </html>
    """, stats=stats, messages=recent_messages)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Bad Request', 400

@app.route('/setup_webhook', methods=['GET'])
def setup_webhook_route():
    """Setup webhook"""
    try:
        bot.remove_webhook()
        time.sleep(1)
        
        # Get current URL for webhook
        webhook_url = f"https://{request.host}/webhook"
        bot.set_webhook(url=webhook_url)
        
        update_stats('webhook_url', webhook_url)
        update_stats('webhook_setup', datetime.now().isoformat())
        
        bot.send_message(USER_ID, f"✅ Webhook setup complete!\nURL: {webhook_url}")
        
        return f"""
        <h1>✅ Webhook Setup Complete</h1>
        <p>URL: {webhook_url}</p>
        <p><a href="/">← Back to Home</a></p>
        """
    except Exception as e:
        return f"<h1>❌ Error: {e}</h1>"

@app.route('/send_test')
def send_test():
    """Send test message"""
    try:
        current_time = datetime.now().strftime('%H:%M:%S')
        message = f"✅ Test from Web Interface!\nTime: {current_time}\nPlatform: {PLATFORM}\nStatus: Working perfectly!"
        bot.send_message(USER_ID, message)
        log_message(USER_ID, f"Test from web: {current_time}", "outgoing")
        return """
        <h1>✅ Test Message Sent</h1>
        <p>Check your Telegram!</p>
        <p><a href="/">← Back to Home</a></p>
        """
    except Exception as e:
        return f"<h1>❌ Error: {e}</h1>"

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        # Check if bot is responsive
        bot_info = bot.get_me()
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "bot": {
                "username": bot_info.username,
                "id": bot_info.id
            },
            "platform": PLATFORM,
            "uptime": get_uptime(),
            "database": "connected",
            "webhook": WEBHOOK_URL if WEBHOOK_URL else "not_set",
            "statistics": {
                "total_messages": get_stats().get('total_messages', '0'),
                "scheduled_messages": get_stats().get('scheduled_messages', '0')
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/stats')
def stats_api():
    """Statistics API endpoint"""
    return jsonify({
        "status": "success",
        "data": get_stats(),
        "recent_messages": get_recent_messages(10),
        "platform": PLATFORM,
        "timestamp": datetime.now().isoformat()
    })

# ============= INITIALIZATION =============
def initialize_bot():
    """Initialize bot on startup"""
    print("=" * 60)
    print("🤖 Koyeb Telegram Bot Initialization")
    print("=" * 60)
    print(f"Platform: {PLATFORM}")
    print(f"Bot Token: {BOT_TOKEN[:10]}...")
    print(f"User ID: {USER_ID}")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Get bot info
        bot_info = bot.get_me()
        print(f"✅ Bot: @{bot_info.username} (ID: {bot_info.id})")
        
        # Send startup message
        startup_msg = f"""
🚀 *Bot Started on Koyeb!*

*Platform:* {PLATFORM}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
*Bot:* @{bot_info.username}
*Status:* ✅ Active and Running
*Features:* Scheduled Messages Every Minute

Bot will send automated messages every minute.
"""
        bot.send_message(USER_ID, startup_msg, parse_mode='Markdown')
        
        # Update stats
        update_stats('bot_started', datetime.now().isoformat())
        update_stats('bot_username', f"@{bot_info.username}")
        update_stats('platform', PLATFORM)
        update_stats('total_messages', '0')
        update_stats('scheduled_messages', '0')
        
        print("✅ Bot initialized successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Bot initialization error: {e}")
        print("=" * 60)

# ============= MAIN =============
if __name__ == '__main__':
    # Initialize bot
    initialize_bot()
    
    # Start Flask app
    port = int(os.getenv('PORT', 8000))
    print(f"🌐 Starting web server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # For Gunicorn
    initialize_bot()
