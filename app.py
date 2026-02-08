
"""
Simple Task Tracker with GitHub Storage
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

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"

# GitHub Configuration
GITHUB_TOKEN = "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"  # Replace with your GitHub token
GITHUB_REPO = "Qepheyr/gettingfast"  # Replace with your repo name
GITHUB_FILE_PATH = "data.json"  # Path in repo

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')

# Initialize Flask and Telegram bot
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# ============= GITHUB HELPER FUNCTIONS =============
def load_from_github():
    """Load data from GitHub"""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            content = response.json()["content"]
            decoded = base64.b64decode(content).decode('utf-8')
            return json.loads(decoded)
        elif response.status_code == 404:
            # File doesn't exist yet, return default
            return {
                "tasks": [],
                "messages": [],
                "notes": [],
                "last_id": 0
            }
        else:
            print(f"GitHub API Error: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error loading from GitHub: {e}")
        return None

def save_to_github(data):
    """Save data to GitHub"""
    try:
        # First, get the current file to get SHA (for update)
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        get_response = requests.get(url, headers=headers)
        sha = None
        
        if get_response.status_code == 200:
            sha = get_response.json()["sha"]
        
        # Prepare content
        content = json.dumps(data, indent=2, ensure_ascii=False)
        encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        # Create payload
        payload = {
            "message": f"Update tasks data - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": encoded,
            "branch": "main"
        }
        
        if sha:
            payload["sha"] = sha
        
        # Make request
        response = requests.put(url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            print("✅ Successfully saved to GitHub")
            return True
        else:
            print(f"❌ GitHub save error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error saving to GitHub: {e}")
        return False

def get_ist_time():
    """Get current time in IST"""
    return datetime.now(IST)

# ============= FALLBACK LOCAL STORAGE =============
LOCAL_DATA_FILE = 'data_backup.json'

def load_data():
    """Load data - try GitHub first, then local backup"""
    data = load_from_github()
    
    if data is not None:
        # Save local backup
        with open(LOCAL_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return data
    else:
        # Fallback to local file
        if os.path.exists(LOCAL_DATA_FILE):
            with open(LOCAL_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "tasks": [],
            "messages": [],
            "notes": [],
            "last_id": 0
        }

def save_data(data):
    """Save data - try GitHub first, then local backup"""
    success = save_to_github(data)
    
    # Always save local backup
    with open(LOCAL_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return success

# ============= TELEGRAM BOT COMMANDS =============
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Send welcome message"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ <b>Unauthorized Access</b>")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📝 Add Task", callback_data='add_task'),
        InlineKeyboardButton("📋 View Tasks", callback_data='view_tasks'),
        InlineKeyboardButton("📥 Download Data", callback_data='download_data'),
        InlineKeyboardButton("🌐 Open Web", url="https://patient-maxie-sandip232-786edcb8.koyeb.app/"),
        InlineKeyboardButton("🔄 Refresh", callback_data='refresh'),
        InlineKeyboardButton("🗑️ Clear All", callback_data='clear_data')
    )
    
    welcome = """
🤖 <b>GitHub Task Tracker</b>
<i>Data saved to GitHub repository</i>

<u>Commands:</u>
• <code>/add</code> - Add a new task
• <code>/tasks</code> - View your tasks
• <code>/download</code> - Download JSON data
• <code>/clear</code> - Clear all data

<u>How to use:</u>
1. Send any message - it will be saved
2. View data on web interface
3. Download JSON anytime

