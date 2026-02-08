"""
Scheduler for Koyeb - Runs as background worker
"""

import os
import telebot
import time
import schedule
from datetime import datetime
import sqlite3

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I')
USER_ID = os.getenv('USER_ID', '8469993808')
PLATFORM = os.getenv('PLATFORM', 'Koyeb Scheduler')

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

def init_db():
    """Initialize database connection"""
    conn = sqlite3.connect('/tmp/bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS scheduled_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp DATETIME,
                  status TEXT,
                  message TEXT)''')
    conn.commit()
    conn.close()

def log_schedule(status, message=""):
    """Log scheduler activity"""
    conn = sqlite3.connect('/tmp/bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO scheduled_logs (timestamp, status, message) VALUES (?, ?, ?)",
              (datetime.now(), status, message))
    conn.commit()
    conn.close()

def send_hello():
    """Send scheduled message"""
    try:
        current_time = datetime.now().strftime('%H:%M:%S')
        message = f"""
🔔 *Scheduled Message from Koyeb*

*Time:* {current_time}
*Platform:* {PLATFORM}
*Status:* ✅ Automated message

This is your scheduled message sent every minute.
Keep up the great work! 🚀
"""
        bot.send_message(USER_ID, message, parse_mode='Markdown')
        
        # Log success
        log_schedule("success", f"Message sent at {current_time}")
        
        print(f"✅ Scheduled message sent at {current_time}")
        return True
        
    except Exception as e:
        error_msg = f"Error sending message: {str(e)}"
        print(f"❌ {error_msg}")
        log_schedule("error", error_msg)
        return False

def update_stats():
    """Update statistics in main database"""
    try:
        conn = sqlite3.connect('/tmp/bot_data.db')
        c = conn.cursor()
        
        # Get current count
        c.execute("SELECT value FROM stats WHERE key='scheduled_messages'")
        result = c.fetchone()
        
        if result:
            current_count = int(result[0]) + 1
            c.execute("UPDATE stats SET value=? WHERE key='scheduled_messages'", (str(current_count),))
        else:
            c.execute("INSERT INTO stats (key, value) VALUES ('scheduled_messages', '1')")
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"⚠️ Could not update stats: {e}")

def enhanced_scheduled_message():
    """Enhanced scheduled message with stats update"""
    if send_hello():
        update_stats()

def run_scheduler():
    """Main scheduler loop"""
    print("=" * 50)
    print("⏰ Koyeb Scheduler Started")
    print(f"Platform: {PLATFORM}")
    print(f"User ID: {USER_ID}")
    print("Schedule: Every minute")
    print("=" * 50)
    
    # Initialize database
    init_db()
    
    # Send startup message
    try:
        startup_msg = f"""
🔧 *Scheduler Started on Koyeb*

*Platform:* {PLATFORM}
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
*Schedule:* Every minute
*Status:* ✅ Running
"""
        bot.send_message(USER_ID, startup_msg, parse_mode='Markdown')
        log_schedule("startup", "Scheduler started successfully")
    except Exception as e:
        print(f"⚠️ Could not send startup message: {e}")
    
    # Schedule the task
    schedule.every(1).minutes.do(enhanced_scheduled_message)
    
    # Run immediately once
    enhanced_scheduled_message()
    
    # Main loop
    print("🔄 Scheduler running... (Ctrl+C to stop)")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    run_scheduler()
