"""
Simple Task Tracker with JSON Storage
"""

import os
import json
import threading
from datetime import datetime
import pytz
from flask import Flask, request, render_template_string, send_file, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import io

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')

# Initialize Flask and Telegram bot
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# JSON data file
DATA_FILE = 'data.json'

# ============= JSON HELPER FUNCTIONS =============
def load_data():
    """Load data from JSON file"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "tasks": [],
        "messages": [],
        "notes": [],
        "last_id": 0
    }

def save_data(data):
    """Save data to JSON file"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_ist_time():
    """Get current time in IST"""
    return datetime.now(IST)

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
        InlineKeyboardButton("🌐 Open Web App", url="https://patient-maxie-sandip232-786edcb8.koyeb.app/")
    )
    
    welcome = """
🤖 <b>Simple Task Tracker</b>

<i>Commands:</i>
• <code>/add</code> - Add a new task
• <code>/tasks</code> - View your tasks
• <code>/download</code> - Download data as JSON
• <code>/clear</code> - Clear all data

<i>How it works:</i>
1. Send any message - it will be saved as a task
2. Use web app to view all data
3. Download JSON file anytime

<b>Note:</b> All data is stored locally in JSON file.
"""
    bot.send_message(message.chat.id, welcome, parse_mode='HTML', reply_markup=keyboard)

@bot.message_handler(commands=['add'])
def add_task_command(message):
    """Add task command"""
    if str(message.chat.id) != USER_ID:
        return
    
    bot.reply_to(message, "📝 <b>Send me your task message:</b>\n\n<i>Just type your task and send it. I'll save it automatically.</i>", parse_mode='HTML')

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
        "type": "task"
    }
    
    # Add to tasks
    data["tasks"].append(new_task)
    data["last_id"] += 1
    
    # Save data
    save_data(data)
    
    # Send confirmation
    bot.reply_to(message, f"✅ <b>Task Saved!</b>\n\n{message.text}\n\n📅 {new_task['date']}\n⏰ {new_task['time']} IST", parse_mode='HTML')

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
def download_data(message):
    """Send JSON file"""
    if str(message.chat.id) != USER_ID:
        return
    
    if not os.path.exists(DATA_FILE):
        bot.reply_to(message, "❌ <b>No data found!</b>\n\nSend some messages first to create data.", parse_mode='HTML')
        return
    
    try:
        # Send the file
        with open(DATA_FILE, 'rb') as f:
            bot.send_document(message.chat.id, f, caption="📁 <b>Your Data Export</b>\n\nAll your saved tasks in JSON format.", parse_mode='HTML')
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Error:</b> {str(e)}", parse_mode='HTML')

