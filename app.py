"""
Task Tracker with Telegram Bot - IST Timezone
Enhanced UI with GitHub Storage
"""

import os
import json
import threading
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, Response, render_template_string, jsonify, session, redirect, url_for
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import time
import secrets
import requests
import base64
import uuid

# ============= CONFIGURATION =============
BOT_TOKEN = "8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I"
ADMIN_ID = "8469993808"
SECRET_KEY = secrets.token_hex(32)

GITHUB_TOKEN = "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"
GITHUB_REPO = "Qepheyr/gettingfast"
GITHUB_USER = "Qepheyr"

IST = pytz.timezone('Asia/Kolkata')

app = Flask(__name__)
app.secret_key = SECRET_KEY
bot = telebot.TeleBot(BOT_TOKEN)

def get_ist_time():
    return datetime.now(IST)

def github_api_request(method, endpoint, data=None):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    url = f"https://api.github.com/{endpoint}"
    
    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "PUT":
        response = requests.put(url, headers=headers, json=data)
    elif method == "POST":
        response = requests.post(url, headers=headers, json=data)
    
    return response

def load_data_from_github():
    try:
        tasks_response = github_api_request(
            "GET", 
            f"repos/{GITHUB_REPO}/contents/data/tasks.json"
        )
        
        if tasks_response.status_code == 200:
            tasks_content = base64.b64decode(tasks_response.json()["content"]).decode()
            tasks_data = json.loads(tasks_content)
        else:
            tasks_data = {"tasks": []}
        
        notes_response = github_api_request(
            "GET",
            f"repos/{GITHUB_REPO}/contents/data/notes.json"
        )
        
        if notes_response.status_code == 200:
            notes_content = base64.b64decode(notes_response.json()["content"]).decode()
            notes_data = json.loads(notes_content)
        else:
            notes_data = {"notes": []}
        
        return tasks_data, notes_data
        
    except Exception as e:
        print(f"Error loading from GitHub: {e}")
        return {"tasks": []}, {"notes": []}

def save_data_to_github(tasks_data, notes_data):
    try:
        try:
            github_api_request(
                "PUT",
                f"repos/{GITHUB_REPO}/contents/data",
                {
                    "message": "Create data directory",
                    "content": base64.b64encode(b"{}").decode()
                }
            )
        except:
            pass
        
        tasks_response = github_api_request(
            "GET",
            f"repos/{GITHUB_REPO}/contents/data/tasks.json"
        )
        
        tasks_content = json.dumps(tasks_data, indent=2)
        tasks_payload = {
            "message": "Update tasks",
            "content": base64.b64encode(tasks_content.encode()).decode(),
            "sha": tasks_response.json()["sha"] if tasks_response.status_code == 200 else None
        }
        
        github_api_request(
            "PUT",
            f"repos/{GITHUB_REPO}/contents/data/tasks.json",
            tasks_payload
        )
        
        notes_response = github_api_request(
            "GET",
            f"repos/{GITHUB_REPO}/contents/data/notes.json"
        )
        
        notes_content = json.dumps(notes_data, indent=2)
        notes_payload = {
            "message": "Update notes",
            "content": base64.b64encode(notes_content.encode()).decode(),
            "sha": notes_response.json()["sha"] if notes_response.status_code == 200 else None
        }
        
        github_api_request(
            "PUT",
            f"repos/{GITHUB_REPO}/contents/data/notes.json",
            notes_payload
        )
        
        return True
    except Exception as e:
        print(f"Error saving to GitHub: {e}")
        return False