<u>Storage:</u>
✅ GitHub Repository
📁 Local backup
"""
    bot.send_message(message.chat.id, welcome, parse_mode='HTML', reply_markup=keyboard)

@bot.message_handler(commands=['add'])
def add_task_command(message):
    """Add task command"""
    if str(message.chat.id) != USER_ID:
        return
    
    bot.reply_to(message, "📝 <b>Send me your task:</b>\n\nJust type and send your message. I'll save it to GitHub.", parse_mode='HTML')

@bot.message_handler(func=lambda message: True)
def save_message(message):
    """Save any message as task"""
    if str(message.chat.id) != USER_ID:
        return
    
    # Load existing data
    data = load_data()
    
    # Create new task
    new_task = {
        "id": data["last_id"] + 1,
        "text": message.text,
        "timestamp": get_ist_time().strftime('%Y-%m-%d %H:%M:%S'),
        "date": get_ist_time().strftime('%B %d, %Y'),
        "time": get_ist_time().strftime('%I:%M %p'),
        "type": "task",
        "source": "telegram"
    }
    
    # Add to tasks
    data["tasks"].append(new_task)
    data["last_id"] += 1
    
    # Save data
    success = save_data(data)
    
    # Send confirmation
    if success:
        reply = f"✅ <b>Task Saved to GitHub!</b>\n\n{message.text}\n\n📅 {new_task['date']}\n⏰ {new_task['time']} IST\n\n<i>Synced to repository</i>"
    else:
        reply = f"⚠️ <b>Saved Locally (GitHub Error)</b>\n\n{message.text}\n\n📅 {new_task['date']}\n⏰ {new_task['time']} IST\n\n<i>Saved to local backup only</i>"
    
    bot.reply_to(message, reply, parse_mode='HTML')

@bot.message_handler(commands=['tasks'])
def show_tasks(message):
    """Show all tasks"""
    if str(message.chat.id) != USER_ID:
        return
    
    data = load_data()
    
    if not data["tasks"]:
        bot.reply_to(message, "📭 <b>No tasks yet!</b>\n\nSend me a message to add your first task.", parse_mode='HTML')
        return
    
    response = "📋 <b>Your Tasks:</b>\n\n"
    
    for task in data["tasks"][-10:]:  # Show last 10 tasks
        response += f"🔹 {task['text']}\n"
        response += f"   📅 {task['date']} | ⏰ {task['time']}\n\n"
    
    if len(data["tasks"]) > 10:
        response += f"\n<i>Showing last 10 of {len(data['tasks'])} total tasks</i>"
    
    bot.reply_to(message, response, parse_mode='HTML')

@bot.message_handler(commands=['download'])
def download_data_command(message):
    """Send JSON file"""
    if str(message.chat.id) != USER_ID:
        return
    
    data = load_data()
    
    # Create JSON file in memory
    import io
    json_data = json.dumps(data, indent=2, ensure_ascii=False)
    
    # Send as document
    bot.send_document(
        message.chat.id,
        io.BytesIO(json_data.encode('utf-8')),
        visible_file_name='tasks_data.json',
        caption="📁 <b>Your Data Export</b>\n\nAll tasks in JSON format.",
        parse_mode='HTML'
    )

@bot.message_handler(commands=['clear'])
def clear_data_command(message):
    """Clear all data"""
    if str(message.chat.id) != USER_ID:
        return
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Yes, clear all", callback_data='confirm_clear'),
        InlineKeyboardButton("❌ Cancel", callback_data='cancel_clear')
    )
    
    bot.reply_to(message, "⚠️ <b>Warning!</b>\n\nThis will delete ALL data from GitHub repository.\nAre you sure?", parse_mode='HTML', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Handle callback queries"""
    chat_id = call.message.chat.id
    
    if str(chat_id) != USER_ID:
        return
    
    if call.data == 'add_task':
        bot.send_message(chat_id, "📝 <b>Send me your task:</b>\n\nJust type and send your message.", parse_mode='HTML')
    
    elif call.data == 'view_tasks':
        show_tasks(call.message)
    
    elif call.data == 'download_data':
        download_data_command(call.message)
    
    elif call.data == 'refresh':
        data = load_data()
        bot.edit_message_text(
            f"🔄 <b>Refreshed!</b>\n\nTotal tasks: {len(data['tasks'])}\nLast task: {data['tasks'][-1]['text'][:50] if data['tasks'] else 'None'}",
            chat_id,
            call.message.message_id,
            parse_mode='HTML'
        )
    
    elif call.data == 'clear_data':
        clear_data_command(call.message)
    
    elif call.data == 'confirm_clear':
        # Clear data
        empty_data = {
            "tasks": [],
            "messages": [],
            "notes": [],
            "last_id": 0
        }
        success = save_data(empty_data)
        
        if success:
            bot.edit_message_text("🗑️ <b>All data cleared from GitHub!</b>", chat_id, call.message.message_id, parse_mode='HTML')
        else:
            bot.edit_message_text("⚠️ <b>Failed to clear from GitHub</b>\n\nLocal data cleared only.", chat_id, call.message.message_id, parse_mode='HTML')
    
    elif call.data == 'cancel_clear':
        bot.edit_message_text("✅ <b>Cancelled</b>\n\nYour data is safe.", chat_id, call.message.message_id, parse_mode='HTML')
    
    bot.answer_callback_query(call.id)

