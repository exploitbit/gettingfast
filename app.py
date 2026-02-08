"""
Simple Task Tracker - GitHub Storage
Works on Koyeb without gunicorn issues
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

# GitHub Configuration - SET THESE IN KOYEB ENVIRONMENT VARIABLES
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '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')
GITHUB_REPO = os.getenv('GITHUB_REPO', 'Qepheyr/gettingfast')
GITHUB_FILE_PATH = "data.json"

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')

# Initialize Flask and Telegram bot
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# ============= SIMPLE GITHUB FUNCTIONS =============
def get_github_data():
    """Get data from GitHub"""
    try:
        if not GITHUB_TOKEN or GITHUB_TOKEN == 'ghp_yourtokenhere':
            print("GitHub token not set")
            return None
            
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
            # File doesn't exist yet
            return {
                "tasks": [],
                "last_id": 0,
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        else:
            print(f"GitHub error: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Error getting GitHub data: {e}")
        return None

def save_to_github(data):
    """Save data to GitHub"""
    try:
        if not GITHUB_TOKEN or GITHUB_TOKEN == 'ghp_yourtokenhere':
            print("GitHub token not set")
            return False
            
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # First, check if file exists to get SHA
        sha = None
        check_response = requests.get(url, headers=headers)
        if check_response.status_code == 200:
            sha = check_response.json()["sha"]
        
        # Prepare content
        content = json.dumps(data, indent=2, ensure_ascii=False)
        encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        # Create payload
        payload = {
            "message": f"Update tasks - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "content": encoded,
            "branch": "main"
        }
        
        if sha:
            payload["sha"] = sha
        
        # Save to GitHub
        response = requests.put(url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            print("Saved to GitHub successfully")
            return True
        else:
            print(f"Failed to save to GitHub: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Error saving to GitHub: {e}")
        return False

def get_ist_time():
    """Get current time in IST"""
    return datetime.now(IST)

# ============= TELEGRAM BOT =============
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Welcome message"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized")
        return
    
    welcome_text = f"""
🤖 <b>Task Tracker Bot</b>

<i>Commands:</i>
• Just send a message - it will be saved
• /tasks - View your tasks
• /download - Get JSON file
• /clear - Delete all data

<b>Web Interface:</b>
https://handsome-rafaela-sandip232-7f9d347c.koyeb.app/

<b>Current Time:</b>
{get_ist_time().strftime('%I:%M %p')} IST

