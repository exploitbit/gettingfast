
"""
Task Tracker Telegram Bot with Mini App Integration
Monitors JSON files and sends Telegram notifications
"""

import os
import json
import time
import threading
from datetime import datetime, timedelta
import telebot
from telebot import types
from flask import Flask, request, jsonify

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
USER_ID = "8469993808"
MINI_APP_URL = "https://patient-maxie-sandip232-786edcb8.koyeb.app/index.php"

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
hourly_notifications = True
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

def send_telegram_message(chat_id, text, reply_markup=None):
    """Send message to Telegram"""
    try:
        bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=reply_markup)
        log_telegram_notification(text, True)
        return True
    except Exception as e:
        log_telegram_notification(f"Error: {str(e)}", False)
        return False

def create_main_menu_keyboard():
    """Create main menu inline keyboard"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    buttons = [
        types.InlineKeyboardButton("📱 Open Mini App", web_app=types.WebAppInfo(url=MINI_APP_URL)),
        types.InlineKeyboardButton("📊 Stats", callback_data="stats"),
        types.InlineKeyboardButton("🔔 Hourly Notifications", callback_data="toggle_hourly"),
        types.InlineKeyboardButton("✅ Completed Tasks", callback_data="completed_tasks"),
        types.InlineKeyboardButton("📋 All Tasks", callback_data="all_tasks"),
        types.InlineKeyboardButton("⏳ Remaining Tasks", callback_data="remaining_tasks"),
        types.InlineKeyboardButton("📝 Notes", callback_data="notes"),
        types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh")
    ]
    
    # Add buttons in rows
    keyboard.add(buttons[0])  # Mini App button alone
    keyboard.add(buttons[1], buttons[2])  # Stats and Hourly Notifications
    keyboard.add(buttons[3], buttons[4])  # Completed and All Tasks
    keyboard.add(buttons[5], buttons[6])  # Remaining Tasks and Notes
    keyboard.add(buttons[7])  # Refresh button
    
    return keyboard

def create_back_to_menu_keyboard():
    """Create back to menu keyboard"""
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu"))
    return keyboard

def get_bot_stats():
    """Get bot statistics"""
    tasks = load_json_file(TASKS_FILE)
    notes = load_json_file(NOTES_FILE)
    
    # Calculate task statistics
    total_tasks = len(tasks) if tasks else 0
    completed_tasks = len([t for t in tasks if t.get('completed', False)]) if tasks else 0
    remaining_tasks = total_tasks - completed_tasks
    
    # Calculate note statistics
    total_notes = len(notes) if notes else 0
    notes_with_notifications = len([n for n in notes if n.get('notify_enabled', False)]) if notes else 0
    
    # Calculate task notifications
    tasks_with_notifications = len([t for t in tasks if t.get('notify_enabled', False)]) if tasks else 0
    
    return {
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'remaining_tasks': remaining_tasks,
        'total_notes': total_notes,
        'notes_with_notifications': notes_with_notifications,
        'tasks_with_notifications': tasks_with_notifications,
        'hourly_notifications': hourly_notifications,
        'monitor_active': monitor_active,
        'uptime': str(datetime.now() - app_start_time).split('.')[0]
    }

def format_task_message(task):
    """Format task for display in message"""
    title = task.get('title', 'Untitled Task')
    description = task.get('description', '')
    start_time = task.get('start_time', '')
    end_time = task.get('end_time', '')
    completed = task.get('completed', False)
    notify_enabled = task.get('notify_enabled', False)
    priority = task.get('priority', 15)
    repeat = task.get('repeat', 'none')
    
    # Format time
    time_str = ""
    if start_time:
        try:
            start_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            time_str = start_dt.strftime('%I:%M %p')
        except:
            time_str = start_time
    
    # Format description (shorten if too long)
    if description:
        clean_desc = description.replace('*', '').replace('_', '')
        if len(clean_desc) > 100:
            description = clean_desc[:100] + '...'
    
    # Create message
    message = f"{'✅' if completed else '⏳'} <b>{title}</b>\n"
    
    if time_str:
        message += f"   🕐 {time_str}\n"
    
    if description:
        message += f"   📝 {description}\n"
    
    if repeat != 'none':
        message += f"   🔄 {repeat.capitalize()}\n"
    
    message += f"   ⭐ Priority: {priority}/15\n"
    
    # Add notification status
    if notify_enabled:
        message += "   🔔 Notifications: Enabled\n"
    
    return message

def format_note_message(note):
    """Format note for display in message"""
    title = note.get('title', 'Untitled Note')
    description = note.get('description', '')
    notify_enabled = note.get('notify_enabled', False)
    notify_interval = note.get('notify_interval', 0)
    updated_at = note.get('updatedAt', '')
    
    # Format description (shorten if too long)
    if description:
        clean_desc = description.replace('*', '').replace('_', '')
        if len(clean_desc) > 100:
            description = clean_desc[:100] + '...'
    
    # Create message
    message = f"📝 <b>{title}</b>\n"
    
    if description:
        message += f"   {description}\n"
    
    if notify_enabled and notify_interval > 0:
        message += f"   🔔 Reminders every {notify_interval} hours\n"
    
    if updated_at:
        try:
            updated_dt = datetime.strptime(updated_at, '%Y-%m-%d %H:%M:%S')
            message += f"   📅 Updated: {updated_dt.strftime('%b %d, %Y')}\n"
        except:
            pass
    
    return message

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
                    
                    if send_telegram_message(USER_ID, message):
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
            
            if send_telegram_message(USER_ID, message):
                # Update last_notified time
                note['last_notified'] = current_time.strftime('%Y-%m-%d %H:%M:%S')
                save_json_file(NOTES_FILE, notes)
            
    except Exception as e:
        print(f"Error checking note reminders: {e}")

def send_hourly_report():
    """Send hourly task status report"""
    global hourly_notifications
    
    if not hourly_notifications:
        return
    
    try:
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
            for task in completed_tasks[:3]:  # Show first 3 completed
                task_title = task.get('title', 'Untitled')
                if len(task_title) > 30:
                    task_title = task_title[:27] + '...'
                message += f"   ✓ {task_title}\n"
            if len(completed_tasks) > 3:
                message += f"   ... and {len(completed_tasks) - 3} more\n"
            
            message += f"\n⏳ <b>Pending ({len(pending_tasks)})</b>\n"
            for task in pending_tasks[:3]:  # Show first 3 pending
                task_title = task.get('title', 'Untitled')
                if len(task_title) > 30:
                    task_title = task_title[:27] + '...'
                
                try:
                    start_time = datetime.strptime(task.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
                    time_str = start_time.strftime('%I:%M %p')
                    message += f"   • {task_title} ({time_str})\n"
                except:
                    message += f"   • {task_title}\n"
            
            if len(pending_tasks) > 3:
                message += f"   ... and {len(pending_tasks) - 3} more\n"
        
        send_telegram_message(USER_ID, message)
        
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

# ============= TELEGRAM COMMAND HANDLERS =============
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Send welcome message with inline keyboard"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    # Create welcome message with buttons
    welcome_msg = """