# ============= FLASK WEB APP =============
@app.route('/')
def index():
    """Web interface to view data"""
    data = load_data()
    now = get_ist_time()
    
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>GitHub Task Tracker</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }
            
            body {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            
            .container {
                max-width: 800px;
                margin: 0 auto;
                background: white;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                overflow: hidden;
            }
            
            .header {
                background: linear-gradient(135deg, #24292e 0%, #0366d6 100%);
                color: white;
                padding: 25px;
                text-align: center;
            }
            
            .header h1 {
                font-size: 2.2rem;
                margin-bottom: 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
            }
            
            .header p {
                opacity: 0.9;
                font-size: 1rem;
            }
            
            .github-badge {
                display: inline-block;
                background: rgba(255,255,255,0.1);
                padding: 5px 10px;
                border-radius: 20px;
                font-size: 0.8rem;
                margin-top: 5px;
            }
            
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 15px;
                padding: 20px;
                background: #f8f9fa;
            }
            
            .stat-card {
                background: white;
                padding: 20px;
                border-radius: 10px;
                text-align: center;
                box-shadow: 0 3px 10px rgba(0,0,0,0.1);
            }
            
            .stat-number {
                font-size: 2rem;
                font-weight: bold;
                color: #0366d6;
                margin-bottom: 5px;
            }
            
            .stat-label {
                color: #666;
                font-size: 0.9rem;
            }
            
            .content {
                padding: 30px;
            }
            
            .section {
                margin-bottom: 30px;
            }
            
            .section-title {
                font-size: 1.3rem;
                color: #333;
                margin-bottom: 15px;
                padding-bottom: 10px;
                border-bottom: 2px solid #0366d6;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .section-title i {
                color: #0366d6;
            }
            
            .task-list {
                display: flex;
                flex-direction: column;
                gap: 15px;
            }
            
            .task-card {
                background: #f8f9fa;
                border-radius: 10px;
                padding: 20px;
                border-left: 4px solid #0366d6;
                transition: transform 0.3s, box-shadow 0.3s;
            }
            
            .task-card:hover {
                transform: translateY(-3px);
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }
            
            .task-text {
                font-size: 1.1rem;
                color: #333;
                margin-bottom: 10px;
                line-height: 1.4;
            }
            
            .task-meta {
                display: flex;
                justify-content: space-between;
                font-size: 0.85rem;
                color: #666;
            }
            
            .empty-state {
                text-align: center;
                padding: 40px 20px;
                color: #666;
            }
            
            .empty-state i {
                font-size: 3rem;
                margin-bottom: 15px;
                opacity: 0.3;
            }
            
            .empty-state p {
                font-size: 1.1rem;
                margin-bottom: 20px;
            }
            
            .btn {
                display: inline-block;
                background: #0366d6;
                color: white;
                padding: 12px 25px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 600;
                transition: background 0.3s;
                border: none;
                cursor: pointer;
                font-size: 1rem;
            }
            
            .btn:hover {
                background: #005cc5;
            }
            
            .btn-download {
                background: #28a745;
            }
            
            .btn-download:hover {
                background: #218838;
            }
            
            .btn-clear {
                background: #dc3545;
            }
            
            .btn-clear:hover {
                background: #c82333;
            }
            
            .btn-telegram {
                background: #0088cc;
            }
            
            .btn-telegram:hover {
                background: #0077b5;
            }
            
            .actions {
                display: flex;
                gap: 15px;
                margin-top: 20px;
                flex-wrap: wrap;
            }
            
            .info-box {
                background: #e9ecef;
                padding: 15px;
                border-radius: 10px;
                margin-top: 20px;
                border-left: 4px solid #28a745;
            }
            
            .info-box.warning {
                border-left-color: #ffc107;
                background: #fff3cd;
            }
            
            .info-box.error {
                border-left-color: #dc3545;
                background: #f8d7da;
            }
            
            @media (max-width: 768px) {
                .container {
                    border-radius: 10px;
                }
                
                .header {
                    padding: 20px;
                }
                
                .header h1 {
                    font-size: 1.8rem;
                }
                
                .content {
                    padding: 20px;
                }
                
                .stats {
                    grid-template-columns: 1fr;
                }
                
                .actions {
                    flex-direction: column;
                }
                
                .btn {
                    width: 100%;
                    text-align: center;
                }
            }
        </style>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1><i class="fab fa-github"></i> GitHub Task Tracker</h1>
                <p>Data stored in GitHub repository • {}</p>
                <div class="github-badge">
                    <i class="fas fa-database"></i> Synced to GitHub
                </div>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number">{}</div>
                    <div class="stat-label">Total Tasks</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{}</div>
                    <div class="stat-label">Last Update</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{}</div>
                    <div class="stat-label">Storage</div>
                </div>
            </div>
            
            <div class="content">
                <div class="section">
                    <h2 class="section-title"><i class="fas fa-tasks"></i> Your Tasks (Newest First)</h2>
                    
                    {}
                </div>
                
                <div class="actions">
                    <a href="/download" class="btn btn-download">
                        <i class="fas fa-download"></i> Download JSON
                    </a>
                    <button onclick="clearData()" class="btn btn-clear">
                        <i class="fas fa-trash"></i> Clear All Data
                    </button>
                    <a href="https://t.me/tasktracker_simple_bot" target="_blank" class="btn btn-telegram">
                        <i class="fab fa-telegram"></i> Open Telegram
                    </a>
                    <button onclick="refreshData()" class="btn">
                        <i class="fas fa-sync"></i> Refresh
                    </button>
                </div>
                
                <div class="info-box">
                    <p><i class="fas fa-info-circle"></i> <strong>How to use:</strong></p>
                    <p>1. Send any message to Telegram bot - it auto-saves to GitHub</p>
                    <p>2. View data here or download JSON</p>
                    <p>3. Data is synced to GitHub repository</p>
                </div>
                
                {}
            </div>
        </div>
        
        <script>
            function clearData() {
                if (confirm('⚠️ Delete ALL data from GitHub? This cannot be undone!')) {
                    fetch('/clear', { method: 'POST' })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                alert('✅ All data cleared from GitHub!');
                                location.reload();
                            } else {
                                alert('❌ Error: ' + data.error);
                            }
                        })
                        .catch(error => {
                            alert('❌ Error: ' + error);
                        });
                }
            }
            
            function refreshData() {
                location.reload();
            }
            
            // Auto-refresh every 30 seconds
            setTimeout(() => {
                location.reload();
            }, 30000);
        </script>
    </body>
    </html>
    '''
    
    # Prepare tasks HTML
    if not data["tasks"]:
        tasks_html = '''
        <div class="empty-state">
            <i class="fas fa-inbox"></i>
            <p>No tasks yet! Send a message to the Telegram bot to get started.</p>
            <a href="https://t.me/tasktracker_simple_bot" target="_blank" class="btn btn-telegram">
                <i class="fab fa-telegram"></i> Open Telegram Bot
            </a>
        </div>
        '''
    else:
        tasks_html = '<div class="task-list">'
        for task in reversed(data["tasks"]):  # Show newest first
            tasks_html += f'''
            <div class="task-card">
                <div class="task-text">{task["text"]}</div>
                <div class="task-meta">
                    <span><i class="far fa-calendar"></i> {task["date"]}</span>
                    <span><i class="far fa-clock"></i> {task["time"]} IST</span>
                    <span><i class="fab fa-github"></i> GitHub</span>
                </div>
            </div>
            '''
        tasks_html += '</div>'
    
    # Calculate data size
    data_size = len(json.dumps(data).encode('utf-8'))
    size_str = f"{data_size/1024:.1f} KB" if data_size > 1024 else f"{data_size} bytes"
    
    # Get last update time
    last_update = "Never"
    if data["tasks"]:
        last_task = data["tasks"][-1]
        last_update = f"{last_task['time']}"
    
    # Check GitHub connection
    github_status = ''
    try:
        test = load_from_github()
        if test is not None:
            github_status = '<div class="info-box"><i class="fas fa-check-circle"></i> <strong>GitHub Status:</strong> Connected and syncing</div>'
        else:
            github_status = '<div class="info-box warning"><i class="fas fa-exclamation-triangle"></i> <strong>GitHub Status:</strong> Using local backup only</div>'
    except:
        github_status = '<div class="info-box error"><i class="fas fa-times-circle"></i> <strong>GitHub Status:</strong> Connection error</div>'
    
    return html.format(
        now.strftime('%B %d, %Y %I:%M %p'),
        len(data["tasks"]),
        last_update,
        "GitHub + Local",
        tasks_html,
        github_status
    )

@app.route('/download')
def download_json():
    """Download JSON file"""
    data = load_data()
    json_data = json.dumps(data, indent=2, ensure_ascii=False)
    
    from flask import Response
    return Response(
        json_data,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=tasks_data.json"}
    )

@app.route('/clear', methods=['POST'])
def clear_json():
    """Clear all data"""
    empty_data = {
        "tasks": [],
        "messages": [],
        "notes": [],
        "last_id": 0
    }
    success = save_data(empty_data)
    
    if success:
        return jsonify({"success": True, "message": "Data cleared from GitHub"})
    else:
        return jsonify({"success": False, "error": "Failed to clear from GitHub"})

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
def start_bot():
    """Start Telegram bot in background"""
    print("=" * 60)
    print("🤖 GitHub Task Tracker")
    print("=" * 60)
    print("🌐 Web app: http://localhost:8000")
    print("📱 Telegram: Send any message to save to GitHub")
    print("💾 Storage: GitHub repository + local backup")
    print("=" * 60)
    
    # Test GitHub connection
    print("🔗 Testing GitHub connection...")
    if GITHUB_TOKEN == "YOUR_GITHUB_TOKEN_HERE":
        print("❌ Please set your GitHub token in the code!")
    else:
        test_data = load_from_github()
        if test_data is not None:
            print("✅ GitHub connection successful!")
        else:
            print("⚠️ GitHub connection failed, using local backup only")
    
    try:
        bot.polling(none_stop=True, interval=1, timeout=30)
    except Exception as e:
        print(f"❌ Bot error: {e}")
        import time
        time.sleep(5)
        start_bot()

if __name__ == '__main__':
    # Create initial local backup if it doesn't exist
    if not os.path.exists(LOCAL_DATA_FILE):
        with open(LOCAL_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "tasks": [],
                "messages": [],
                "notes": [],
                "last_id": 0
            }, f, indent=2, ensure_ascii=False)
        print("📁 Created local backup file")
    
    # Start bot in background thread
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask app
    print("🚀 Starting web server on port 8000...")
    app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)