<b>Storage:</b>
✅ GitHub Repository
"""
    bot.send_message(message.chat.id, welcome_text, parse_mode='HTML')

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Save any message as task"""
    if str(message.chat.id) != USER_ID:
        return
    
    # Get current data
    data = get_github_data()
    if data is None:
        data = {"tasks": [], "last_id": 0}
    
    # Create new task
    new_task = {
        "id": data.get("last_id", 0) + 1,
        "text": message.text,
        "date": get_ist_time().strftime('%Y-%m-%d'),
        "time": get_ist_time().strftime('%I:%M %p'),
        "timestamp": get_ist_time().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    if "tasks" not in data:
        data["tasks"] = []
    
    data["tasks"].append(new_task)
    data["last_id"] = data.get("last_id", 0) + 1
    data["updated_at"] = get_ist_time().strftime('%Y-%m-%d %H:%M:%S')
    
    # Save to GitHub
    success = save_to_github(data)
    
    if success:
        reply = f"✅ <b>Saved to GitHub!</b>\n\n{message.text}\n\n📅 {new_task['date']}\n⏰ {new_task['time']} IST"
    else:
        reply = f"❌ <b>Save failed!</b>\n\nCould not save to GitHub. Check token and repository."
    
    bot.reply_to(message, reply, parse_mode='HTML')

@bot.message_handler(commands=['tasks'])
def show_tasks(message):
    """Show all tasks"""
    if str(message.chat.id) != USER_ID:
        return
    
    data = get_github_data()
    
    if not data or "tasks" not in data or not data["tasks"]:
        bot.reply_to(message, "📭 <b>No tasks found!</b>\n\nSend a message to add your first task.", parse_mode='HTML')
        return
    
    response = f"📋 <b>Your Tasks ({len(data['tasks'])} total):</b>\n\n"
    
    for task in data["tasks"][-10:]:
        response += f"• {task['text']}\n"
        response += f"  ⏰ {task['time']} | 📅 {task['date']}\n\n"
    
    bot.reply_to(message, response, parse_mode='HTML')

@bot.message_handler(commands=['download'])
def download_data(message):
    """Download JSON file"""
    if str(message.chat.id) != USER_ID:
        return
    
    data = get_github_data()
    
    if not data:
        bot.reply_to(message, "❌ <b>No data found!</b>", parse_mode='HTML')
        return
    
    # Create JSON file
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    
    # Send as file
    bot.send_document(
        chat_id=message.chat.id,
        document=io.BytesIO(json_str.encode('utf-8')),
        visible_file_name='tasks_data.json',
        caption="📁 <b>Tasks Data Export</b>\n\nJSON file from GitHub repository"
    )

@bot.message_handler(commands=['clear'])
def clear_data(message):
    """Clear all data"""
    if str(message.chat.id) != USER_ID:
        return
    
    # Create empty data
    empty_data = {
        "tasks": [],
        "last_id": 0,
        "cleared_at": get_ist_time().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Save to GitHub
    success = save_to_github(empty_data)
    
    if success:
        bot.reply_to(message, "🗑️ <b>All data cleared from GitHub!</b>", parse_mode='HTML')
    else:
        bot.reply_to(message, "❌ <b>Failed to clear data!</b>", parse_mode='HTML')

# ============= FLASK WEB APP =============
@app.route('/')
def home():
    """Main web page showing data.json content"""
    try:
        # Get data from GitHub
        data = get_github_data()
        
        if data is None:
            # Show error if can't get data
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Task Tracker</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; }
                    .error { background: #ffebee; color: #c62828; padding: 20px; border-radius: 8px; }
                </style>
            </head>
            <body>
                <h1>⚠️ Error</h1>
                <div class="error">
                    <h3>Cannot load data from GitHub</h3>
                    <p>Possible issues:</p>
                    <ul>
                        <li>GitHub token not set correctly</li>
                        <li>Repository not found: Qepheyr/gettingfast</li>
                        <li>No data.json file in repository</li>
                    </ul>
                </div>
            </body>
            </html>
            '''
        
        # Create HTML page
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Task Tracker - GitHub Data</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                }
                .container {
                    max-width: 1000px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                    overflow: hidden;
                }
                .header {
                    background: linear-gradient(135deg, #24292e 0%, #0366d6 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }
                .header h1 {
                    margin: 0;
                    font-size: 28px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 10px;
                }
                .stats {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    padding: 25px;
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
                    font-size: 32px;
                    font-weight: bold;
                    color: #0366d6;
                    margin-bottom: 5px;
                }
                .stat-label {
                    color: #666;
                    font-size: 14px;
                }
                .content {
                    padding: 30px;
                }
                .tabs {
                    display: flex;
                    gap: 10px;
                    margin-bottom: 20px;
                    border-bottom: 2px solid #e1e4e8;
                    padding-bottom: 10px;
                }
                .tab-btn {
                    padding: 10px 20px;
                    background: #f6f8fa;
                    border: none;
                    border-radius: 6px;
                    cursor: pointer;
                    font-weight: 500;
                }
                .tab-btn.active {
                    background: #0366d6;
                    color: white;
                }
                .tab-content {
                    display: none;
                }
                .tab-content.active {
                    display: block;
                }
                .task-list {
                    display: flex;
                    flex-direction: column;
                    gap: 15px;
                }
                .task-card {
                    background: #f6f8fa;
                    border-radius: 10px;
                    padding: 20px;
                    border-left: 4px solid #28a745;
                    transition: transform 0.2s;
                }
                .task-card:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                }
                .task-text {
                    font-size: 16px;
                    margin-bottom: 10px;
                    line-height: 1.5;
                }
                .task-meta {
                    display: flex;
                    justify-content: space-between;
                    font-size: 14px;
                    color: #586069;
                }
                .json-viewer {
                    background: #f6f8fa;
                    border-radius: 10px;
                    padding: 20px;
                    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
                    font-size: 14px;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                    max-height: 500px;
                    overflow-y: auto;
                }
                .actions {
                    display: flex;
                    gap: 15px;
                    margin: 25px 0;
                    flex-wrap: wrap;
                }
                .btn {
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    padding: 12px 24px;
                    background: #0366d6;
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 500;
                    transition: background 0.2s;
                }
                .btn:hover {
                    background: #005cc5;
                }
                .btn-telegram {
                    background: #0088cc;
                }
                .btn-telegram:hover {
                    background: #0077b5;
                }
                .btn-download {
                    background: #28a745;
                }
                .btn-download:hover {
                    background: #218838;
                }
                .empty-state {
                    text-align: center;
                    padding: 40px;
                    color: #586069;
                }
                .empty-state-icon {
                    font-size: 48px;
                    margin-bottom: 15px;
                    opacity: 0.5;
                }
                .timestamp {
                    color: #586069;
                    font-size: 14px;
                    margin-top: 10px;
                }
                @media (max-width: 768px) {
                    .container {
                        border-radius: 10px;
                    }
                    .stats {
                        grid-template-columns: 1fr;
                    }
                    .actions {
                        flex-direction: column;
                    }
                    .btn {
                        width: 100%;
                        justify-content: center;
                    }
                }
            </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1><i class="fab fa-github"></i> Task Tracker - GitHub Data</h1>
                    <p>Data stored in: Qepheyr/gettingfast • Updated: {}</p>
                </div>
                
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-number">{}</div>
                        <div class="stat-label">Total Tasks</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{}</div>
                        <div class="stat-label">Last Task ID</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{}</div>
                        <div class="stat-label">Last Updated</div>
                    </div>
                </div>
                
                <div class="content">
                    <div class="tabs">
                        <button class="tab-btn active" onclick="switchTab('tasks')">
                            <i class="fas fa-tasks"></i> Tasks View
                        </button>
                        <button class="tab-btn" onclick="switchTab('json')">
                            <i class="fas fa-code"></i> JSON View
                        </button>
                        <button class="tab-btn" onclick="switchTab('raw')">
                            <i class="fas fa-file-code"></i> Raw JSON
                        </button>
                    </div>
                    
                    <div id="tasks-tab" class="tab-content active">
                        {}
                    </div>
                    
                    <div id="json-tab" class="tab-content">
                        <div class="json-viewer">
                            {}
                        </div>
                    </div>
                    
                    <div id="raw-tab" class="tab-content">
                        <div class="json-viewer">
{}
                        </div>
                    </div>
                    
                    <div class="actions">
                        <a href="/download" class="btn btn-download">
                            <i class="fas fa-download"></i> Download JSON
                        </a>
                        <a href="https://t.me/tasktracker_simple_bot" target="_blank" class="btn btn-telegram">
                            <i class="fab fa-telegram"></i> Telegram Bot
                        </a>
                        <button onclick="refreshPage()" class="btn">
                            <i class="fas fa-sync"></i> Refresh
                        </button>
                    </div>
                </div>
            </div>
            
            <script>
                function switchTab(tabName) {
                    // Hide all tabs
                    document.querySelectorAll('.tab-content').forEach(tab => {
                        tab.classList.remove('active');
                    });
                    document.querySelectorAll('.tab-btn').forEach(btn => {
                        btn.classList.remove('active');
                    });
                    
                    // Show selected tab
                    document.getElementById(tabName + '-tab').classList.add('active');
                    event.target.classList.add('active');
                }
                
                function refreshPage() {
                    location.reload();
                }
                
                // Auto-refresh every 30 seconds
                setTimeout(refreshPage, 30000);
            </script>
        </body>
        </html>
        '''
        
        # Prepare task cards HTML
        tasks = data.get('tasks', [])
        if not tasks:
            tasks_html = '''
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <h3>No tasks yet</h3>
                <p>Send a message to the Telegram bot to add your first task!</p>
            </div>
            '''
        else:
            tasks_html = '<div class="task-list">'
            for task in reversed(tasks):  # Show newest first
                tasks_html += f'''
                <div class="task-card">
                    <div class="task-text">{task.get('text', '')}</div>
                    <div class="task-meta">
                        <span><i class="far fa-calendar"></i> {task.get('date', '')}</span>
                        <span><i class="far fa-clock"></i> {task.get('time', '')} IST</span>
                        <span>ID: {task.get('id', '')}</span>
                    </div>
                </div>
                '''
            tasks_html += '</div>'
        
        # Get formatted JSON
        formatted_json = json.dumps(data, indent=2)
        escaped_json = json.dumps(data).replace('<', '&lt;').replace('>', '&gt;')
        
        # Get timestamps
        updated_at = data.get('updated_at', 'Never')
        created_at = data.get('created_at', 'Unknown')
        
        return html.format(
            updated_at,
            len(tasks),
            data.get('last_id', 0),
            updated_at,
            tasks_html,
            formatted_json,
            escaped_json
        )
        
    except Exception as e:
        error_html = f'''
        <!DOCTYPE html>
        <html>
        <head><title>Error</title><style>body {{ padding: 40px; font-family: sans-serif; }}</style></head>
        <body>
            <h1>⚠️ Error</h1>
            <div style="background: #ffebee; padding: 20px; border-radius: 8px;">
                <p><strong>Error details:</strong> {str(e)}</p>
            </div>
        </body>
        </html>
        '''
        return error_html

@app.route('/download')
def download_json():
    """Download data.json file"""
    data = get_github_data()
    
    if data is None:
        return "No data available", 404
    
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    
    return send_file(
        io.BytesIO(json_str.encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name='data.json'
    )

@app.route('/data.json')
def raw_json():
    """Direct access to data.json"""
    data = get_github_data()
    
    if data is None:
        return jsonify({"error": "No data available"}), 404
    
    return jsonify(data)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "github_repo": GITHUB_REPO,
        "github_connected": get_github_data() is not None
    })

# ============= TELEGRAM WEBHOOK =============
@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook handler"""
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
    except Exception as e:
        print(f"Webhook error: {e}")
    return 'Error', 400

# ============= START APPLICATION =============
def run_bot():
    """Run Telegram bot"""
    print("🤖 Starting Telegram bot...")
    print(f"🌐 Web URL: https://handsome-rafaela-sandip232-7f9d347c.koyeb.app/")
    print(f"📁 GitHub repo: {GITHUB_REPO}")
    
    try:
        bot.polling(none_stop=True, interval=1, timeout=30)
    except Exception as e:
        print(f"Bot error: {e}")
        import time
        time.sleep(5)
        run_bot()

if __name__ == '__main__':
    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask app
    port = int(os.getenv('PORT', 8000))
    print(f"🚀 Starting web server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