🤖 <b>Welcome to Task Tracker Bot!</b>

I help you manage your tasks and notes with:
• Task reminders (10 minutes before start)
• Note reminders (custom intervals)
• Hourly status reports
• Mini App for full management

<b>Basic Information:</b>
• User ID: 8469993808
• Status: ✅ Active
• Mini App: Available below
"""
    
    # Create keyboard with inline buttons
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    # Basic Info button
    keyboard.add(
        types.InlineKeyboardButton("ℹ️ Basic Info", callback_data="basic_info"),
        types.InlineKeyboardButton("📱 Open Mini App", web_app=types.WebAppInfo(url=MINI_APP_URL)),
        types.InlineKeyboardButton("📋 Main Menu", callback_data="main_menu")
    )
    
    send_telegram_message(message.chat.id, welcome_msg, keyboard)

@bot.message_handler(commands=['menu'])
def show_main_menu(message):
    """Show main menu"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    menu_msg = """
📱 <b>Main Menu</b>

Choose an option below:
"""
    
    keyboard = create_main_menu_keyboard()
    send_telegram_message(message.chat.id, menu_msg, keyboard)

@bot.message_handler(commands=['stats'])
def show_stats(message):
    """Show statistics"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    stats = get_bot_stats()
    
    stats_msg = f"""
📊 <b>Bot Statistics</b>

📋 <b>Tasks:</b>
   • Total: {stats['total_tasks']}
   • Completed: {stats['completed_tasks']}
   • Remaining: {stats['remaining_tasks']}
   • With Notifications: {stats['tasks_with_notifications']}

📝 <b>Notes:</b>
   • Total: {stats['total_notes']}
   • With Notifications: {stats['notes_with_notifications']}

🔔 <b>Notifications:</b>
   • Hourly Reports: {'✅ ON' if stats['hourly_notifications'] else '❌ OFF'}
   • Monitor: {'✅ Active' if stats['monitor_active'] else '❌ Inactive'}

⏰ <b>System:</b>
   • Uptime: {stats['uptime']}
   • Last Check: {datetime.now().strftime('%H:%M:%S')}
"""
    
    keyboard = create_back_to_menu_keyboard()
    send_telegram_message(message.chat.id, stats_msg, keyboard)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """Handle all callback queries"""
    if str(call.message.chat.id) != USER_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized access")
        return
    
    try:
        if call.data == "main_menu":
            menu_msg = """
📱 <b>Main Menu</b>

Choose an option below:
"""
            keyboard = create_main_menu_keyboard()
            bot.edit_message_text(
                menu_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "basic_info":
            info_msg = f"""
ℹ️ <b>Basic Information</b>

• <b>User ID:</b> {USER_ID}
• <b>Bot Status:</b> ✅ Active
• <b>Mini App URL:</b> {MINI_APP_URL}
• <b>Started:</b> {app_start_time.strftime('%Y-%m-%d %H:%M:%S')}
• <b>Uptime:</b> {str(datetime.now() - app_start_time).split('.')[0]}
"""
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                info_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "stats":
            stats = get_bot_stats()
            stats_msg = f"""
📊 <b>Bot Statistics</b>

📋 <b>Tasks:</b>
   • Total: {stats['total_tasks']}
   • Completed: {stats['completed_tasks']}
   • Remaining: {stats['remaining_tasks']}
   • With Notifications: {stats['tasks_with_notifications']}

📝 <b>Notes:</b>
   • Total: {stats['total_notes']}
   • With Notifications: {stats['notes_with_notifications']}

🔔 <b>Notifications:</b>
   • Hourly Reports: {'✅ ON' if stats['hourly_notifications'] else '❌ OFF'}
   • Monitor: {'✅ Active' if stats['monitor_active'] else '❌ Inactive'}

⏰ <b>System:</b>
   • Uptime: {stats['uptime']}
   • Last Check: {datetime.now().strftime('%H:%M:%S')}
"""
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                stats_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "toggle_hourly":
            global hourly_notifications
            hourly_notifications = not hourly_notifications
            
            status_msg = f"""
🔔 <b>Hourly Notifications</b>

Status: {'✅ TURNED ON' if hourly_notifications else '❌ TURNED OFF'}

Hourly task reports will {'now be sent' if hourly_notifications else 'no longer be sent'} every hour.
"""
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                status_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "completed_tasks":
            tasks = load_json_file(TASKS_FILE)
            completed_tasks = [t for t in tasks if t.get('completed', False)] if tasks else []
            
            if not completed_tasks:
                message_text = "✅ <b>Completed Tasks</b>\n\nNo completed tasks found."
            else:
                message_text = f"✅ <b>Completed Tasks</b>\n\nTotal: {len(completed_tasks)} tasks\n\n"
                for i, task in enumerate(completed_tasks[:10], 1):  # Show first 10
                    task_title = task.get('title', 'Untitled Task')
                    if len(task_title) > 40:
                        task_title = task_title[:37] + '...'
                    
                    notify_icon = "🔔" if task.get('notify_enabled', False) else ""
                    message_text += f"{i}. {task_title} {notify_icon}\n"
                
                if len(completed_tasks) > 10:
                    message_text += f"\n... and {len(completed_tasks) - 10} more tasks"
            
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "all_tasks":
            tasks = load_json_file(TASKS_FILE)
            
            if not tasks:
                message_text = "📋 <b>All Tasks</b>\n\nNo tasks found."
            else:
                message_text = f"📋 <b>All Tasks</b>\n\nTotal: {len(tasks)} tasks\n\n"
                for i, task in enumerate(tasks[:10], 1):  # Show first 10
                    task_title = task.get('title', 'Untitled Task')
                    if len(task_title) > 40:
                        task_title = task_title[:37] + '...'
                    
                    completed = task.get('completed', False)
                    notify_icon = "🔔" if task.get('notify_enabled', False) else ""
                    status_icon = "✅" if completed else "⏳"
                    
                    message_text += f"{i}. {status_icon} {task_title} {notify_icon}\n"
                
                if len(tasks) > 10:
                    message_text += f"\n... and {len(tasks) - 10} more tasks"
            
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "remaining_tasks":
            tasks = load_json_file(TASKS_FILE)
            remaining_tasks = [t for t in tasks if not t.get('completed', False)] if tasks else []
            
            if not remaining_tasks:
                message_text = "⏳ <b>Remaining Tasks</b>\n\nNo remaining tasks. Great job!"
            else:
                message_text = f"⏳ <b>Remaining Tasks</b>\n\nTotal: {len(remaining_tasks)} tasks\n\n"
                for i, task in enumerate(remaining_tasks[:10], 1):  # Show first 10
                    task_title = task.get('title', 'Untitled Task')
                    if len(task_title) > 40:
                        task_title = task_title[:37] + '...'
                    
                    notify_icon = "🔔" if task.get('notify_enabled', False) else ""
                    
                    # Try to show time
                    time_str = ""
                    start_time = task.get('start_time', '')
                    if start_time:
                        try:
                            start_dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
                            time_str = start_dt.strftime('%I:%M %p')
                        except:
                            pass
                    
                    if time_str:
                        message_text += f"{i}. {task_title} ({time_str}) {notify_icon}\n"
                    else:
                        message_text += f"{i}. {task_title} {notify_icon}\n"
                
                if len(remaining_tasks) > 10:
                    message_text += f"\n... and {len(remaining_tasks) - 10} more tasks"
            
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "notes":
            notes = load_json_file(NOTES_FILE)
            
            if not notes:
                message_text = "📝 <b>Notes</b>\n\nNo notes found."
            else:
                message_text = f"📝 <b>Notes</b>\n\nTotal: {len(notes)} notes\n\n"
                for i, note in enumerate(notes[:10], 1):  # Show first 10
                    note_title = note.get('title', 'Untitled Note')
                    if len(note_title) > 40:
                        note_title = note_title[:37] + '...'
                    
                    notify_icon = "🔔" if note.get('notify_enabled', False) else ""
                    message_text += f"{i}. {note_title} {notify_icon}\n"
                
                if len(notes) > 10:
                    message_text += f"\n... and {len(notes) - 10} more notes"
            
            keyboard = create_back_to_menu_keyboard()
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        
        elif call.data == "refresh":
            menu_msg = """
📱 <b>Main Menu</b>

Choose an option below:
"""
            keyboard = create_main_menu_keyboard()
            bot.edit_message_text(
                menu_msg,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            bot.answer_callback_query(call.id, "✅ Refreshed!")
        
        else:
            bot.answer_callback_query(call.id, "Unknown command")
    
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle other messages"""
    if str(message.chat.id) != USER_ID:
        bot.reply_to(message, "❌ Unauthorized access")
        return
    
    if message.text.lower() in ['menu', 'main menu', 'show menu']:
        show_main_menu(message)
    else:
        response = f"""
Echo: <b>{message.text}</b>

Send /start to see the main menu or /menu to open the menu directly.
"""
        send_telegram_message(message.chat.id, response)

# ============= WEB ROUTES =============
@app.route('/')
def home():
    """Home page"""
    stats = get_bot_stats()
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Task Tracker Bot</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                color: white;
            }}
            .container {{
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                padding: 30px;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }}
            h1 {{
                text-align: center;
                font-size: 2.5em;
                margin-bottom: 10px;
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }}
            .stat-card {{
                background: rgba(255, 255, 255, 0.15);
                padding: 20px;
                border-radius: 15px;
                text-align: center;
                transition: all 0.3s;
            }}
            .stat-card:hover {{
                transform: translateY(-5px);
                background: rgba(255, 255, 255, 0.2);
            }}
            .stat-value {{
                font-size: 2.5em;
                font-weight: bold;
                margin: 10px 0;
            }}
            .btn {{
                display: block;
                width: 100%;
                background: white;
                color: #667eea;
                text-align: center;
                padding: 15px;
                border-radius: 10px;
                text-decoration: none;
                font-weight: bold;
                margin: 10px 0;
                transition: all 0.3s;
            }}
            .btn:hover {{
                transform: translateY(-3px);
                box-shadow: 0 10px 20px rgba(0,0,0,0.2);
            }}
            .status-indicator {{
                display: inline-block;
                width: 12px;
                height: 12px;
                border-radius: 50%;
                margin-right: 8px;
            }}
            .status-on {{
                background: #4CAF50;
                box-shadow: 0 0 10px #4CAF50;
            }}
            .status-off {{
                background: #f44336;
                box-shadow: 0 0 10px #f44336;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Task Tracker Bot</h1>
            <p style="text-align: center; opacity: 0.9;">Mini App Integration • Real-time Monitoring • Telegram Notifications</p>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>📋 Total Tasks</h3>
                    <div class="stat-value">{stats['total_tasks']}</div>
                    <p>{stats['completed_tasks']} completed • {stats['remaining_tasks']} remaining</p>
                </div>
                <div class="stat-card">
                    <h3>📝 Total Notes</h3>
                    <div class="stat-value">{stats['total_notes']}</div>
                    <p>{stats['notes_with_notifications']} with notifications</p>
                </div>
                <div class="stat-card">
                    <h3>⏰ Uptime</h3>
                    <div class="stat-value">{stats['uptime'].split(':')[0]}h</div>
                    <p>{stats['uptime']}</p>
                </div>
                <div class="stat-card">
                    <h3>🔔 Status</h3>
                    <div class="stat-value">
                        <span class="status-indicator {'status-on' if stats['monitor_active'] else 'status-off'}"></span>
                        {'Active' if stats['monitor_active'] else 'Inactive'}
                    </div>
                    <p>Hourly: {'ON' if stats['hourly_notifications'] else 'OFF'}</p>
                </div>
            </div>
            
            <a href="{MINI_APP_URL}" class="btn" target="_blank">
                📱 Open Mini App
            </a>
            
            <div style="margin-top: 30px; padding: 20px; background: rgba(0,0,0,0.2); border-radius: 10px;">
                <h3>⚡ Features</h3>
                <ul>
                    <li>✅ Task reminders (10 minutes before start)</li>
                    <li>✅ Note reminders (custom intervals)</li>
                    <li>✅ Hourly status reports (24x per day)</li>
                    <li>✅ Mini App for full task management</li>
                    <li>✅ Real-time monitoring</li>
                    <li>✅ Telegram inline menu</li>
                </ul>
                
                <p style="margin-top: 20px; color: rgba(255,255,255,0.8);">
                    <strong>Mini App URL:</strong> {MINI_APP_URL}<br>
                    <strong>User ID:</strong> {USER_ID}<br>
                    <strong>Last updated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </p>
            </div>
        </div>
        
        <script>
            // Auto-refresh every 30 seconds
            setTimeout(() => location.reload(), 30000);
        </script>
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
    if send_telegram_message(USER_ID, test_msg):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial; text-align: center; padding: 50px; background: #f5f5f5; }
                .success { color: #4CAF50; font-size: 2em; }
                .btn { display: inline-block; margin-top: 20px; padding: 10px 20px; background: #4CAF50; color: white; text-decoration: none; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="success">✅ Test message sent!</div>
            <p>Check your Telegram bot.</p>
            <a href="/" class="btn">← Back to Dashboard</a>
        </body>
        </html>
        """
    else:
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial; text-align: center; padding: 50px; background: #f5f5f5; }
                .error { color: #f44336; font-size: 2em; }
                .btn { display: inline-block; margin-top: 20px; padding: 10px 20px; background: #f44336; color: white; text-decoration: none; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="error">❌ Failed to send message</div>
            <a href="/" class="btn">← Back to Dashboard</a>
        </body>
        </html>
        """

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
        
        # Load hourly notifications setting
        notification_settings = load_json_file(NOTIFICATIONS_FILE)
        global hourly_notifications
        if isinstance(notification_settings, dict):
            hourly_notifications = notification_settings.get('hourly_report', True)
        
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
• Mini App integration

Send /start to begin!
"""
        send_telegram_message(USER_ID, startup_msg)
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
