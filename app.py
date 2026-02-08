
"""
Simple Task Tracker with GitHub Storage
Fixed version with better error handling
"""

import os
import json
import threading
from datetime import datetime
import pytz
from flask import Flask, request, render_template_string, send_file, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import base64
import io

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"

# GitHub Configuration - REPLACE THESE!
# Get token from: GitHub → Settings → Developer settings → Personal access tokens
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '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')  # Set in Koyeb env vars
GITHUB_REPO = os.getenv('GITHUB_REPO', 'Qupheyr/gettingfast')  # Your repo
GITHUB_FILE_PATH = "data.json"

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')

# Initialize Flask and Telegram bot
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# ============= GITHUB HELPER FUNCTIONS =============
def load_from_github():
    """Load data from GitHub"""
    try:
        if not GITHUB_TOKEN or GITHUB_TOKEN == 'ghp_yourtokenhere':
            print("❌ GitHub token not configured")
            return None
            
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            content = response.json()["content"]
            decoded = base64.b64decode(content).decode('utf-8')
            data = json.loads(decoded)
            print(f"✅ Loaded {len(data.get('tasks', []))} tasks from GitHub")
            return data
        elif response.status_code == 404:
            print("📄 GitHub file not found, will create on first save")
            return {
                "tasks": [],
                "messages": [],
                "notes": [],
                "last_id": 0
            }
        else:
            print(f"❌ GitHub API Error {response.status_code}: {response.text[:100]}")
            return None
    except requests.exceptions.Timeout:
        print("❌ GitHub request timeout")
        return None
    except Exception as e:
        print(f"❌ Error loading from GitHub: {str(e)}")
        return None

def save_to_github(data):
    """Save data to GitHub"""
    try:
        if not GITHUB_TOKEN or GITHUB_TOKEN == 'ghp_yourtokenhere':
            print("❌ GitHub token not configured, saving locally only")
            return False
            
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Get current SHA
        sha = None
        get_response = requests.get(url, headers=headers, timeout=5)
        if get_response.status_code == 200:
            sha = get_response.json()["sha"]
        
        # Prepare content
        content = json.dumps(data, indent=2, ensure_ascii=False)
        encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        # Create payload
        payload = {
            "message": f"Update tasks - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "content": encoded,
            "branch": "main"
        }
        
        if sha:
            payload["sha"] = sha
        
        # Save to GitHub
        response = requests.put(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code in [200, 201]:
            print(f"✅ Saved {len(data.get('tasks', []))} tasks to GitHub")
            return True
        else:
            print(f"❌ GitHub save failed: {response.status_code} - {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Error saving to GitHub: {str(e)}")
        return False

def get_ist_time():
    """Get current time in IST"""
    return datetime.now(IST)

# ============= LOCAL STORAGE (BACKUP) =============
LOCAL_DATA_FILE = 'data_backup.json'

def load_data():
    """Load data - try GitHub first, then local backup"""
    try:
        github_data = load_from_github()
        
        if github_data is not None:
            # Save local backup
            with open(LOCAL_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(github_data, f, indent=2, ensure_ascii=False)
            return github_data
        
        # Fallback to local file
        if os.path.exists(LOCAL_DATA_FILE):
            with open(LOCAL_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"📂 Loaded {len(data.get('tasks', []))} tasks from local backup")
                return data
                
    except Exception as e:
        print(f"❌ Error loading data: {str(e)}")
    
    # Return empty data if all else fails
    return {
        "tasks": [],
        "messages": [],
        "notes": [],
        "last_id": 0
    }

def save_data(data):
    """Save data - try GitHub, always save local backup"""
    success = False
    
    # Always save local backup first
    try:
        with open(LOCAL_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"📁 Saved {len(data.get('tasks', []))} tasks to local backup")
    except Exception as e:
        print(f"❌ Error saving local backup: {str(e)}")
    
    # Try to save to GitHub
    try:
        success = save_to_github(data)
    except Exception as e:
        print(f"❌ Error in save_to_github: {str(e)}")
        success = False
    
    return success

# ============= TELEGRAM BOT COMMANDS =============
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Send welcome message"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📝 Add Task", callback_data='add_task'),
        InlineKeyboardButton("📋 View Tasks", callback_data='view_tasks'),
        InlineKeyboardButton("📥 Download JSON", callback_data='download_json'),
        InlineKeyboardButton("🔄 Status", callback_data='status')
    )
    
    welcome = f"""
🤖 <b>Task Tracker Bot</b>
<i>Data stored in GitHub</i>

<b>Commands:</b>
• /add - Add new task
• /tasks - View all tasks  
• /download - Download JSON file
• /clear - Clear all data
• /status - Check connection

<b>How to use:</b>
1. Send any message to save as task
2. View at: https://patient-maxie-sandip232-786edcb8.koyeb.app/
3. Download JSON anytime

<b>Current time:</b>
{get_ist_time().strftime('%I:%M %p')} IST
"""
    bot.send_message(message.chat.id, welcome, parse_mode='HTML', reply_markup=keyboard)