ENHANCED_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Task Tracker Pro</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
        }
        
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --secondary: #8b5cf6;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --light: #f8fafc;
            --dark: #1e293b;
            --gray: #64748b;
            --gray-light: #e2e8f0;
            --card-bg: rgba(255, 255, 255, 0.95);
            --shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1);
            --radius: 16px;
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            color: var(--dark);
            overflow-x: hidden;
        }
        
        .app-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            max-width: 500px;
            margin: 0 auto;
            width: 100%;
            background: var(--light);
            position: relative;
            min-height: 100vh;
            box-shadow: var(--shadow);
        }
        
        .header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            padding: 24px 20px;
            text-align: center;
            position: relative;
            border-radius: 0 0 var(--radius) var(--radius);
        }
        
        .header h1 {
            font-size: 1.8rem;
            font-weight: 700;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }
        
        .header .date {
            font-size: 0.9rem;
            opacity: 0.9;
        }
        
        .content-area {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            padding-bottom: 80px;
        }
        
        .tab-content {
            display: none;
            animation: fadeIn 0.3s ease;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .page-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }
        
        .page-title {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--dark);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .add-btn {
            background: var(--primary);
            color: white;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
            transition: var(--transition);
            border: none;
        }
        
        .add-btn:hover {
            background: var(--primary-dark);
            transform: scale(1.05);
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
        }
        
        .tasks-list, .notes-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .task-card, .note-card {
            background: var(--card-bg);
            padding: 18px;
            border-radius: var(--radius);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            transition: var(--transition);
            border-left: 4px solid var(--primary);
        }
        
        .task-card:hover, .note-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 15px rgba(0, 0, 0, 0.12);
        }
        
        .task-card.high { border-left-color: var(--danger); }
        .task-card.medium { border-left-color: var(--warning); }
        .task-card.low { border-left-color: var(--success); }
        
        .task-header, .note-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 8px;
        }
        
        .task-title, .note-title {
            font-weight: 600;
            font-size: 1.1rem;
            color: var(--dark);
        }
        
        .priority {
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        
        .priority.high { background: rgba(239, 68, 68, 0.15); color: var(--danger); }
        .priority.medium { background: rgba(245, 158, 11, 0.15); color: var(--warning); }
        .priority.low { background: rgba(16, 185, 129, 0.15); color: var(--success); }
        
        .task-desc, .note-content {
            color: var(--gray);
            font-size: 0.9rem;
            line-height: 1.5;
            margin-bottom: 12px;
        }
        
        .task-footer, .note-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.8rem;
            color: var(--gray);
        }
        
        .task-date, .note-date {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        
        .task-actions, .note-actions {
            display: flex;
            gap: 8px;
        }
        
        .icon-btn {
            background: none;
            border: none;
            color: var(--gray);
            cursor: pointer;
            font-size: 1rem;
            transition: var(--transition);
            padding: 4px;
            border-radius: 6px;
        }
        
        .icon-btn:hover {
            color: var(--primary);
            background: rgba(99, 102, 241, 0.1);
        }
        
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--gray);
        }
        
        .empty-state i {
            font-size: 3rem;
            margin-bottom: 15px;
            opacity: 0.5;
        }
        
        .empty-state p {
            font-size: 1rem;
        }
        
        .history-controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            background: var(--card-bg);
            padding: 15px;
            border-radius: var(--radius);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        }
        
        .sort-select {
            padding: 8px 15px;
            border-radius: 10px;
            border: 2px solid var(--gray-light);
            background: white;
            color: var(--dark);
            font-weight: 500;
            cursor: pointer;
            transition: var(--transition);
        }
        
        .sort-select:focus {
            outline: none;
            border-color: var(--primary);
        }
        
        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            max-width: 500px;
            margin: 0 auto;
            background: var(--card-bg);
            display: flex;
            justify-content: space-around;
            padding: 15px 10px;
            border-top: 1px solid var(--gray-light);
            z-index: 100;
        }
        
        .nav-btn {
            display: flex;
            flex-direction: column;
            align-items: center;
            background: none;
            border: none;
            color: var(--gray);
            cursor: pointer;
            transition: var(--transition);
            padding: 8px 15px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
            gap: 5px;
        }
        
        .nav-btn i {
            font-size: 1.3rem;
        }
        
        .nav-btn.active {
            color: var(--primary);
            background: rgba(99, 102, 241, 0.1);
        }
        
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.7);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            animation: fadeIn 0.2s ease;
        }
        
        .modal.active {
            display: flex;
        }
        
        .modal-content {
            background: white;
            width: 90%;
            max-width: 400px;
            border-radius: var(--radius);
            padding: 25px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
            animation: slideUp 0.3s ease;
        }
        
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        
        .modal-title {
            font-size: 1.3rem;
            font-weight: 700;
            color: var(--dark);
        }
        
        .close-modal {
            background: none;
            border: none;
            font-size: 1.5rem;
            color: var(--gray);
            cursor: pointer;
            transition: var(--transition);
        }
        
        .close-modal:hover {
            color: var(--danger);
        }
        
        .form-group {
            margin-bottom: 18px;
        }
        
        .form-label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: var(--dark);
        }
        
        .form-input, .form-textarea, .form-select {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid var(--gray-light);
            border-radius: 10px;
            font-size: 1rem;
            transition: var(--transition);
            background: white;
        }
        
        .form-input:focus, .form-textarea:focus, .form-select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }
        
        .form-textarea {
            min-height: 100px;
            resize: vertical;
        }
        
        .btn-submit {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            border: none;
            padding: 14px 25px;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: var(--transition);
            width: 100%;
            margin-top: 10px;
        }
        
        .btn-submit:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(99, 102, 241, 0.4);
        }
        
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-right: 5px;
        }
        
        .badge.completed { background: rgba(16, 185, 129, 0.15); color: var(--success); }
        .badge.pending { background: rgba(245, 158, 11, 0.15); color: var(--warning); }
        
        .status-toggle {
            display: flex;
            gap: 10px;
            margin-top: 10px;
        }
        
        .status-btn {
            flex: 1;
            padding: 10px;
            border-radius: 8px;
            border: 2px solid var(--gray-light);
            background: white;
            font-weight: 500;
            cursor: pointer;
            transition: var(--transition);
            text-align: center;
        }
        
        .status-btn.active {
            border-color: var(--primary);
            background: rgba(99, 102, 241, 0.1);
            color: var(--primary);
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        @keyframes slideUp {
            from { transform: translateY(30px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        
        @media (max-width: 480px) {
            .header { padding: 20px 15px; }
            .content-area { padding: 15px; }
            .modal-content { width: 95%; padding: 20px; }
        }
        
        .loading {
            text-align: center;
            padding: 30px;
            color: var(--gray);
        }
        
        .loading i {
            font-size: 2rem;
            margin-bottom: 10px;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="app-container">
        <div class="header">
            <h1><i class="fas fa-tasks"></i> Task Tracker Pro</h1>
            <div class="date" id="currentDate"></div>
        </div>
        
        <div class="content-area">
            <div id="tasksTab" class="tab-content active">
                <div class="page-header">
                    <div class="page-title"><i class="fas fa-tasks"></i> Tasks</div>
                    <button class="add-btn" onclick="openTaskModal()">
                        <i class="fas fa-plus"></i>
                    </button>
                </div>
                <div id="tasksList" class="tasks-list">
                    <div class="loading">
                        <i class="fas fa-spinner"></i>
                        <p>Loading tasks...</p>
                    </div>
                </div>
            </div>
            
            <div id="notesTab" class="tab-content">
                <div class="page-header">
                    <div class="page-title"><i class="fas fa-sticky-note"></i> Notes</div>
                    <button class="add-btn" onclick="openNoteModal()">
                        <i class="fas fa-plus"></i>
                    </button>
                </div>
                <div id="notesList" class="notes-list">
                    <div class="loading">
                        <i class="fas fa-spinner"></i>
                        <p>Loading notes...</p>
                    </div>
                </div>
            </div>
            
            <div id="historyTab" class="tab-content">
                <div class="history-controls">
                    <div class="page-title"><i class="fas fa-history"></i> History</div>
                    <select class="sort-select" id="sortSelect" onchange="sortHistory()">
                        <option value="newest">Newest First</option>
                        <option value="oldest">Oldest First</option>
                        <option value="priority_high">Priority: High to Low</option>
                        <option value="priority_low">Priority: Low to High</option>
                    </select>
                </div>
                <div id="historyList" class="tasks-list">
                    <div class="loading">
                        <i class="fas fa-spinner"></i>
                        <p>Loading history...</p>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="bottom-nav">
            <button class="nav-btn active" onclick="switchTab('tasks')">
                <i class="fas fa-tasks"></i>
                <span>Tasks</span>
            </button>
            <button class="nav-btn" onclick="switchTab('notes')">
                <i class="fas fa-sticky-note"></i>
                <span>Notes</span>
            </button>
            <button class="nav-btn" onclick="switchTab('history')">
                <i class="fas fa-history"></i>
                <span>History</span>
            </button>
        </div>
        
        <div id="taskModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title" id="taskModalTitle">Add New Task</div>
                    <button class="close-modal" onclick="closeTaskModal()">&times;</button>
                </div>
                <form id="taskForm" onsubmit="saveTask(event)">
                    <div class="form-group">
                        <label class="form-label">Task Title</label>
                        <input type="text" class="form-input" id="taskTitle" placeholder="Enter task title" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Description</label>
                        <textarea class="form-textarea" id="taskDesc" placeholder="Enter task description"></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Priority</label>
                        <select class="form-select" id="taskPriority" required>
                            <option value="high">High</option>
                            <option value="medium" selected>Medium</option>
                            <option value="low">Low</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Due Date</label>
                        <input type="date" class="form-input" id="taskDueDate">
                    </div>
                    <div class="form-group" id="statusGroup">
                        <label class="form-label">Status</label>
                        <div class="status-toggle">
                            <button type="button" class="status-btn active" data-status="pending" onclick="setStatus('pending')">Pending</button>
                            <button type="button" class="status-btn" data-status="completed" onclick="setStatus('completed')">Completed</button>
                        </div>
                    </div>
                    <input type="hidden" id="taskId">
                    <button type="submit" class="btn-submit">Save Task</button>
                </form>
            </div>
        </div>
        
        <div id="noteModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title" id="noteModalTitle">Add New Note</div>
                    <button class="close-modal" onclick="closeNoteModal()">&times;</button>
                </div>
                <form id="noteForm" onsubmit="saveNote(event)">
                    <div class="form-group">
                        <label class="form-label">Note Title</label>
                        <input type="text" class="form-input" id="noteTitle" placeholder="Enter note title" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Content</label>
                        <textarea class="form-textarea" id="noteContent" placeholder="Enter your note" required></textarea>
                    </div>
                    <input type="hidden" id="noteId">
                    <button type="submit" class="btn-submit">Save Note</button>
                </form>
            </div>
        </div>
    </div>
    
    <script>
        let currentTab = 'tasks';
        let currentTaskStatus = 'pending';
        let tasks = [];
        let notes = [];
        
        document.addEventListener('DOMContentLoaded', function() {
            updateDate();
            loadAllData();
            
            document.querySelectorAll('.modal').forEach(modal => {
                modal.addEventListener('click', function(e) {
                    if (e.target === this) {
                        closeTaskModal();
                        closeNoteModal();
                    }
                });
            });
        });
        
        function updateDate() {
            const now = new Date();
            const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
            document.getElementById('currentDate').textContent = now.toLocaleDateString('en-US', options);
        }
        
        function switchTab(tab) {
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            currentTab = tab;
            document.getElementById(tab + 'Tab').classList.add('active');
            document.querySelector(`.nav-btn[onclick="switchTab('${tab}')"]`).classList.add('active');
            
            if (tab === 'tasks') loadTasks();
            else if (tab === 'notes') loadNotes();
            else if (tab === 'history') loadHistory();
        }
        
        function loadAllData() {
            fetch('/api/data')
                .then(response => response.json())
                .then(data => {
                    tasks = data.tasks || [];
                    notes = data.notes || [];
                    loadTasks();
                    loadNotes();
                    loadHistory();
                })
                .catch(error => {
                    console.error('Error loading data:', error);
                    showError('Failed to load data');
                });
        }
        
        function loadTasks() {
            const container = document.getElementById('tasksList');
            const pendingTasks = tasks.filter(task => task.status === 'pending');
            
            if (pendingTasks.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-tasks"></i>
                        <p>No tasks yet. Add your first task!</p>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = pendingTasks.map(task => `
                <div class="task-card ${task.priority}" data-id="${task.id}">
                    <div class="task-header">
                        <div class="task-title">${escapeHtml(task.title)}</div>
                        <div class="priority ${task.priority}">${task.priority.toUpperCase()}</div>
                    </div>
                    ${task.description ? `<div class="task-desc">${escapeHtml(task.description)}</div>` : ''}
                    <div class="task-footer">
                        <div class="task-date">
                            <i class="far fa-calendar"></i>
                            ${formatDate(task.created_at)}
                        </div>
                        <div class="task-actions">
                            <button class="icon-btn" onclick="completeTask('${task.id}')" title="Mark Complete">
                                <i class="fas fa-check"></i>
                            </button>
                            <button class="icon-btn" onclick="editTask('${task.id}')" title="Edit">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="icon-btn" onclick="deleteTask('${task.id}')" title="Delete">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        function loadNotes() {
            const container = document.getElementById('notesList');
            
            if (notes.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-sticky-note"></i>
                        <p>No notes yet. Add your first note!</p>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = notes.map(note => `
                <div class="note-card" data-id="${note.id}">
                    <div class="note-header">
                        <div class="note-title">${escapeHtml(note.title)}</div>
                    </div>
                    <div class="note-content">${escapeHtml(note.content)}</div>
                    <div class="note-footer">
                        <div class="note-date">
                            <i class="far fa-calendar"></i>
                            ${formatDate(note.created_at)}
                        </div>
                        <div class="note-actions">
                            <button class="icon-btn" onclick="editNote('${note.id}')" title="Edit">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="icon-btn" onclick="deleteNote('${note.id}')" title="Delete">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        function loadHistory() {
            const container = document.getElementById('historyList');
            const allTasks = [...tasks];
            
            if (allTasks.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-history"></i>
                        <p>No history yet. Complete some tasks!</p>
                    </div>
                `;
                return;
            }
            
            sortHistoryData(allTasks);
            
            container.innerHTML = allTasks.map(task => `
                <div class="task-card ${task.priority}" data-id="${task.id}">
                    <div class="task-header">
                        <div class="task-title">${escapeHtml(task.title)}</div>
                        <div class="badge ${task.status}">${task.status.toUpperCase()}</div>
                    </div>
                    ${task.description ? `<div class="task-desc">${escapeHtml(task.description)}</div>` : ''}
                    <div class="task-footer">
                        <div class="task-date">
                            <i class="far fa-calendar"></i>
                            ${formatDate(task.created_at)}
                            ${task.completed_at ? ` • Completed: ${formatDate(task.completed_at)}` : ''}
                        </div>
                        <div class="task-actions">
                            ${task.status === 'pending' ? 
                                `<button class="icon-btn" onclick="completeTask('${task.id}')" title="Mark Complete">
                                    <i class="fas fa-check"></i>
                                </button>` : ''
                            }
                            <button class="icon-btn" onclick="editTask('${task.id}')" title="Edit">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="icon-btn" onclick="deleteTask('${task.id}')" title="Delete">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        function sortHistory() {
            loadHistory();
        }
        
        function sortHistoryData(tasksArray) {
            const sortValue = document.getElementById('sortSelect').value;
            
            tasksArray.sort((a, b) => {
                const priorityOrder = { high: 3, medium: 2, low: 1 };
                
                switch (sortValue) {
                    case 'newest':
                        return new Date(b.created_at) - new Date(a.created_at);
                    case 'oldest':
                        return new Date(a.created_at) - new Date(b.created_at);
                    case 'priority_high':
                        return priorityOrder[b.priority] - priorityOrder[a.priority] || 
                               new Date(b.created_at) - new Date(a.created_at);
                    case 'priority_low':
                        return priorityOrder[a.priority] - priorityOrder[b.priority] || 
                               new Date(a.created_at) - new Date(b.created_at);
                    default:
                        return new Date(b.created_at) - new Date(a.created_at);
                }
            });
        }
        
        function openTaskModal(taskId = null) {
            const modal = document.getElementById('taskModal');
            const form = document.getElementById('taskForm');
            const title = document.getElementById('taskModalTitle');
            
            if (taskId) {
                const task = tasks.find(t => t.id === taskId);
                if (task) {
                    title.textContent = 'Edit Task';
                    document.getElementById('taskId').value = task.id;
                    document.getElementById('taskTitle').value = task.title;
                    document.getElementById('taskDesc').value = task.description || '';
                    document.getElementById('taskPriority').value = task.priority;
                    document.getElementById('taskDueDate').value = task.due_date || '';
                    setStatus(task.status);
                    currentTaskStatus = task.status;
                }
            } else {
                title.textContent = 'Add New Task';
                form.reset();
                document.getElementById('taskId').value = '';
                setStatus('pending');
                currentTaskStatus = 'pending';
                
                const tomorrow = new Date();
                tomorrow.setDate(tomorrow.getDate() + 1);
                document.getElementById('taskDueDate').value = tomorrow.toISOString().split('T')[0];
            }
            
            modal.classList.add('active');
        }
        
        function closeTaskModal() {
            document.getElementById('taskModal').classList.remove('active');
        }
        
        function openNoteModal(noteId = null) {
            const modal = document.getElementById('noteModal');
            const form = document.getElementById('noteForm');
            const title = document.getElementById('noteModalTitle');
            
            if (noteId) {
                const note = notes.find(n => n.id === noteId);
                if (note) {
                    title.textContent = 'Edit Note';
                    document.getElementById('noteId').value = note.id;
                    document.getElementById('noteTitle').value = note.title;
                    document.getElementById('noteContent').value = note.content;
                }
            } else {
                title.textContent = 'Add New Note';
                form.reset();
                document.getElementById('noteId').value = '';
            }
            
            modal.classList.add('active');
        }
        
        function closeNoteModal() {
            document.getElementById('noteModal').classList.remove('active');
        }
        
        function setStatus(status) {
            currentTaskStatus = status;
            document.querySelectorAll('.status-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.status === status);
            });
        }
        
        function saveTask(event) {
            event.preventDefault();
            
            const taskId = document.getElementById('taskId').value;
            const taskData = {
                title: document.getElementById('taskTitle').value,
                description: document.getElementById('taskDesc').value,
                priority: document.getElementById('taskPriority').value,
                due_date: document.getElementById('taskDueDate').value || null,
                status: currentTaskStatus
            };
            
            if (taskId) {
                taskData.id = taskId;
                updateTask(taskData);
            } else {
                addTask(taskData);
            }
        }
        
        function addTask(taskData) {
            fetch('/api/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(taskData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    closeTaskModal();
                    loadAllData();
                    showMessage('Task added successfully!');
                } else {
                    showError('Failed to add task');
                }
            })
            .catch(error => {
                console.error('Error adding task:', error);
                showError('Failed to add task');
            });
        }
        
        function updateTask(taskData) {
            fetch('/api/tasks', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(taskData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    closeTaskModal();
                    loadAllData();
                    showMessage('Task updated successfully!');
                } else {
                    showError('Failed to update task');
                }
            })
            .catch(error => {
                console.error('Error updating task:', error);
                showError('Failed to update task');
            });
        }
        
        function completeTask(taskId) {
            if (!confirm('Mark this task as completed?')) return;
            
            fetch(`/api/tasks/${taskId}/complete`, {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    loadAllData();
                    showMessage('Task marked as completed!');
                } else {
                    showError('Failed to complete task');
                }
            })
            .catch(error => {
                console.error('Error completing task:', error);
                showError('Failed to complete task');
            });
        }
        
        function deleteTask(taskId) {
            if (!confirm('Are you sure you want to delete this task?')) return;
            
            fetch(`/api/tasks/${taskId}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    loadAllData();
                    showMessage('Task deleted successfully!');
                } else {
                    showError('Failed to delete task');
                }
            })
            .catch(error => {
                console.error('Error deleting task:', error);
                showError('Failed to delete task');
            });
        }
        
        function editTask(taskId) {
            openTaskModal(taskId);
        }
        
        function saveNote(event) {
            event.preventDefault();
            
            const noteId = document.getElementById('noteId').value;
            const noteData = {
                title: document.getElementById('noteTitle').value,
                content: document.getElementById('noteContent').value
            };
            
            if (noteId) {
                noteData.id = noteId;
                updateNote(noteData);
            } else {
                addNote(noteData);
            }
        }
        
        function addNote(noteData) {
            fetch('/api/notes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(noteData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    closeNoteModal();
                    loadAllData();
                    showMessage('Note added successfully!');
                } else {
                    showError('Failed to add note');
                }
            })
            .catch(error => {
                console.error('Error adding note:', error);
                showError('Failed to add note');
            });
        }
        
        function updateNote(noteData) {
            fetch('/api/notes', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(noteData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    closeNoteModal();
                    loadAllData();
                    showMessage('Note updated successfully!');
                } else {
                    showError('Failed to update note');
                }
            })
            .catch(error => {
                console.error('Error updating note:', error);
                showError('Failed to update note');
            });
        }
        
        function deleteNote(noteId) {
            if (!confirm('Are you sure you want to delete this note?')) return;
            
            fetch(`/api/notes/${noteId}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    loadAllData();
                    showMessage('Note deleted successfully!');
                } else {
                    showError('Failed to delete note');
                }
            })
            .catch(error => {
                console.error('Error deleting note:', error);
                showError('Failed to delete note');
            });
        }
        
        function editNote(noteId) {
            openNoteModal(noteId);
        }
        
        function formatDate(dateString) {
            const date = new Date(dateString);
            return date.toLocaleDateString('en-US', { 
                month: 'short', 
                day: 'numeric',
                year: date.getFullYear() !== new Date().getFullYear() ? 'numeric' : undefined
            });
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function showMessage(text) {
            alert(text);
        }
        
        function showError(text) {
            alert('Error: ' + text);
        }
    </script>
</body>
</html>
'''

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = str(message.from_user.id)
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ <b>Unauthorized Access</b>\n\nThis bot is private and only accessible to authorized users.", parse_mode='HTML')
        return
    
    now = get_ist_time()
    username = message.from_user.username or message.from_user.first_name or "Admin"
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📱 Open Task Tracker", web_app=WebAppInfo(url=f"https://handsome-rafaela-sandip232-7f9d347c.koyeb.app/mini_app"))
    )
    
    welcome_message = f"""
━━━━━━━━━━━━━━━━━━━━
🤖 <b>Welcome to Task Tracker Pro!</b>
━━━━━━━━━━━━━━━━━━━━

👤 <i>User:</i> <b>{username}</b>
⏰ <i>Time:</i> <b>{now.strftime('%I:%M %p')} IST</b>
📅 <i>Date:</i> <b>{now.strftime('%B %d, %Y')}</b>

━━━━━━━━━━━━━━━━━━━━
📱 <b>Features:</b>
━━━━━━━━━━━━━━━━━━━━

• 📝 <b>Task Management</b> - Add, edit, complete tasks
• 🗒️ <b>Notes</b> - Keep important notes
• 📊 <b>History</b> - View task history with sorting
• 🎯 <b>Priority Levels</b> - High, Medium, Low
• 💾 <b>Cloud Storage</b> - GitHub-powered storage

Click the button below to open the app:
"""
    
    bot.send_message(message.chat.id, welcome_message, parse_mode='HTML', reply_markup=keyboard)

@app.route('/api/data', methods=['GET'])
def api_get_data():
    try:
        tasks_data, notes_data = load_data_from_github()
        return jsonify({
            'success': True,
            'tasks': tasks_data.get('tasks', []),
            'notes': notes_data.get('notes', [])
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tasks', methods=['POST'])
def api_add_task():
    try:
        data = request.json
        tasks_data, notes_data = load_data_from_github()
        
        new_task = {
            'id': str(uuid.uuid4()),
            'title': data['title'],
            'description': data.get('description', ''),
            'priority': data['priority'],
            'due_date': data.get('due_date'),
            'status': data.get('status', 'pending'),
            'created_at': datetime.now(IST).isoformat(),
            'completed_at': None
        }
        
        tasks_data['tasks'].append(new_task)
        
        if save_data_to_github(tasks_data, notes_data):
            return jsonify({'success': True, 'task': new_task})
        else:
            return jsonify({'success': False, 'error': 'Failed to save'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tasks', methods=['PUT'])
def api_update_task():
    try:
        data = request.json
        tasks_data, notes_data = load_data_from_github()
        
        task_index = next((i for i, t in enumerate(tasks_data['tasks']) if t['id'] == data['id']), -1)
        
        if task_index == -1:
            return jsonify({'success': False, 'error': 'Task not found'}), 404
        
        tasks_data['tasks'][task_index].update({
            'title': data['title'],
            'description': data.get('description', ''),
            'priority': data['priority'],
            'due_date': data.get('due_date'),
            'status': data.get('status', 'pending')
        })
        
        if save_data_to_github(tasks_data, notes_data):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tasks/<task_id>/complete', methods=['POST'])
def api_complete_task(task_id):
    try:
        tasks_data, notes_data = load_data_from_github()
        
        task_index = next((i for i, t in enumerate(tasks_data['tasks']) if t['id'] == task_id), -1)
        
        if task_index == -1:
            return jsonify({'success': False, 'error': 'Task not found'}), 404
        
        tasks_data['tasks'][task_index].update({
            'status': 'completed',
            'completed_at': datetime.now(IST).isoformat()
        })
        
        if save_data_to_github(tasks_data, notes_data):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tasks/<task_id>', methods=['DELETE'])
def api_delete_task(task_id):
    try:
        tasks_data, notes_data = load_data_from_github()
        
        tasks_data['tasks'] = [t for t in tasks_data['tasks'] if t['id'] != task_id]
        
        if save_data_to_github(tasks_data, notes_data):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/notes', methods=['POST'])
def api_add_note():
    try:
        data = request.json
        tasks_data, notes_data = load_data_from_github()
        
        new_note = {
            'id': str(uuid.uuid4()),
            'title': data['title'],
            'content': data['content'],
            'created_at': datetime.now(IST).isoformat(),
            'updated_at': datetime.now(IST).isoformat()
        }
        
        notes_data['notes'].append(new_note)
        
        if save_data_to_github(tasks_data, notes_data):
            return jsonify({'success': True, 'note': new_note})
        else:
            return jsonify({'success': False, 'error': 'Failed to save'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/notes', methods=['PUT'])
def api_update_note():
    try:
        data = request.json
        tasks_data, notes_data = load_data_from_github()
        
        note_index = next((i for i, n in enumerate(notes_data['notes']) if n['id'] == data['id']), -1)
        
        if note_index == -1:
            return jsonify({'success': False, 'error': 'Note not found'}), 404
        
        notes_data['notes'][note_index].update({
            'title': data['title'],
            'content': data['content'],
            'updated_at': datetime.now(IST).isoformat()
        })
        
        if save_data_to_github(tasks_data, notes_data):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/notes/<note_id>', methods=['DELETE'])
def api_delete_note(note_id):
    try:
        tasks_data, notes_data = load_data_from_github()
        
        notes_data['notes'] = [n for n in notes_data['notes'] if n['id'] != note_id]
        
        if save_data_to_github(tasks_data, notes_data):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to save'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/')
def index():
    return "Task Tracker Pro API is running. Please access via Telegram bot."

@app.route('/mini_app')
def mini_app():
    return render_template_string(ENHANCED_HTML)

@app.route('/auth/<path:user_info>')
def auth(user_info):
    try:
        if ADMIN_ID in user_info:
            session['logged_in'] = True
            session['username'] = "Admin User"
            return redirect('/mini_app')
        else:
            return "Unauthorized access.", 401
    except:
        return "Authentication failed.", 401

def start_bot_polling():
    print("🤖 Starting Telegram bot polling...")
    try:
        bot.polling(none_stop=True, interval=1, timeout=30)
    except Exception as e:
        print(f"❌ Bot polling error: {e}")
        time.sleep(5)
        start_bot_polling()

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Task Tracker Pro - Enhanced Version")
    print("=" * 60)
    now = get_ist_time()
    print(f"📅 IST Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"👑 Admin User ID: {ADMIN_ID}")
    print(f"📱 Features: Tasks, Notes, History with sorting")
    print(f"💾 Storage: GitHub-powered (Repo: {GITHUB_REPO})")
    print(f"🎨 UI: Modern, responsive design with bottom navigation")
    print("=" * 60)
    
    print("🔗 Testing GitHub connection...")
    try:
        test_response = github_api_request("GET", f"repos/{GITHUB_REPO}")
        if test_response.status_code == 200:
            print("✅ GitHub connection successful!")
        else:
            print(f"⚠️ GitHub connection issue: {test_response.status_code}")
    except Exception as e:
        print(f"❌ GitHub connection failed: {e}")
    
    print("=" * 60)
    
    bot_thread = threading.Thread(target=start_bot_polling, daemon=True)
    bot_thread.start()
    
    port = int(os.getenv('PORT', 8000))
    print(f"🌐 Web server: http://0.0.0.0:{port}")
    print(f"📱 Mini-app: http://0.0.0.0:{port}/mini_app")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
