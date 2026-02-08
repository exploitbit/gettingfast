"""
Telegram Bot for Koyeb Free Tier - Complete Solution
No background workers needed - Uses threading + APScheduler
URL: patient-maxie-sandip232-786edcb8.koyeb.app
"""

from flask import Flask, request, jsonify
import telebot
import threading
import time
from datetime import datetime
import os
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import schedule
import requests
import sqlite3
import json

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"
KOYEB_URL = "patient-maxie-sandip232-786edcb8.koyeb.app"
ADMIN_PASSWORD = "admin123"

# ============= INITIALIZE =============
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# Global variables
message_count = 0
last_message_time = None
scheduler_active = True
app_start_time = datetime.now()

# Initialize APScheduler for keep-alive
keepalive_scheduler = BackgroundScheduler()

# ============= DATABASE SETUP =============
def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect('/tmp/bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS bot_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME,
                  type TEXT,
                  message TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME,
                  chat_id TEXT,
                  message_text TEXT,
                  direction TEXT)''')
    conn.commit()
    conn.close()
    log_activity("DATABASE", "Database initialized")

def log_activity(log_type, message):
    """Log activity to database"""
    conn = sqlite3.connect('/tmp/bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO bot_logs (timestamp, type, message) VALUES (?, ?, ?)",
              (datetime.now(), log_type, message))
    conn.commit()
    conn.close()
    print(f"[{log_type}] {message}")

def log_message(chat_id, text, direction="outgoing"):
    """Log message to database"""
    conn = sqlite3.connect('/tmp/bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (timestamp, chat_id, message_text, direction) VALUES (?, ?, ?, ?)",
              (datetime.now(), chat_id, text, direction))
    conn.commit()
    conn.close()

def get_stats():
    """Get statistics"""
    conn = sqlite3.connect('/tmp/bot_data.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages WHERE direction='outgoing'")
    outgoing = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM messages WHERE direction='incoming'")
    incoming = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM bot_logs")
    logs = c.fetchone()[0]
    conn.close()
    return {
        'outgoing_messages': outgoing,
        'incoming_messages': incoming,
        'total_logs': logs,
        'scheduled_count': message_count
    }

# ============= TELEGRAM HANDLERS =============
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    global message_count
    message_count += 1
    
    welcome_msg = f"""
🤖 *Welcome to Koyeb Telegram Bot!*

*URL:* {KOYEB_URL}
*Status:* ✅ Online
*Scheduled Messages:* {message_count}
*Uptime:* {get_uptime()}

*Commands:*
/start - Show this message
/status - Bot status  
/time - Server time
/stats - Message statistics
/now - Send immediate message
/schedule on|off - Control scheduler

*Admin:* /admin [password]
"""
    bot.reply_to(message, welcome_msg, parse_mode='Markdown')
    log_message(message.chat.id, "/start", "incoming")
    log_activity("COMMAND", f"/start from {message.chat.id}")

@bot.message_handler(commands=['status'])
def send_status(message):
    stats = get_stats()
    status_msg = f"""
📊 *Bot Status Report*

*Platform:* Koyeb Free Tier
*URL:* {KOYEB_URL}
*Status:* {'🟢 Running' if scheduler_active else '⏸️ Paused'}
*Uptime:* {get_uptime()}
*Messages:* {stats['outgoing_messages']} sent, {stats['incoming_messages']} received
*Last Scheduled:* {last_message_time or 'None yet'}
*Memory:* Threading + APScheduler
"""
    bot.reply_to(message, status_msg, parse_mode='Markdown')
    log_message(message.chat.id, "/status", "incoming")

@bot.message_handler(commands=['time'])
def send_time(message):
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    bot.reply_to(message, f"🕐 *Server Time:*\n`{current_time}`", parse_mode='Markdown')
    log_message(message.chat.id, "/time", "incoming")

@bot.message_handler(commands=['stats'])
def send_stats(message):
    stats = get_stats()
    stats_msg = f"""
📈 *Message Statistics*

*Total Sent:* {stats['outgoing_messages']}
*Total Received:* {stats['incoming_messages']}
*Scheduled Count:* {message_count}
*Log Entries:* {stats['total_logs']}
*Uptime:* {get_uptime()}
*Scheduler:* {'✅ Active' if scheduler_active else '⏸️ Paused'}
"""
    bot.reply_to(message, stats_msg, parse_mode='Markdown')
    log_message(message.chat.id, "/stats", "incoming")

@bot.message_handler(commands=['now'])
def send_now_cmd(message):
    """Send immediate message via command"""
    current_time = datetime.now().strftime('%H:%M:%S')
    msg = f"🚀 *Immediate Message*\nTime: {current_time}\nFrom: Command\nChat ID: {message.chat.id}"
    bot.send_message(message.chat.id, msg, parse_mode='Markdown')
    log_message(message.chat.id, "/now command", "incoming")

@bot.message_handler(commands=['schedule'])
def control_schedule(message):
    global scheduler_active
    parts = message.text.split()
    if len(parts) > 1:
        command = parts[1].lower()
        if command == 'on':
            scheduler_active = True
            response = "✅ Scheduler activated"
        elif command == 'off':
            scheduler_active = False
            response = "⏸️ Scheduler paused"
        else:
            response = "Usage: /schedule on|off"
    else:
        response = f"Scheduler is {'✅ ON' if scheduler_active else '⏸️ OFF'}"
    
    bot.reply_to(message, response, parse_mode='Markdown')
    log_message(message.chat.id, f"/schedule {parts[1] if len(parts)>1 else 'status'}", "incoming")

@bot.message_handler(commands=['admin'])
def admin_command(message):
    parts = message.text.split()
    if len(parts) > 1 and parts[1] == ADMIN_PASSWORD:
        admin_msg = f"""
🔐 *Admin Panel*

*URL:* {KOYEB_URL}
*Token:* {BOT_TOKEN[:10]}...
*User ID:* {USER_ID}
*Webhook:* https://{KOYEB_URL}/webhook
*Admin Panel:* https://{KOYEB_URL}/admin?password={ADMIN_PASSWORD}
*Health Check:* https://{KOYEB_URL}/health
"""
        bot.reply_to(message, admin_msg, parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ Admin access required", parse_mode='Markdown')
    log_message(message.chat.id, "/admin attempt", "incoming")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    response = f"Echo: *{message.text}*\n\nSend /help for commands"
    bot.reply_to(message, response, parse_mode='Markdown')
    log_message(message.chat.id, message.text, "incoming")

# ============= SCHEDULED MESSAGES =============
def send_scheduled_message():
    """Send scheduled message every minute"""
    global message_count, last_message_time
    
    if not scheduler_active:
        return
    
    try:
        current_time = datetime.now().strftime('%H:%M:%S')
        uptime = get_uptime()
        stats = get_stats()
        
        message = f"""
⏰ *Automatic Message from Koyeb*

*Time:* {current_time}
*URL:* {KOYEB_URL}
*Message #:* {message_count + 1}
*Total Sent:* {stats['outgoing_messages']}
*Uptime:* {uptime}
*Status:* ✅ Everything working perfectly!

Next message in 1 minute. ⏱️
"""
        bot.send_message(USER_ID, message, parse_mode='Markdown')
        
        message_count += 1
        last_message_time = current_time
        log_message(USER_ID, f"Scheduled #{message_count}", "outgoing")
        log_activity("SCHEDULER", f"Message #{message_count} sent at {current_time}")
        
        # Schedule next message
        threading.Timer(60.0, send_scheduled_message).start()
        
    except Exception as e:
        log_activity("ERROR", f"Scheduler error: {str(e)}")
        # Retry after 30 seconds
        threading.Timer(30.0, send_scheduled_message).start()

# ============= WEB ROUTES =============
@app.route('/')
def home():
    stats = get_stats()
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 Koyeb Telegram Bot</title>
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
                max-width: 1000px;
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
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 20px;
                padding: 30px;
            }}
            .stat-card {{
                background: #f8f9fa;
                border-radius: 15px;
                padding: 25px;
                text-align: center;
                transition: all 0.3s;
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
            .controls {{
                padding: 30px;
                background: #f8f9fa;
                margin: 20px;
                border-radius: 15px;
                text-align: center;
            }}
            .btn {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 50px;
                font-size: 16px;
                cursor: pointer;
                margin: 10px;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-block;
            }}
            .btn:hover {{
                transform: scale(1.05);
                box-shadow: 0 10px 20px rgba(0,0,0,0.2);
            }}
            .btn-success {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }}
            .btn-danger {{ background: linear-gradient(135deg, #ff416c 0%, #ff4b2b 100%); }}
            .btn-warning {{ background: linear-gradient(135deg, #f7971e 0%, #ffd200 100%); }}
            .info-box {{
                background: #e9f7fe;
                padding: 25px;
                margin: 20px;
                border-radius: 15px;
                border-left: 5px solid #2196F3;
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
                .controls {{ margin: 10px; padding: 20px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>🤖 Telegram Bot on Koyeb</h1>
                <p style="opacity: 0.9;">Free Tier • No Workers Needed • Scheduled Messages</p>
                <p style="margin-top: 10px; font-size: 1.2em;">{KOYEB_URL}</p>
            </header>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>📨 Messages Sent</h3>
                    <div class="stat-value">{stats['outgoing_messages']}</div>
                    <p>Scheduled: {message_count}</p>
                </div>
                <div class="stat-card">
                    <h3>⏰ Uptime</h3>
                    <div class="stat-value">{get_uptime().split()[0]}</div>
                    <p>{get_uptime()}</p>
                </div>
                <div class="stat-card">
                    <h3>📊 Status</h3>
                    <div class="stat-value" style="color: {'#28a745' if scheduler_active else '#ffc107'}">
                        {'✅ ON' if scheduler_active else '⏸️ OFF'}
                    </div>
                    <p>Scheduler Active</p>
                </div>
                <div class="stat-card">
                    <h3>🕐 Server Time</h3>
                    <div class="stat-value">{datetime.now().strftime('%H:%M')}</div>
                    <p>{datetime.now().strftime('%Y-%m-%d')}</p>
                </div>
            </div>
            
            <div class="controls">
                <h2 style="color: #333; margin-bottom: 20px;">⚡ Quick Actions</h2>
                <a href="/send_now" class="btn">📨 Send Message Now</a>
                <a href="/health" class="btn btn-success">❤️ Health Check</a>
                <a href="/start_schedule" class="btn">▶️ Start Schedule</a>
                <a href="/stop_schedule" class="btn btn-warning">⏸️ Stop Schedule</a>
                <a href="/setup_webhook" class="btn">🔗 Setup Webhook</a>
                <a href="/admin?password={ADMIN_PASSWORD}" class="btn btn-danger">🔐 Admin Panel</a>
            </div>
            
            <div class="info-box">
                <h3 style="color: #333;">🎯 How It Works (Free Tier)</h3>
                <p style="color: #555; margin-top: 10px; line-height: 1.6;">
                    ✅ <strong>No background workers needed</strong> - Uses Flask threading<br>
                    ✅ <strong>Scheduled messages every minute</strong> - Threading.Timer based<br>
                    ✅ <strong>Auto-restart mechanism</strong> - Recursive threading calls<br>
                    ✅ <strong>Keep-alive pings</strong> - APScheduler every 5 minutes<br>
                    ✅ <strong>Database logging</strong> - SQLite for persistence<br>
                    ✅ <strong>Web admin panel</strong> - Full control via browser
                </p>
            </div>
            
            <div class="controls">
                <h2 style="color: #333;">📝 Recent Activity</h2>
                <div style="background: white; padding: 15px; border-radius: 10px; max-height: 200px; overflow-y: auto;">
                    <pre style="color: #333; font-family: monospace; font-size: 12px;">
{get_recent_logs(5)}
                    </pre>
                </div>
            </div>
            
            <div class="footer">
                <p>Deployed on Koyeb Free Tier • GitHub Integration • exploitbit.pythonanywhere.com</p>
                <p>Bot Token: {BOT_TOKEN[:10]}... • User ID: {USER_ID} • Password: {ADMIN_PASSWORD}</p>
                <p>Auto-refresh: 30 seconds • Keep-alive: 5 minutes</p>
            </div>
        </div>
        
        <script>
            // Auto-refresh every 30 seconds
            setTimeout(() => location.reload(), 30000);
            
            // Auto-start schedule if not active
            window.addEventListener('load', function() {{
                fetch('/start_schedule').catch(() => {{}});
            }});
            
            // Confirm dangerous actions
            document.querySelectorAll('.btn-danger, .btn-warning').forEach(btn => {{
                btn.addEventListener('click', function(e) {{
                    if (!confirm('Are you sure?')) {{
                        e.preventDefault();
                    }}
                }});
            }});
        </script>
    </body>
    </html>
    """

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        bot_info = bot.get_me()
        stats = get_stats()
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "url": KOYEB_URL,
            "platform": "Koyeb Free Tier",
            "bot": {
                "username": bot_info.username,
                "id": bot_info.id
            },
            "scheduler": {
                "active": scheduler_active,
                "messages_sent": message_count,
                "last_message": last_message_time
            },
            "statistics": stats,
            "uptime": get_uptime(),
            "memory": "threading_apscheduler"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/send_now')
def send_now():
    """Send immediate message via web"""
    try:
        current_time = datetime.now().strftime('%H:%M:%S')
        message = f"🚀 *Immediate Message from Web*\nTime: {current_time}\nURL: {KOYEB_URL}\nTrigger: Web Interface"
        bot.send_message(USER_ID, message, parse_mode='Markdown')
        
        log_message(USER_ID, f"Web trigger: {current_time}", "outgoing")
        log_activity("WEB", f"Manual message sent at {current_time}")
        
        return f"""
        <!DOCTYPE html>
        <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
        <style>body{{font-family:Arial;text-align:center;padding:50px;}}h1{{color:green;}}</style>
        </head><body>
        <h1>✅ Message Sent Successfully!</h1>
        <p>Check your Telegram bot.</p>
        <p>Total scheduled messages: {message_count}</p>
        <p><a href="/" class="btn">← Back to Dashboard</a></p>
        <script>setTimeout(()=>window.location.href='/',2000);</script>
        </body></html>
        """
    except Exception as e:
        return f"<h1>❌ Error: {e}</h1>"

@app.route('/start_schedule')
def start_schedule():
    """Start the scheduler"""
    global scheduler_active
    scheduler_active = True
    
    # Start the scheduling thread if not already running
    if not hasattr(app, 'scheduler_started') or not app.scheduler_started:
        threading.Thread(target=send_scheduled_message, daemon=True).start()
        app.scheduler_started = True
        log_activity("SCHEDULER", "Scheduler thread started")
    
    bot.send_message(USER_ID, "✅ Scheduler activated! Messages every minute.")
    
    return jsonify({
        "status": "started",
        "message": "Scheduler activated",
        "interval": "60 seconds",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/stop_schedule')
def stop_schedule():
    """Stop the scheduler"""
    global scheduler_active
    scheduler_active = False
    
    bot.send_message(USER_ID, "⏸️ Scheduler paused. No more auto messages.")
    
    return jsonify({
        "status": "stopped",
        "message": "Scheduler paused",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/setup_webhook')
def setup_webhook():
    """Setup Telegram webhook"""
    try:
        webhook_url = f"https://{KOYEB_URL}/webhook"
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)
        
        bot.send_message(USER_ID, f"✅ Webhook setup complete!\nURL: {webhook_url}")
        log_activity("WEBHOOK", f"Webhook set to {webhook_url}")
        
        return f"""
        <!DOCTYPE html>
        <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
        <style>body{{font-family:Arial;text-align:center;padding:50px;}}h1{{color:green;}}</style>
        </head><body>
        <h1>✅ Webhook Setup Complete!</h1>
        <p><strong>URL:</strong> {webhook_url}</p>
        <p>Telegram will now send messages to this URL.</p>
        <p><a href="/">← Back to Dashboard</a></p>
        </body></html>
        """
    except Exception as e:
        return f"<h1>❌ Error: {e}</h1>"

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
            log_activity("WEBHOOK_ERROR", str(e))
            return 'Error', 500
    return 'Bad Request', 400

@app.route('/admin')
def admin_panel():
    """Admin panel"""
    password = request.args.get('password', '')
    if password != ADMIN_PASSWORD:
        return """
        <!DOCTYPE html>
        <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
        <style>body{font-family:Arial;text-align:center;padding:50px;}form{padding:20px;}</style>
        </head><body>
        <h1>🔐 Admin Login</h1>
        <form method="GET">
            <input type="password" name="password" placeholder="Enter admin password" style="padding:10px;font-size:16px;width:300px;">
            <button type="submit" style="padding:10px 20px;font-size:16px;background:#667eea;color:white;border:none;border-radius:5px;">Login</button>
        </form>
        <p>Default password: admin123</p>
        </body></html>
        """
    
    stats = get_stats()
    recent_logs = get_recent_logs(20)
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .card {{ background: white; padding: 20px; margin: 20px 0; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .btn {{ display: inline-block; padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 5px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Admin Panel</h1>
            <a href="/" class="btn">← Dashboard</a>
            
            <div class="card">
                <h2>📊 System Information</h2>
                <p><strong>URL:</strong> {KOYEB_URL}</p>
                <p><strong>Bot Token:</strong> {BOT_TOKEN[:15]}...</p>
                <p><strong>User ID:</strong> {USER_ID}</p>
                <p><strong>Password:</strong> {ADMIN_PASSWORD}</p>
                <p><strong>Webhook:</strong> https://{KOYEB_URL}/webhook</p>
                <p><strong>Uptime:</strong> {get_uptime()}</p>
            </div>
            
            <div class="card">
                <h2>📈 Statistics</h2>
                <table>
                    <tr><th>Metric</th><th>Value</th></tr>
                    <tr><td>Outgoing Messages</td><td>{stats['outgoing_messages']}</td></tr>
                    <tr><td>Incoming Messages</td><td>{stats['incoming_messages']}</td></tr>
                    <tr><td>Scheduled Count</td><td>{message_count}</td></tr>
                    <tr><td>Log Entries</td><td>{stats['total_logs']}</td></tr>
                    <tr><td>Scheduler Status</td><td>{'✅ Active' if scheduler_active else '⏸️ Paused'}</td></tr>
                    <tr><td>Last Message</td><td>{last_message_time or 'None'}</td></tr>
                </table>
            </div>
            
            <div class="card">
                <h2>📝 Recent Logs</h2>
                <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;">
{recent_logs}
                </pre>
            </div>
            
            <div class="card">
                <h2>⚡ Admin Actions</h2>
                <a href="/send_now" class="btn">Send Test Message</a>
                <a href="/start_schedule" class="btn">Start Schedule</a>
                <a href="/stop_schedule" class="btn">Stop Schedule</a>
                <a href="/setup_webhook" class="btn">Setup Webhook</a>
                <a href="/ping" class="btn">Ping Self</a>
                <a href="/health" class="btn">Health Check</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/ping')
def ping():
    """Keep-alive ping endpoint"""
    log_activity("PING", "Keep-alive ping received")
    return jsonify({
        "status": "pong",
        "timestamp": datetime.now().isoformat(),
        "url": KOYEB_URL,
        "scheduler": scheduler_active
    })

# ============= HELPER FUNCTIONS =============
def get_uptime():
    """Calculate uptime"""
    delta = datetime.now() - app_start_time
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    else:
        return f"{minutes}m {seconds}s"

def get_recent_logs(limit=10):
    """Get recent logs from database"""
    try:
        conn = sqlite3.connect('/tmp/bot_data.db')
        c = conn.cursor()
        c.execute("SELECT timestamp, type, message FROM bot_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
        logs = c.fetchall()
        conn.close()
        
        result = ""
        for log in logs:
            result += f"{log[0]} [{log[1]}] {log[2]}\n"
        return result if result else "No logs yet"
    except:
        return "Logs unavailable"

# ============= KEEP-ALIVE MECHANISM =============
def ping_self():
    """Ping the app to keep it awake"""
    try:
        response = requests.get(f"https://{KOYEB_URL}/ping", timeout=10)
        log_activity("KEEPALIVE", f"Self-ping successful: {response.status_code}")
    except Exception as e:
        log_activity("KEEPALIVE_ERROR", f"Self-ping failed: {str(e)}")

# ============= INITIALIZATION =============
def initialize():
    """Initialize the application"""
    print("=" * 70)
    print("🤖 TELEGRAM BOT FOR KOYEB FREE TIER - INITIALIZING")
    print("=" * 70)
    
    # Initialize database
    init_db()
    
    try:
        # Get bot info
        bot_info = bot.get_me()
        print(f"✅ Bot: @{bot_info.username} (ID: {bot_info.id})")
        
        # Setup webhook
        webhook_url = f"https://{KOYEB_URL}/webhook"
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook set to: {webhook_url}")
        
        # Setup APScheduler for keep-alive
        keepalive_scheduler.add_job(ping_self, 'interval', minutes=5)
        keepalive_scheduler.start()
        print("✅ APScheduler started (keep-alive every 5 minutes)")
        
        # Send startup message
        startup_msg = f"""
🚀 *Bot Started on Koyeb Free Tier!*

*URL:* {KOYEB_URL}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
*Bot:* @{bot_info.username}
*Status:* ✅ Active and Running
*Features:* 
• Scheduled messages every minute
• No background workers needed
• Threading + APScheduler
• Web admin panel
• Database logging

Enjoy your bot! 🤖
"""
        bot.send_message(USER_ID, startup_msg, parse_mode='Markdown')
        
        # Start scheduler thread
        threading.Thread(target=send_scheduled_message, daemon=True).start()
        app.scheduler_started = True
        global scheduler_active
        scheduler_active = True
        
        print("✅ Scheduler thread started (messages every minute)")
        print("✅ Startup message sent")
        print("✅ Database initialized")
        
        log_activity("SYSTEM", "Application initialized successfully")
        
    except Exception as e:
        print(f"❌ Initialization error: {e}")
        log_activity("ERROR", f"Initialization failed: {str(e)}")
    
    print("=" * 70)
    print(f"🌐 Access your bot at: https://{KOYEB_URL}")
    print(f"🔐 Admin panel: https://{KOYEB_URL}/admin?password={ADMIN_PASSWORD}")
    print("=" * 70)

# ============= SHUTDOWN HANDLER =============
def shutdown_handler():
    """Handle application shutdown"""
    log_activity("SYSTEM", "Application shutting down")
    keepalive_scheduler.shutdown()
    print("🛑 Application shutdown complete")

# Register shutdown handler
atexit.register(shutdown_handler)

# ============= MAIN =============
if __name__ == '__main__':
    # Initialize application
    initialize()
    
    # Start Flask app
    port = int(os.getenv('PORT', 8000))
    print(f"🌐 Starting web server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # For Gunicorn
    initialize()