@bot.message_handler(commands=['add'])
def add_task_command(message):
    """Add task command"""
    if str(message.chat.id) != USER_ID:
        return
    
    bot.reply_to(message, "📝 <b>Send me your task:</b>\n\nJust type and send your message.", parse_mode='HTML')

@bot.message_handler(func=lambda message: True)
def save_message(message):
    """Save any message as task"""
    if str(message.chat.id) != USER_ID:
        return
    
    try:
        data = load_data()
        
        new_task = {
            "id": data["last_id"] + 1,
            "text": message.text,
            "timestamp": get_ist_time().strftime('%Y-%m-%d %H:%M:%S'),
            "date": get_ist_time().strftime('%B %d, %Y'),
            "time": get_ist_time().strftime('%I:%M %p'),
            "type": "task"
        }
        
        data["tasks"].append(new_task)
        data["last_id"] += 1
        
        success = save_data(data)
        
        if success:
            reply = f"✅ <b>Saved to GitHub!</b>\n\n{message.text}\n\n📅 {new_task['date']}\n⏰ {new_task['time']} IST"
        else:
            reply = f"⚠️ <b>Saved locally only</b>\n\n{message.text}\n\n📅 {new_task['date']}\n⏰ {new_task['time']} IST\n\n<i>GitHub sync failed</i>"
        
        bot.reply_to(message, reply, parse_mode='HTML')
        
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Error:</b> {str(e)}", parse_mode='HTML')

@bot.message_handler(commands=['tasks'])
def show_tasks(message):
    """Show all tasks"""
    if str(message.chat.id) != USER_ID:
        return
    
    try:
        data = load_data()
        
        if not data["tasks"]:
            bot.reply_to(message, "📭 <b>No tasks yet!</b>\n\nSend a message to add your first task.", parse_mode='HTML')
            return
        
        response = "📋 <b>Your Tasks:</b>\n\n"
        
        for task in data["tasks"][-10:]:  # Last 10
            response += f"• {task['text']}\n"
            response += f"  ⏰ {task['time']} | 📅 {task['date']}\n\n"
        
        if len(data["tasks"]) > 10:
            response += f"<i>Showing last 10 of {len(data['tasks'])} tasks</i>"
        
        bot.reply_to(message, response, parse_mode='HTML')
        
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Error loading tasks:</b> {str(e)}", parse_mode='HTML')

@bot.message_handler(commands=['download'])
def download_command(message):
    """Download JSON from GitHub"""
    if str(message.chat.id) != USER_ID:
        return
    
    try:
        # Try to get from GitHub first
        data = load_from_github()
        
        if data is None:
            # Fallback to local
            data = load_data()
            
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        
        # Send as file
        bot.send_document(
            chat_id=message.chat.id,
            document=io.BytesIO(json_str.encode('utf-8')),
            visible_file_name='tasks_data.json',
            caption="📁 <b>Tasks Data</b>\n\nJSON export of all tasks"
        )
        
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Download error:</b> {str(e)}", parse_mode='HTML')

@bot.message_handler(commands=['status'])
def status_command(message):
    """Check connection status"""
    if str(message.chat.id) != USER_ID:
        return
    
    try:
        # Check GitHub connection
        if not GITHUB_TOKEN or GITHUB_TOKEN == 'ghp_yourtokenhere':
            status_msg = "❌ <b>GitHub Token:</b> Not configured\n"
        else:
            test_data = load_from_github()
            if test_data is not None:
                status_msg = f"✅ <b>GitHub:</b> Connected\n📊 <b>Tasks:</b> {len(test_data.get('tasks', []))}\n"
            else:
                status_msg = "⚠️ <b>GitHub:</b> Connection failed\n"
        
        # Check local data
        data = load_data()
        status_msg += f"💾 <b>Local tasks:</b> {len(data.get('tasks', []))}\n"
        status_msg += f"🕐 <b>Last ID:</b> {data.get('last_id', 0)}\n"
        status_msg += f"⏰ <b>Time:</b> {get_ist_time().strftime('%I:%M %p')} IST"
        
        bot.reply_to(message, status_msg, parse_mode='HTML')
        
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Status error:</b> {str(e)}", parse_mode='HTML')