@bot.message_handler(commands=['clear'])
def clear_data(message):
    """Clear all data"""
    if str(message.chat.id) != USER_ID:
        return
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Yes, clear all", callback_data='confirm_clear'),
        InlineKeyboardButton("❌ Cancel", callback_data='cancel_clear')
    )
    
    bot.reply_to(message, "⚠️ <b>Warning!</b>\n\nThis will delete ALL your data permanently.\nAre you sure?", parse_mode='HTML', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Handle callback queries"""
    chat_id = call.message.chat.id
    
    if str(chat_id) != USER_ID:
        return
    
    if call.data == 'add_task':
        bot.send_message(chat_id, "📝 <b>Send me your task:</b>\n\nJust type and send your task message.", parse_mode='HTML')
    
    elif call.data == 'view_tasks':
        show_tasks(call.message)
    
    elif call.data == 'download_data':
        download_data(call.message)
    
    elif call.data == 'confirm_clear':
        # Clear data
        save_data({
            "tasks": [],
            "messages": [],
            "notes": [],
            "last_id": 0
        })
        bot.edit_message_text("🗑️ <b>All data cleared!</b>", chat_id, call.message.message_id, parse_mode='HTML')
    
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
        <title>Simple Task Tracker</title>
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
                background: linear-gradient(135deg, #4361ee 0%, #3a0ca3 100%);
                color: white;
                padding: 25px;
                text-align: center;
            }
            
            .header h1 {
                font-size: 2.2rem;
                margin-bottom: 10px;
            }
            
            .header p {
                opacity: 0.9;
                font-size: 1rem;
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
                color: #4361ee;
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
                border-bottom: 2px solid #4361ee;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            
            .section-title i {
                color: #4361ee;
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
                border-left: 4px solid #4361ee;
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
                background: #4361ee;
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
                background: #3a56d4;
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
            
            .actions {
                display: flex;
                gap: 15px;
                margin-top: 20px;
                flex-wrap: wrap;
            }
            
            .telegram-info {
                background: #0088cc;
                color: white;
                padding: 15px;
                border-radius: 10px;
                margin-top: 20px;
            }
            
            .telegram-info a {
                color: white;
                text-decoration: underline;
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
                <h1><i class="fas fa-tasks"></i> Simple Task Tracker</h1>
                <p>All your tasks in one place • {}</p>
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
                    <div class="stat-label">Data Size</div>
                </div>
            </div>
            
            <div class="content">
                <div class="section">
                    <h2 class="section-title"><i class="fas fa-clipboard-list"></i> Your Tasks</h2>
                    
                    {}
                </div>
                
                <div class="actions">
                    <a href="/download" class="btn btn-download">
                        <i class="fas fa-download"></i> Download JSON
                    </a>
                    <button onclick="clearData()" class="btn btn-clear">
                        <i class="fas fa-trash"></i> Clear All Data
                    </button>
                    <a href="https://t.me/tasktracker_simple_bot" target="_blank" class="btn">
                        <i class="fab fa-telegram"></i> Open Telegram Bot
                    </a>
                </div>
                
                <div class="telegram-info">
                    <p><i class="fas fa-info-circle"></i> <strong>How to use:</strong></p>
                    <p>1. Open Telegram and send any message to the bot</p>
                    <p>2. It will automatically save as a task</p>
                    <p>3. Use <code>/download</code> in Telegram to get JSON file</p>
                </div>
            </div>
        </div>
        
        <script>
            function clearData() {
                if (confirm('⚠️ Are you sure? This will delete ALL data permanently!')) {
                    fetch('/clear', { method: 'POST' })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                alert('✅ All data cleared!');
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
            <a href="https://t.me/tasktracker_simple_bot" target="_blank" class="btn">
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
                </div>
            </div>
            '''
        tasks_html += '</div>'
    
    # Calculate data size
    import sys
    data_size = len(json.dumps(data).encode('utf-8'))
    size_str = f"{data_size/1024:.1f} KB" if data_size > 1024 else f"{data_size} bytes"
    
    # Get last update time
    last_update = "Never"
    if data["tasks"]:
        last_task = data["tasks"][-1]
        last_update = f"{last_task['date']} {last_task['time']}"
    
    return html.format(
        now.strftime('%B %d, %Y %I:%M %p'),
        len(data["tasks"]),
        last_update,
        size_str,
        tasks_html
    )

@app.route('/download')
def download_json():
    """Download JSON file"""
    if not os.path.exists(DATA_FILE):
        return "No data found", 404
    
    return send_file(
        DATA_FILE,
        as_attachment=True,
        download_name='task_tracker_data.json',
        mimetype='application/json'
    )

@app.route('/clear', methods=['POST'])
def clear_json():
    """Clear all data"""
    save_data({
        "tasks": [],
        "messages": [],
        "notes": [],
        "last_id": 0
    })
    return jsonify({"success": True})

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
    print("🤖 Starting Telegram bot...")
    print("🌐 Web app: http://localhost:8000")
    print("📱 Telegram: Send any message to save as task")
    print("💾 Data file: data.json")
    
    try:
        bot.polling(none_stop=True, interval=1, timeout=30)
    except Exception as e:
        print(f"❌ Bot error: {e}")
        import time
        time.sleep(5)
        start_bot()

if __name__ == '__main__':
    # Create initial data file if it doesn't exist
    if not os.path.exists(DATA_FILE):
        save_data({
            "tasks": [],
            "messages": [],
            "notes": [],
            "last_id": 0
        })
        print("📁 Created new data.json file")
    
    # Start bot in background thread
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)