@bot.message_handler(commands=['clear'])
def clear_command(message):
    """Clear all data"""
    if str(message.chat.id) != USER_ID:
        return
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Yes, delete all", callback_data='confirm_clear'),
        InlineKeyboardButton("❌ Cancel", callback_data='cancel_clear')
    )
    
    bot.reply_to(message, "⚠️ <b>Delete ALL data?</b>\n\nThis will remove all tasks from GitHub and local storage.", 
                 parse_mode='HTML', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Handle callback queries"""
    chat_id = call.message.chat.id
    
    if str(chat_id) != USER_ID:
        return
    
    try:
        if call.data == 'add_task':
            bot.send_message(chat_id, "📝 <b>Send your task message:</b>", parse_mode='HTML')
        
        elif call.data == 'view_tasks':
            show_tasks(call.message)
        
        elif call.data == 'download_json':
            download_command(call.message)
        
        elif call.data == 'status':
            status_command(call.message)
        
        elif call.data == 'confirm_clear':
            empty_data = {
                "tasks": [],
                "messages": [],
                "notes": [],
                "last_id": 0
            }
            success = save_data(empty_data)
            
            if success:
                bot.edit_message_text("🗑️ <b>All data cleared!</b>\n\nGitHub and local storage emptied.", 
                                     chat_id, call.message.message_id, parse_mode='HTML')
            else:
                bot.edit_message_text("⚠️ <b>Partial clear</b>\n\nLocal data cleared, GitHub may have failed.", 
                                     chat_id, call.message.message_id, parse_mode='HTML')
        
        elif call.data == 'cancel_clear':
            bot.edit_message_text("✅ <b>Cancelled</b>\n\nNo data was deleted.", 
                                 chat_id, call.message.message_id, parse_mode='HTML')
    
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {str(e)}")
    
    bot.answer_callback_query(call.id)

# ============= FLASK WEB APP =============
@app.route('/')
def index():
    """Web interface"""
    try:
        data = load_data()
        now = get_ist_time()
        
        # Check GitHub status
        github_status = "❌ Not configured"
        if GITHUB_TOKEN and GITHUB_TOKEN != 'ghp_yourtokenhere':
            test = load_from_github()
            github_status = "✅ Connected" if test is not None else "⚠️ Connection failed"
        else:
            github_status = "❌ Token missing"
        
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Task Tracker</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; font-family: sans-serif; }
                body { background: #f0f2f5; padding: 20px; }
                .container { max-width: 800px; margin: 0 auto; background: white; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; border-radius: 10px 10px 0 0; }
                .header h1 { font-size: 24px; margin-bottom: 10px; }
                .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; padding: 20px; }
                .stat-card { background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }
                .stat-number { font-size: 28px; font-weight: bold; color: #4361ee; }
                .stat-label { color: #666; font-size: 14px; margin-top: 5px; }
                .content { padding: 20px; }
                .task-card { background: #f8f9fa; border-radius: 8px; padding: 15px; margin-bottom: 15px; border-left: 4px solid #4361ee; }
                .task-text { font-size: 16px; margin-bottom: 10px; }
                .task-meta { color: #666; font-size: 14px; display: flex; justify-content: space-between; }
                .btn { display: inline-block; background: #4361ee; color: white; padding: 10px 20px; border-radius: 6px; text-decoration: none; margin: 5px; }
                .btn:hover { background: #3a56d4; }
                .error { background: #fee; color: #c00; padding: 15px; border-radius: 8px; margin: 20px 0; }
                .info { background: #e3f2fd; color: #1565c0; padding: 15px; border-radius: 8px; margin: 20px 0; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📝 Task Tracker</h1>
                    <p>All your tasks in one place • {}</p>
                </div>
                
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-number">{}</div>
                        <div class="stat-label">Total Tasks</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{}</div>
                        <div class="stat-label">GitHub Status</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{}</div>
                        <div class="stat-label">Last Update</div>
                    </div>
                </div>
                
                <div class="content">
                    <div style="margin-bottom: 20px;">
                        <a href="/download" class="btn">📥 Download JSON</a>
                        <a href="https://t.me/valmobot" target="_blank" class="btn">🤖 Telegram Bot</a>
                        <button onclick="location.reload()" class="btn">🔄 Refresh</button>
                    </div>
                    
                    {}
                    
                    <div class="info">
                        <strong>How to use:</strong><br>
                        1. Send any message to Telegram bot<br>
                        2. It auto-saves as a task<br>
                        3. View here or download JSON
                    </div>
                </div>
            </div>
            
            <script>
                // Auto-refresh every 30 seconds
                setTimeout(() => location.reload(), 30000);
            </script>
        </body>
        </html>
        '''
        
        # Prepare tasks HTML
        if not data["tasks"]:
            tasks_html = '''
            <div style="text-align: center; padding: 40px; color: #666;">
                <div style="font-size: 48px; margin-bottom: 20px;">📭</div>
                <h3>No tasks yet</h3>
                <p>Send a message to the Telegram bot to get started</p>
            </div>
            '''
        else:
            tasks_html = '<h3>Recent Tasks:</h3>'
            for task in reversed(data["tasks"][-20:]):  # Last 20
                tasks_html += f'''
                <div class="task-card">
                    <div class="task-text">{task["text"]}</div>
                    <div class="task-meta">
                        <span>📅 {task["date"]}</span>
                        <span>⏰ {task["time"]} IST</span>
                    </div>
                </div>
                '''
        
        # Last update time
        last_update = "Never"
        if data["tasks"]:
            last_task = data["tasks"][-1]
            last_update = f"{last_task['time']}"
        
        return html.format(
            now.strftime('%B %d, %Y'),
            len(data["tasks"]),
            github_status,
            last_update,
            tasks_html
        )
        
    except Exception as e:
        error_html = f'''
        <!DOCTYPE html>
        <html>
        <head><title>Error</title><style>body {{ padding: 40px; font-family: sans-serif; }}</style></head>
        <body>
            <h1>⚠️ Server Error</h1>
            <div style="background: #fee; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <strong>Error:</strong> {str(e)}
            </div>
            <p>Please check server logs for details.</p>
            <button onclick="location.reload()">Retry</button>
        </body>
        </html>
        '''
        return error_html

@app.route('/download')
def download():
    """Download JSON directly from GitHub"""
    try:
        # Try to get from GitHub first
        data = load_from_github()
        
        if data is None:
            # Fallback to local
            data = load_data()
        
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        
        return send_file(
            io.BytesIO(json_str.encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name='tasks_data.json'
        )
        
    except Exception as e:
        return f"Error downloading: {str(e)}", 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')})

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
    except Exception as e:
        print(f"Webhook error: {e}")
    return 'Error', 500

# ============= START APPLICATION =============
def start_bot():
    """Start Telegram bot"""
    print("=" * 50)
    print("🤖 Task Tracker Bot")
    print("=" * 50)
    
    # Check GitHub config
    if not GITHUB_TOKEN or GITHUB_TOKEN == 'ghp_yourtokenhere':
        print("❌ WARNING: GitHub token not configured!")
        print("   Set GITHUB_TOKEN environment variable")
        print("   Or edit the GITHUB_TOKEN in the code")
    else:
        print(f"✅ GitHub token configured")
        print(f"📁 Repository: {GITHUB_REPO}")
        
        # Test connection
        print("🔗 Testing GitHub connection...")
        test = load_from_github()
        if test is not None:
            print(f"✅ Connected! Found {len(test.get('tasks', []))} tasks")
        else:
            print("⚠️ Connection failed, will use local storage")
    
    print(f"🌐 Web app: http://0.0.0.0:8000")
    print(f"📱 User ID: {USER_ID}")
    print("=" * 50)
    
    try:
        bot.polling(none_stop=True, interval=1, timeout=30)
    except Exception as e:
        print(f"Bot error: {e}")
        import time
        time.sleep(5)
        start_bot()

if __name__ == '__main__':
    # Create local backup file if it doesn't exist
    if not os.path.exists(LOCAL_DATA_FILE):
        with open(LOCAL_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "tasks": [],
                "messages": [],
                "notes": [],
                "last_id": 0
            }, f, indent=2, ensure_ascii=False)
        print("📁 Created local backup file")
    
    # Start bot in background
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask
    port = int(os.getenv('PORT', 8000))
    print(f"🚀 Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
