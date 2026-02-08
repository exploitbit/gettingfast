<?php
session_start();
date_default_timezone_set("Asia/kolkata");

// Enhanced error handling
error_reporting(E_ALL);
ini_set('display_errors', 0);
ini_set('log_errors', 1);
ini_set('error_log', 'php_errors.log');

// Telegram configuration
define('TELEGRAM_BOT_TOKEN', '8388773187:AAFxz5U8GJ94Wf21VaGvFx9QQSZFU2Rd43I');
define('TELEGRAM_USER_ID', '8469993808');

// CSRF Protection
function generateCSRFToken() {
    if (empty($_SESSION['csrf_token'])) {
        $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf_token'];
}

function validateCSRFToken($token) {
    return isset($_SESSION['csrf_token']) && hash_equals($_SESSION['csrf_token'], $token);
}

// Secure ID generation
function generateSecureId($prefix = '') {
    return $prefix . bin2hex(random_bytes(16)) . '_' . time();
}

// Secure file operations
function safeFilePutContents($filename, $data) {
    $tempFile = $filename . '.tmp';
    if (file_put_contents($tempFile, $data) !== false) {
        if (rename($tempFile, $filename)) {
            return true;
        }
        unlink($tempFile);
    }
    return false;
}

// Send Telegram notification
function sendTelegramNotification($message) {
    try {
        $url = "https://api.telegram.org/bot" . TELEGRAM_BOT_TOKEN . "/sendMessage";
        $data = [
            'chat_id' => TELEGRAM_USER_ID,
            'text' => $message,
            'parse_mode' => 'HTML'
        ];
        
        $options = [
            'http' => [
                'header' => "Content-type: application/x-www-form-urlencoded\r\n",
                'method' => 'POST',
                'content' => http_build_query($data)
            ]
        ];
        
        $context = stream_context_create($options);
        $result = file_get_contents($url, false, $context);
        
        // Log notification
        logTelegramNotification($message, $result !== false);
        
        return $result !== false;
    } catch (Exception $e) {
        error_log("Telegram error: " . $e->getMessage());
        return false;
    }
}

// Log Telegram notifications
function logTelegramNotification($message, $success) {
    $logFile = 'telegram_log.json';
    $logs = [];
    
    if (file_exists($logFile)) {
        $content = file_get_contents($logFile);
        if ($content) {
            $logs = json_decode($content, true);
        }
    }
    
    $logs[] = [
        'timestamp' => date('Y-m-d H:i:s'),
        'message' => substr($message, 0, 100) . (strlen($message) > 100 ? '...' : ''),
        'success' => $success
    ];
    
    // Keep only last 100 logs
    if (count($logs) > 100) {
        $logs = array_slice($logs, -100);
    }
    
    safeFilePutContents($logFile, json_encode($logs, JSON_PRETTY_PRINT));
}

// File paths for data storage
$tasksFilePath = 'tasks.json';
$historyFilePath = 'history.json';
$configFilePath = 'config.json';
$notesFilePath = 'notes.json';
$notificationsFilePath = 'notifications.json';

// Initialize data structures
function initializeDataStructure() {
    return [];
}

// Load data from JSON files
function loadData($filePath) {
    if (file_exists($filePath)) {
        $content = file_get_contents($filePath);
        if ($content !== false) {
            $data = json_decode($content, true);
            if (is_array($data)) {
                return $data;
            }
        }
    }
    return initializeDataStructure();
}

// Save data to JSON files
function saveData($filePath, $data) {
    return safeFilePutContents($filePath, json_encode($data, JSON_PRETTY_PRINT));
}

// Load configuration or create it with a default access code
function loadOrCreateConfig($filePath) {
    $defaultConfig = ['access_code' => '1234'];
    if (file_exists($filePath)) {
        $content = file_get_contents($filePath);
        if ($content !== false) {
            $data = json_decode($content, true);
            if (is_array($data) && isset($data['access_code'])) {
                return $data;
            }
        }
    }
    // If file doesn't exist, is empty, or malformed, create it with the default
    saveData($filePath, $defaultConfig);
    return $defaultConfig;
}

// Authentication functions - SIMPLIFIED for single user
function isUserLoggedIn() {
    return isset($_SESSION['authenticated']) && $_SESSION['authenticated'] === true;
}

// Calculate next occurrence for repeating items with day
function calculateNextOccurrence($repeatType, $baseDate = null, $dayOfWeek = null) {
    if ($baseDate === null) {
        $baseDate = date('Y-m-d H:i:s');
    }
    
    $date = new DateTime($baseDate);
    
    switch ($repeatType) {
        case 'daily':
            $date->modify('+1 day');
            break;
        case 'weekly':
            $date->modify('+1 week');
            // If day of week is specified, adjust to that day
            if ($dayOfWeek !== null) {
                $date->modify('next ' . $dayOfWeek);
            }
            break;
        default:
            return null;
    }
    
    // Set time to 00:00:00 for next day
    $date->setTime(0, 0, 0);
    return $date->format('Y-m-d H:i:s');
}

// Check if repetitive item should be active today
function isItemActiveToday($item, $type = 'task') {
    if (($item['repeat'] ?? 'none') !== 'none') {
        if (!isset($item['nextOccurrence']) || empty($item['nextOccurrence'])) {
            return true;
        }
        
        $nextOccurrenceDate = date('Y-m-d', strtotime($item['nextOccurrence']));
        $currentDate = date('Y-m-d');
        
        return $currentDate >= $nextOccurrenceDate;
    }
    
    return true;
}

// Complete task with repetition handling
function completeTaskWithRepetition($taskId, &$userTasks, &$historyRecords) {
    foreach ($userTasks as &$task) {
        if ($task['id'] == $taskId && !$task['completed']) {
            $task['completed'] = true;
            
            $completedSubtasks = array_filter($task['subtasks'], function($subtask) {
                return $subtask['completed'];
            });
            
            $historyRecords[] = [
                'id' => $taskId,
                'title' => $task['title'],
                'description' => $task['description'],
                'type' => 'task',
                'bucket' => $task['bucket'],
                'repeat' => $task['repeat'],
                'completedAt' => date('Y-m-d H:i:s'),
                'subtasks' => $completedSubtasks,
                'time_range' => date('g:i A', strtotime($task['start_time'])) . ' - ' . date('g:i A', strtotime($task['end_time'])),
                'priority' => $task['priority'] ?? 15
            ];
            
            if ($task['repeat'] !== 'none') {
                $nextOccurrenceDate = calculateNextOccurrence($task['repeat'], $task['start_time'], $task['repeat_day'] ?? null);
                $originalStartTime = date('H:i', strtotime($task['start_time']));
                $originalEndTime = date('H:i', strtotime($task['end_time']));
                
                $nextOccurrenceDateTime = new DateTime($nextOccurrenceDate);
                $nextDateStr = $nextOccurrenceDateTime->format('Y-m-d');
                
                $newStartDateTime = $nextDateStr . ' ' . $originalStartTime;
                $newEndDateTime = $nextDateStr . ' ' . $originalEndTime;
                
                $regeneratedSubtasks = [];
                foreach ($task['subtasks'] as $originalSubtask) {
                    $regeneratedSubtasks[] = [
                        'id' => generateSecureId('sub_'),
                        'title' => $originalSubtask['title'],
                        'description' => $originalSubtask['description'] ?? '',
                        'completed' => false,
                        'priority' => $originalSubtask['priority'] ?? 15
                    ];
                }
                
                $task['start_time'] = $newStartDateTime;
                $task['end_time'] = $newEndDateTime;
                $task['completed'] = false;
                $task['nextOccurrence'] = $nextOccurrenceDate;
                $task['subtasks'] = $regeneratedSubtasks;
                $task['createdAt'] = date('Y-m-d H:i:s');
            }
            return true;
        }
    }
    return false;
}

// Handle missed days for repeating items
function handleMissedDaysForRepeatingItems(&$items, $type = 'task') {
    $currentDate = date('Y-m-d');
    
    foreach ($items as &$item) {
        if (($item['repeat'] ?? 'none') !== 'none' && !$item['completed']) {
            $itemDate = date('Y-m-d', strtotime($item['start_time']));
            
            if ($itemDate < $currentDate) {
                if ($item['repeat'] === 'daily') {
                    $originalStartTime = date('H:i', strtotime($item['start_time']));
                    $originalEndTime = date('H:i', strtotime($item['end_time']));
                    
                    $item['start_time'] = $currentDate . ' ' . $originalStartTime;
                    $item['end_time'] = $currentDate . ' ' . $originalEndTime;
                    $item['nextOccurrence'] = $currentDate . ' 00:00:00';
                } elseif ($item['repeat'] === 'weekly') {
                    $lastOccurrenceDate = new DateTime($item['start_time']);
                    
                    while ($lastOccurrenceDate->format('Y-m-d') < $currentDate) {
                        $lastOccurrenceDate->modify('+1 week');
                    }
                    $lastOccurrenceDateStr = $lastOccurrenceDate->format('Y-m-d');
                    
                    $originalStartTime = date('H:i', strtotime($item['start_time']));
                    $originalEndTime = date('H:i', strtotime($item['end_time']));
                    
                    $item['start_time'] = $lastOccurrenceDateStr . ' ' . $originalStartTime;
                    $item['end_time'] = $lastOccurrenceDateStr . ' ' . $originalEndTime;
                    $item['nextOccurrence'] = $lastOccurrenceDateStr . ' 00:00:00';
                }
            }
        }
    }
}

// Format text with markdown-like syntax
function formatText($text) {
    // Convert newlines to <br>
    $text = nl2br(htmlspecialchars($text));
    
    // Convert *bold* to <strong>
    $text = preg_replace('/\*(.*?)\*/', '<strong>$1</strong>', $text);
    
    // Convert _italic_ to <em>
    $text = preg_replace('/_(.*?)_/', '<em>$1</em>', $text);
    
    return $text;
}

// Send task status report
function sendTaskStatusReport($tasks) {
    $currentTime = date('H:i');
    
    // Filter active tasks for today
    $todayTasks = array_filter($tasks, function($task) {
        $taskDate = date('Y-m-d', strtotime($task['start_time']));
        $currentDate = date('Y-m-d');
        return $taskDate === $currentDate && !$task['completed'];
    });
    
    if (empty($todayTasks)) {
        $message = "📊 <b>Task Status Report</b>\n";
        $message .= "🕐 Time: $currentTime\n";
        $message .= "📅 Date: " . date('F j, Y') . "\n";
        $message .= "✅ No active tasks for today!";
    } else {
        $message = "📊 <b>Task Status Report</b>\n";
        $message .= "🕐 Time: $currentTime\n";
        $message .= "📅 Date: " . date('F j, Y') . "\n";
        $message .= "📋 Total Tasks: " . count($todayTasks) . "\n\n";
        
        $completedCount = 0;
        $pendingCount = 0;
        
        foreach ($todayTasks as $task) {
            $status = $task['completed'] ? '✅' : '⏳';
            $timeRange = date('g:i A', strtotime($task['start_time'])) . ' - ' . date('g:i A', strtotime($task['end_time']));
            $progress = '';
            
            if (!empty($task['subtasks'])) {
                $completedSubtasks = count(array_filter($task['subtasks'], function($subtask) {
                    return $subtask['completed'] ?? false;
                }));
                $totalSubtasks = count($task['subtasks']);
                $progress = " ($completedSubtasks/$totalSubtasks)";
            }
            
            $message .= "$status <b>{$task['title']}</b>\n";
            $message .= "   ⏰ $timeRange$progress\n";
            
            if ($task['completed']) {
                $completedCount++;
            } else {
                $pendingCount++;
            }
        }
        
        $message .= "\n📈 Summary:\n";
        $message .= "✅ Completed: $completedCount\n";
        $message .= "⏳ Pending: $pendingCount";
    }
    
    return sendTelegramNotification($message);
}

// Send task reminder notification
function sendTaskReminder($task) {
    $title = html_entity_decode(strip_tags($task['title']));
    $timeRange = date('g:i A', strtotime($task['start_time'])) . ' - ' . date('g:i A', strtotime($task['end_time']));
    $taskDate = date('F j, Y', strtotime($task['start_time']));
    
    $message = "⏰ <b>Task Reminder</b>\n";
    $message .= "📝 <b>$title</b>\n";
    $message .= "📅 Date: $taskDate\n";
    $message .= "🕐 Time: $timeRange\n";
    
    if (!empty($task['description'])) {
        $description = html_entity_decode(strip_tags($task['description']));
        $message .= "📋 Description: " . (strlen($description) > 100 ? substr($description, 0, 100) . '...' : $description) . "\n";
    }
    
    $message .= "\nStatus: " . ($task['completed'] ? '✅ Completed' : '⏳ Pending');
    
    return sendTelegramNotification($message);
}

// Send note notification
function sendNoteNotification($note, $intervalHours) {
    $title = html_entity_decode(strip_tags($note['title']));
    
    $message = "📝 <b>Note Reminder</b>\n";
    $message .= "📌 <b>$title</b>\n";
    $message .= "🕐 Interval: Every $intervalHours hours\n";
    $message .= "⏰ Time: " . date('H:i') . "\n";
    
    if (!empty($note['description'])) {
        $description = html_entity_decode(strip_tags($note['description']));
        $message .= "\n" . (strlen($description) > 200 ? substr($description, 0, 200) . '...' : $description);
    }
    
    return sendTelegramNotification($message);
}

// Initialize application data
$config = loadOrCreateConfig($configFilePath);
$authenticationMessage = '';
$filteredTasksList = [];
$historyRecords = [];
$userNotes = [];
$notificationSettings = loadData($notificationsFilePath);

// Handle POST requests with CSRF protection
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['action'])) {
    if ($_POST['action'] !== 'logout' && (!isset($_POST['csrf_token']) || !validateCSRFToken($_POST['csrf_token']))) {
        $authenticationMessage = "Security token validation failed";
    } else {
        $actionType = $_POST['action'];
        
        switch ($actionType) {
            case 'login':
                $enteredCode = trim($_POST['access_code'] ?? '');
                
                if (empty($enteredCode)) {
                    $authenticationMessage = "Please enter access code";
                } elseif ($enteredCode !== $config['access_code']) {
                    $authenticationMessage = "Invalid access code";
                } else {
                    $_SESSION['authenticated'] = true;
                    $authenticationMessage = "Login successful!";
                    header('Location: ' . $_SERVER['PHP_SELF']);
                    exit;
                }
                break;
                
            case 'change_code':
                $currentCode = trim($_POST['current_code'] ?? '');
                $newCode = trim($_POST['new_code'] ?? '');
                $confirmCode = trim($_POST['confirm_code'] ?? '');
                
                if (empty($currentCode)) {
                    $authenticationMessage = "Please enter current access code";
                } elseif ($currentCode !== $config['access_code']) {
                    $authenticationMessage = "Current access code is incorrect";
                } elseif (empty($newCode)) {
                    $authenticationMessage = "Please enter new access code";
                } elseif ($newCode !== $confirmCode) {
                    $authenticationMessage = "New access codes do not match";
                } else {
                    $config['access_code'] = $newCode;
                    if (saveData($configFilePath, $config)) {
                        $authenticationMessage = "Access code changed successfully!";
                    } else {
                        $authenticationMessage = "Error: Could not save the new access code.";
                    }
                }
                break;
                
            case 'logout':
                session_destroy();
                header('Location: ' . $_SERVER['PHP_SELF']);
                exit;
                break;
        }
    }
}

// Load data if logged in
if (isUserLoggedIn()) {
    // Load all data from JSON files
    $userTasks = loadData($tasksFilePath);
    $historyRecords = loadData($historyFilePath);
    $userNotes = loadData($notesFilePath);
    $notificationSettings = loadData($notificationsFilePath);
    
    // Ensure arrays
    if (!is_array($userTasks)) $userTasks = [];
    if (!is_array($historyRecords)) $historyRecords = [];
    if (!is_array($userNotes)) $userNotes = [];
    if (!is_array($notificationSettings)) $notificationSettings = ['hourly_report' => true];
    
    // Handle POST actions for logged-in users
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['action']) && validateCSRFToken($_POST['csrf_token'] ?? '')) {
        $actionType = $_POST['action'];
        
        switch ($actionType) {
            case 'add_task':
                $title = trim($_POST['title'] ?? '');
                $description = trim($_POST['description'] ?? '');
                $priority = intval($_POST['priority'] ?? 15);
                $repeat = $_POST['repeat'] ?? 'none';
                $notify_enabled = isset($_POST['notify_enabled']) ? true : false;
                $repeatDay = null;
                
                if ($repeat === 'weekly') {
                    $repeatDay = date('l'); // Current day name (e.g., Monday)
                }
                
                // Start date and time
                $startDate = $_POST['start_date'] ?? date('Y-m-d');
                $startTime = $_POST['start_time'] ?? date('H:i');
                $startDateTime = $startDate . ' ' . $startTime . ':00';
                
                // End date and time with validation
                $endDate = $_POST['end_date'] ?? date('Y-m-d');
                $endTime = $_POST['end_time'] ?? date('H:i', strtotime('+1 hour'));
                $endDateTime = $endDate . ' ' . $endTime . ':00';
                
                // Validate date range
                $startTimestamp = strtotime($startDateTime);
                $endTimestamp = strtotime($endDateTime);
                $dateDiff = ($endTimestamp - $startTimestamp) / (60 * 60 * 24);
                
                if ($dateDiff > 1) {
                    // If difference is more than 1 day, adjust end date
                    $endDateTime = date('Y-m-d', strtotime($startDate . ' +1 day')) . ' ' . $endTime . ':00';
                }
                
                // End of repeat date
                $repeatEndDate = !empty($_POST['repeat_end_date']) ? $_POST['repeat_end_date'] . ' 23:59:59' : null;
                
                $newTaskData = [
                    'id' => generateSecureId('task_'),
                    'title' => htmlspecialchars($title),
                    'description' => htmlspecialchars($description),
                    'bucket' => 'today',
                    'repeat' => $repeat,
                    'repeat_day' => $repeatDay,
                    'repeat_end_date' => $repeatEndDate,
                    'start_time' => $startDateTime,
                    'end_time' => $endDateTime,
                    'completed' => false,
                    'createdAt' => date('Y-m-d H:i:s'),
                    'nextOccurrence' => null,
                    'subtasks' => [],
                    'priority' => $priority,
                    'notify_enabled' => $notify_enabled,
                    'last_notified' => null
                ];
                
                if ($newTaskData['repeat'] !== 'none') {
                    $newTaskData['nextOccurrence'] = date('Y-m-d 00:00:00');
                }
                
                $userTasks[] = $newTaskData;
                saveData($tasksFilePath, $userTasks);
                
                // Send confirmation notification
                if ($notify_enabled) {
                    $notificationMessage = "✅ <b>New Task Added</b>\n";
                    $notificationMessage .= "📝 <b>$title</b>\n";
                    $notificationMessage .= "📅 Date: " . date('F j, Y', strtotime($startDate)) . "\n";
                    $notificationMessage .= "🕐 Time: " . date('g:i A', strtotime($startTime)) . "\n";
                    $notificationMessage .= "🔔 Notifications: Enabled (10 reminders before start)";
                    sendTelegramNotification($notificationMessage);
                }
                
                header('Location: ' . $_SERVER['PHP_SELF']);
                exit;
                
            case 'add_subtask':
                $parentTaskId = $_POST['task_id'] ?? '';
                
                $subtaskAdded = false;
                foreach ($userTasks as &$task) {
                    if ($task['id'] == $parentTaskId) {
                        $subtaskPriority = count($task['subtasks']) + 1;
                        $task['subtasks'][] = [
                            'id' => generateSecureId('sub_'),
                            'title' => htmlspecialchars($_POST['title'] ?? ''),
                            'description' => '',
                            'completed' => false,
                            'priority' => $subtaskPriority
                        ];
                        $subtaskAdded = true;
                        break;
                    }
                }
                
                if ($subtaskAdded) {
                    saveData($tasksFilePath, $userTasks);
                }
                header('Location: ' . $_SERVER['PHP_SELF']);
                exit;
                
            case 'complete_task':
                $taskIdToComplete = $_POST['task_id'] ?? '';
                if (completeTaskWithRepetition($taskIdToComplete, $userTasks, $historyRecords)) {
                    saveData($tasksFilePath, $userTasks);
                    saveData($historyFilePath, $historyRecords);
                    
                    // Find the completed task
                    foreach ($userTasks as $task) {
                        if ($task['id'] == $taskIdToComplete && $task['completed']) {
                            // Send completion notification
                            $notificationMessage = "✅ <b>Task Completed!</b>\n";
                            $notificationMessage .= "📝 <b>{$task['title']}</b>\n";
                            $notificationMessage .= "⏰ Time: " . date('g:i A') . "\n";
                            $notificationMessage .= "📅 Date: " . date('F j, Y');
                            sendTelegramNotification($notificationMessage);
                            break;
                        }
                    }
                }
                header('Location: ' . $_SERVER['PHP_SELF']);
                exit;
                
            case 'complete_subtask':
                $parentTaskId = $_POST['task_id'] ?? '';
                $subtaskIdToComplete = $_POST['subtask_id'] ?? '';
                
                foreach ($userTasks as &$task) {
                    if ($task['id'] == $parentTaskId) {
                        foreach ($task['subtasks'] as &$subtask) {
                            if ($subtask['id'] == $subtaskIdToComplete) {
                                $subtask['completed'] = !$subtask['completed'];
                                
                                // Check if all subtasks are completed
                                $allCompleted = true;
                                foreach ($task['subtasks'] as $st) {
                                    if (!$st['completed']) {
                                        $allCompleted = false;
                                        break;
                                    }
                                }
                                
                                // Send subtask completion notification
                                if ($subtask['completed']) {
                                    $notificationMessage = "✅ <b>Subtask Completed</b>\n";
                                    $notificationMessage .= "📝 <b>{$subtask['title']}</b>\n";
                                    $notificationMessage .= "📋 Parent Task: {$task['title']}\n";
                                    $notificationMessage .= "⏰ Time: " . date('g:i A');
                                    sendTelegramNotification($notificationMessage);
                                }
                                break;
                            }
                        }
                        break;
                    }
                }
                
                saveData($tasksFilePath, $userTasks);
                header('Location: ' . $_SERVER['PHP_SELF']);
                exit;
                
            case 'delete_task':
                $taskIdToDelete = $_POST['task_id'] ?? '';
                $userTasks = array_filter($userTasks, function($task) use ($taskIdToDelete) {
                    return $task['id'] != $taskIdToDelete;
                });
                $userTasks = array_values($userTasks);
                saveData($tasksFilePath, $userTasks);
                header('Location: ' . $_SERVER['PHP_SELF']);
                exit;
                
            case 'delete_subtask':
                $parentTaskId = $_POST['task_id'] ?? '';
                $subtaskIdToDelete = $_POST['subtask_id'] ?? '';
                
                foreach ($userTasks as &$task) {
                    if ($task['id'] == $parentTaskId) {
                        $task['subtasks'] = array_filter($task['subtasks'], function($subtask) use ($subtaskIdToDelete) {
                            return $subtask['id'] != $subtaskIdToDelete;
                        });
                        $task['subtasks'] = array_values($task['subtasks']);
                        
                        // Reorder subtask priorities
                        $subtaskNumber = 1;
                        foreach ($task['subtasks'] as &$subtask) {
                            $subtask['priority'] = $subtaskNumber;
                            $subtaskNumber++;
                        }
                        break;
                    }
                }
                
                saveData($tasksFilePath, $userTasks);
                header('Location: ' . $_SERVER['PHP_SELF']);
                exit;

            case 'update_task':
                $taskIdToUpdate = $_POST['task_id'] ?? '';
                $updateSuccessful = false;
                
                foreach ($userTasks as &$task) {
                    if ($task['id'] == $taskIdToUpdate) {
                        $oldNotify = $task['notify_enabled'] ?? false;
                        $task['title'] = htmlspecialchars($_POST['title'] ?? $task['title']);
                        $task['description'] = htmlspecialchars($_POST['description'] ?? $task['description']);
                        $task['repeat'] = $_POST['repeat'] ?? $task['repeat'];
                        $task['priority'] = intval($_POST['priority'] ?? $task['priority'] ?? 15);
                        $task['notify_enabled'] = isset($_POST['notify_enabled']) ? true : false;
                        
                        if ($task['repeat'] === 'weekly') {
                            $task['repeat_day'] = $_POST['repeat_day'] ?? date('l');
                        } else {
                            $task['repeat_day'] = null;
                        }
                        
                        $task['repeat_end_date'] = !empty($_POST['repeat_end_date']) ? $_POST['repeat_end_date'] . ' 23:59:59' : null;
                        
                        // Update start date and time
                        if (isset($_POST['start_date']) && !empty($_POST['start_date'])) {
                            $startDate = $_POST['start_date'];
                            $startTime = $_POST['start_time'] ?? date('H:i', strtotime($task['start_time']));
                            $task['start_time'] = $startDate . ' ' . $startTime . ':00';
                        }
                        
                        // Update end date and time with validation
                        if (isset($_POST['end_date']) && !empty($_POST['end_date'])) {
                            $endDate = $_POST['end_date'];
                            $endTime = $_POST['end_time'] ?? date('H:i', strtotime($task['end_time']));
                            
                            $startTimestamp = strtotime($task['start_time']);
                            $endDateTime = $endDate . ' ' . $endTime . ':00';
                            $endTimestamp = strtotime($endDateTime);
                            $dateDiff = ($endTimestamp - $startTimestamp) / (60 * 60 * 24);
                            
                            if ($dateDiff > 1) {
                                // If difference is more than 1 day, adjust end date
                                $endDate = date('Y-m-d', strtotime(date('Y-m-d', $startTimestamp) . ' +1 day'));
                                $task['end_time'] = $endDate . ' ' . $endTime . ':00';
                            } else {
                                $task['end_time'] = $endDateTime;
                            }
                        }
                        
                        if ($task['repeat'] !== 'none') {
                            $task['nextOccurrence'] = date('Y-m-d 00:00:00');
                        } else {
                            $task['nextOccurrence'] = null;
                        }
                        
                        // Send notification if notify was enabled
                        if ($task['notify_enabled'] && !$oldNotify) {
                            $notificationMessage = "🔔 <b>Notifications Enabled</b>\n";
                            $notificationMessage .= "📝 <b>{$task['title']}</b>\n";
                            $notificationMessage .= "📅 You'll receive 10 reminders before the task starts";
                            sendTelegramNotification($notificationMessage);
                        }
                        
                        $updateSuccessful = true;
                        break;
                    }
                }
                
                if ($updateSuccessful) {
                    saveData($tasksFilePath, $userTasks);
                }
                header('Location: ' . $_SERVER['PHP_SELF']);
                exit;

            case 'update_subtask':
                $parentTaskId = $_POST['task_id'] ?? '';
                $subtaskIdToUpdate = $_POST['subtask_id'] ?? '';
                $updateSuccessful = false;
                
                foreach ($userTasks as &$task) {
                    if ($task['id'] == $parentTaskId) {
                        foreach ($task['subtasks'] as &$subtask) {
                            if ($subtask['id'] == $subtaskIdToUpdate) {
                                $subtask['title'] = htmlspecialchars($_POST['title'] ?? $subtask['title']);
                                $subtask['description'] = htmlspecialchars($_POST['description'] ?? $subtask['description']);
                                $subtask['priority'] = intval($_POST['priority'] ?? $subtask['priority'] ?? 15);
                                $updateSuccessful = true;
                                break;
                            }
                        }
                        break;
                    }
                }
                
                if ($updateSuccessful) {
                    saveData($tasksFilePath, $userTasks);
                }
                header('Location: ' . $_SERVER['PHP_SELF']);
                exit;
                
            case 'add_note':
                $maxPriority = 0;
                foreach($userNotes as $note) {
                    if (($note['priority'] ?? 0) > $maxPriority) {
                        $maxPriority = $note['priority'];
                    }
                }

                $newNote = [
                    'id' => generateSecureId('note_'),
                    'title' => htmlspecialchars($_POST['title'] ?? 'Untitled Note'),
                    'description' => htmlspecialchars($_POST['description'] ?? ''),
                    'priority' => $maxPriority + 1,
                    'createdAt' => date('Y-m-d H:i:s'),
                    'updatedAt' => date('Y-m-d H:i:s'),
                    'notify_enabled' => isset($_POST['notify_enabled']) ? true : false,
                    'notify_interval' => isset($_POST['notify_interval']) ? intval($_POST['notify_interval']) : 0,
                    'last_notified' => null
                ];
                $userNotes[] = $newNote;
                saveData($notesFilePath, $userNotes);
                
                // Send notification if enabled
                if ($newNote['notify_enabled'] && $newNote['notify_interval'] > 0) {
                    $notificationMessage = "📝 <b>New Note Added</b>\n";
                    $notificationMessage .= "📌 <b>{$newNote['title']}</b>\n";
                    $notificationMessage .= "🔄 Interval: Every {$newNote['notify_interval']} hours\n";
                    $notificationMessage .= "🔔 You'll receive regular reminders";
                    sendTelegramNotification($notificationMessage);
                }
                
                header('Location: ' . $_SERVER['PHP_SELF'] . '?view=notes');
                exit;

            case 'update_note':
                $noteId = $_POST['note_id'] ?? '';
                foreach ($userNotes as &$note) {
                    if ($note['id'] === $noteId) {
                        $oldNotify = $note['notify_enabled'] ?? false;
                        $oldInterval = $note['notify_interval'] ?? 0;
                        
                        $note['title'] = htmlspecialchars($_POST['title'] ?? $note['title']);
                        $note['description'] = htmlspecialchars($_POST['description'] ?? $note['description']);
                        $note['updatedAt'] = date('Y-m-d H:i:s');
                        $note['notify_enabled'] = isset($_POST['notify_enabled']) ? true : false;
                        $note['notify_interval'] = isset($_POST['notify_interval']) ? intval($_POST['notify_interval']) : 0;
                        
                        // Send notification if notify was enabled
                        if ($note['notify_enabled'] && (!$oldNotify || $oldInterval != $note['notify_interval'])) {
                            $notificationMessage = "🔔 <b>Note Notifications Updated</b>\n";
                            $notificationMessage .= "📌 <b>{$note['title']}</b>\n";
                            $notificationMessage .= "🔄 Interval: Every {$note['notify_interval']} hours";
                            sendTelegramNotification($notificationMessage);
                        }
                        break;
                    }
                }
                saveData($notesFilePath, $userNotes);
                header('Location: ' . $_SERVER['PHP_SELF'] . '?view=notes');
                exit;

            case 'delete_note':
                $noteId = $_POST['note_id'] ?? '';
                $userNotes = array_filter($userNotes, function($note) use ($noteId) {
                    return $note['id'] !== $noteId;
                });
                $userNotes = array_values($userNotes);
                saveData($notesFilePath, $userNotes);
                header('Location: ' . $_SERVER['PHP_SELF'] . '?view=notes');
                exit;

            case 'move_note':
                $noteId = $_POST['note_id'] ?? '';
                $direction = $_POST['direction'] ?? '';
                
                usort($userNotes, function($a, $b) {
                    return ($a['priority'] ?? 0) <=> ($b['priority'] ?? 0);
                });

                $currentIndex = -1;
                foreach ($userNotes as $index => $note) {
                    if ($note['id'] === $noteId) {
                        $currentIndex = $index;
                        break;
                    }
                }

                if ($currentIndex !== -1) {
                    if ($direction === 'up' && $currentIndex > 0) {
                        // Swap priority with the item above
                        $tempPriority = $userNotes[$currentIndex - 1]['priority'];
                        $userNotes[$currentIndex - 1]['priority'] = $userNotes[$currentIndex]['priority'];
                        $userNotes[$currentIndex]['priority'] = $tempPriority;

                    } elseif ($direction === 'down' && $currentIndex < count($userNotes) - 1) {
                        // Swap priority with the item below
                        $tempPriority = $userNotes[$currentIndex + 1]['priority'];
                        $userNotes[$currentIndex + 1]['priority'] = $userNotes[$currentIndex]['priority'];
                        $userNotes[$currentIndex]['priority'] = $tempPriority;
                    }
                    saveData($notesFilePath, $userNotes);
                }
                header('Location: ' . $_SERVER['PHP_SELF'] . '?view=notes');
                exit;
                
            case 'toggle_hourly_report':
                $notificationSettings['hourly_report'] = isset($_POST['enabled']) ? true : false;
                saveData($notificationsFilePath, $notificationSettings);
                
                // Send confirmation
                if ($notificationSettings['hourly_report']) {
                    $notificationMessage = "📊 <b>Hourly Reports Enabled</b>\n";
                    $notificationMessage .= "You'll receive task status reports every hour";
                    sendTelegramNotification($notificationMessage);
                } else {
                    $notificationMessage = "📊 <b>Hourly Reports Disabled</b>\n";
                    $notificationMessage .= "Hourly task reports have been turned off";
                    sendTelegramNotification($notificationMessage);
                }
                
                header('Location: ' . $_SERVER['PHP_SELF'] . '?view=settings');
                exit;
        }
    }
    
    // Handle missed days for repeating tasks
    handleMissedDaysForRepeatingItems($userTasks, 'task');
    
    // Process tasks for display
    $processedTasksList = [];
    $currentDate = date('Y-m-d');
    
    foreach ($userTasks as $task) {
        $processedTask = $task;
        
        $currentTimestamp = time();
        $startTimestamp = strtotime($task['start_time']);
        $endTimestamp = strtotime($task['end_time']);
        $taskDate = date('Y-m-d', $startTimestamp);
        
        $processedTask['start_timestamp'] = $startTimestamp;
        $processedTask['end_timestamp'] = $endTimestamp;
        
        // Check if task is completed for today (for repeating tasks)
        $isCompletedToday = false;
        if (($task['repeat'] ?? 'none') !== 'none' && ($task['completed'] ?? false)) {
            // Check if the completed task is for today
            $completedDate = date('Y-m-d', $startTimestamp);
            $isCompletedToday = ($completedDate === $currentDate);
        }
        
        if (($task['repeat'] ?? 'none') === 'none' && $taskDate < $currentDate && !$task['completed']) {
            $processedTask['status'] = 'expired';
            $processedTask['time_display'] = 'expired';
            $processedTask['is_active'] = false;
        } else {
            // Calculate time status based on new requirements
            $currentMinutes = (int)date('H') * 60 + (int)date('i');
            $startMinutes = (int)date('H', $startTimestamp) * 60 + (int)date('i', $startTimestamp);
            $endMinutes = (int)date('H', $endTimestamp) * 60 + (int)date('i', $endTimestamp);
            
            $twoHours = 120; // 2 hours in minutes
            
            if ($currentMinutes < ($startMinutes - $twoHours)) { // More than 2 hours before start
                $processedTask['status'] = 'upcoming';
                $processedTask['time_display'] = 'upcoming';
                $processedTask['is_active'] = !$task['completed'] && !$isCompletedToday;
            } elseif ($currentMinutes >= ($startMinutes - $twoHours) && $currentMinutes < $startMinutes) { // Within 2 hours of start
                $processedTask['status'] = 'starting_soon';
                $processedTask['time_display'] = 'starting_soon';
                $processedTask['is_active'] = !$task['completed'] && !$isCompletedToday;
            } elseif ($currentMinutes >= $startMinutes && $currentMinutes <= $endMinutes) { // During task time
                $processedTask['status'] = 'active';
                $processedTask['time_display'] = 'active';
                $processedTask['is_active'] = !$task['completed'] && !$isCompletedToday;
            } elseif ($currentMinutes > $endMinutes && $currentMinutes <= ($endMinutes + $twoHours)) { // Within 2 hours after end
                $processedTask['status'] = 'due';
                $processedTask['time_display'] = 'due';
                $processedTask['is_active'] = !$task['completed'] && !$isCompletedToday;
            } else { // More than 2 hours after end
                $processedTask['status'] = 'overdue';
                $processedTask['time_display'] = 'overdue';
                $processedTask['is_active'] = !$task['completed'] && !$isCompletedToday;
            }
        }
        
        // For completed repeating tasks, show next occurrence
        if (($task['repeat'] ?? 'none') !== 'none' && ($task['completed'] ?? false)) {
            $processedTask['next_occurrence'] = calculateNextOccurrence($task['repeat'], $task['start_time'], $task['repeat_day'] ?? null);
            $processedTask['is_completed_repeating'] = true;
            $processedTask['is_active'] = false;
        } else {
            $processedTask['is_completed_repeating'] = false;
        }
        
        $processedTasksList[] = $processedTask;
    }
    
    // Filter tasks - show all tasks including completed repeating ones
    $filteredTasksList = array_filter($processedTasksList, function($task) {
        // Always show non-repeating tasks that are not completed
        if (($task['repeat'] ?? 'none') === 'none' && !$task['completed']) {
            return true;
        }
        
        // Show repeating tasks that are active today
        if (($task['repeat'] ?? 'none') !== 'none') {
            if ($task['is_completed_repeating']) {
                // Show completed repeating tasks
                return true;
            }
            return isItemActiveToday($task, 'task') && !$task['completed'];
        }
        
        return false;
    });
    
    // Sort tasks: active first, then by priority
    usort($filteredTasksList, function($a, $b) {
        // Sort by active status first (active tasks first)
        if ($a['is_active'] !== $b['is_active']) {
            return $b['is_active'] - $a['is_active'];
        }
        
        // Then by priority
        $priorityA = $a['priority'] ?? 15;
        $priorityB = $b['priority'] ?? 15;
        return $priorityA - $priorityB;
    });
    
    // Sort notes by priority
    usort($userNotes, function($a, $b) {
        return ($a['priority'] ?? 0) <=> ($b['priority'] ?? 0);
    });
}

// RENDERING FUNCTIONS
function renderTaskCard($task) {
    $repeatText = '';
    if (($task['repeat'] ?? 'none') !== 'none') {
        if ($task['repeat'] === 'daily') {
            $repeatText = 'Daily';
        } elseif ($task['repeat'] === 'weekly') {
            $day = $task['repeat_day'] ?? 'Sunday';
            $repeatText = "Weekly on {$day}";
        }
    } else {
        $repeatText = 'None';
    }
    
    $repeatBadge = "<span class='repeat-badge'><i class='fas fa-repeat'></i> {$repeatText}</span>";
    
    $priority = $task['priority'] ?? 15;
    $priorityBadge = "<span class='priority-badge'>P{$priority}</span>";
    
    $notifyBadge = "";
    if ($task['notify_enabled'] ?? false) {
        $notifyBadge = "<span class='notify-badge'><i class='fas fa-bell'></i> Notify</span>";
    }
    
    $editButton = "<button class='action-btn' onclick='openEditTaskModal(\"{$task['id']}\")' title='Edit Task'><i class='fas fa-edit'></i></button>";
    
    $addSubtaskButton = "<button class='action-btn' onclick='openAddSubtaskModal(\"{$task['id']}\")' title='Add Subtask'><i class='fas fa-plus'></i></button>";
    
    $completeButton = '';
    if ($task['is_active'] ?? true) {
        $completeButton = "
        <form method='POST' style='display:inline;'>
            <input type='hidden' name='action' value='complete_task'>
            <input type='hidden' name='task_id' value='{$task['id']}'>
            <input type='hidden' name='csrf_token' value='" . generateCSRFToken() . "'>
            <button type='submit' class='action-btn' title='Complete'>
                <i class='fas fa-check'></i>
            </button>
        </form>";
    } else {
        $completeButton = "<button class='action-btn disabled' title='Already Completed' disabled><i class='fas fa-check'></i></button>";
    }
    
    $deleteButton = "
    <form method='POST' style='display:inline;'>
        <input type='hidden' name='action' value='delete_task'>
        <input type='hidden' name='task_id' value='{$task['id']}'>
        <input type='hidden' name='csrf_token' value='" . generateCSRFToken() . "'>
        <button type='submit' class='action-btn' title='Delete'>
            <i class='fas fa-trash'></i>
        </button>
    </form>";
    
    $timeRange = date('g:i A', strtotime($task['start_time'])) . ' - ' . date('g:i A', strtotime($task['end_time']));
    $dateRange = date('M j', strtotime($task['start_time']));
    $endDate = date('M j', strtotime($task['end_time']));
    if ($dateRange !== $endDate) {
        $dateRange .= ' - ' . $endDate;
    }
    
    $startTime = $task['start_timestamp'] ?? strtotime($task['start_time']);
    $endTime = $task['end_timestamp'] ?? strtotime($task['end_time']);
    
    $completedSubtasks = count(array_filter($task['subtasks'] ?? [], function($subtask) {
        return $subtask['completed'] ?? false;
    }));
    $totalSubtasks = count($task['subtasks'] ?? []);
    $progressPercentage = $totalSubtasks > 0 ? round(($completedSubtasks / $totalSubtasks) * 100) : 0;
    
    $subtasksHtml = "";
    if (!empty($task['subtasks'])) {
        // Sort subtasks by priority
        usort($task['subtasks'], function($a, $b) {
            $priorityA = $a['priority'] ?? 15;
            $priorityB = $b['priority'] ?? 15;
            return $priorityA - $priorityB;
        });
        
        $subtasksListHtml = "";
        foreach ($task['subtasks'] as $subtask) {
            $completedClass = ($subtask['completed'] ?? false) ? 'subtask-completed' : '';
            $subtaskNumber = $subtask['priority'] ?? 1;
            
            $subtaskNumberBadge = ($subtask['completed'] ?? false) 
                ? "<span class='subtask-number-badge completed'>{$subtaskNumber}</span>"
                : "<span class='subtask-number-badge'>{$subtaskNumber}</span>";

            $subtaskEditButton = "<button class='edit-subtask-btn' onclick='openEditSubtaskModal(\"{$task['id']}\", \"{$subtask['id']}\")' title='Edit Subtask'><i class='fas fa-edit'></i></button>";
            
            $subtaskDeleteButton = "
            <form method='POST' style='display:inline;'>
                <input type='hidden' name='action' value='delete_subtask'>
                <input type='hidden' name='task_id' value='{$task['id']}'>
                <input type='hidden' name='subtask_id' value='{$subtask['id']}'>
                <input type='hidden' name='csrf_token' value='" . generateCSRFToken() . "'>
                <button type='submit' class='delete-subtask-btn' title='Delete Subtask'>
                    <i class='fas fa-trash'></i>
                </button>
            </form>";
            
            $subtaskDescription = !empty($subtask['description']) ? 
                "<div class='subtask-description'>" . formatText($subtask['description']) . "</div>" : "";

            $completeForm = "
            <form method='POST' style='display:inline;'>
                <input type='hidden' name='action' value='complete_subtask'>
                <input type='hidden' name='task_id' value='{$task['id']}'>
                <input type='hidden' name='subtask_id' value='{$subtask['id']}'>
                <input type='hidden' name='csrf_token' value='" . generateCSRFToken() . "'>
                <button type='submit' class='subtask-complete-btn' title='Toggle Complete'>
                    {$subtaskNumberBadge}
                </button>
            </form>";
            
            $subtasksListHtml .= "
            <div class='subtask-item'>
                {$completeForm}
                <details class='subtask-details-container'>
                    <summary class='subtask-title $completedClass'>{$subtask['title']}</summary>
                    {$subtaskDescription}
                </details>
                <div class='subtask-actions'>
                    {$subtaskEditButton}
                    {$subtaskDeleteButton}
                </div>
            </div>";
        }
        
        $subtasksHtml = "
        <details class='subtasks-details'>
            <summary>
                <i class='fas fa-tasks'></i>
                Subtasks ({$completedSubtasks}/{$totalSubtasks})
                <span class='details-toggle'></span>
            </summary>
            <div class='subtasks-content'>
                {$subtasksListHtml}
            </div>
        </details>";
    }
    
    $progressHtml = "";
    if ($totalSubtasks > 0) {
        $progressHtml = "
        <div class='progress-display-container'>
            <div class='progress-circle' style='background: conic-gradient(var(--primary) {$progressPercentage}%, var(--gray-light) 0%);'>
                <span style='font-size: 0.65rem; z-index: 1;'>{$progressPercentage}%</span>
            </div>
            <div class='progress-text' style='margin-left: 8px; flex: 1;'>
                {$completedSubtasks} of {$totalSubtasks} subtasks completed
            </div>
        </div>";
    }
    
    $description = formatText($task['description'] ?? '');
    
    // Check if this is a completed repeating task
    $isCompletedRepeating = $task['is_completed_repeating'] ?? false;
    $cardClass = $isCompletedRepeating ? 'completed-repeating' : '';
    $nextOccurrenceHtml = '';
    
    if ($isCompletedRepeating && isset($task['next_occurrence'])) {
        $nextDate = date('M j, Y', strtotime($task['next_occurrence']));
        $nextDay = date('l', strtotime($task['next_occurrence']));
        $nextTime = date('g:i A', strtotime($task['start_time'])) . ' - ' . date('g:i A', strtotime($task['end_time']));
        $nextOccurrenceHtml = "
        <div class='next-occurrence-info'>
            <i class='fas fa-calendar-alt'></i>
            Next: {$nextDate} ({$nextDay}) at {$nextTime}
        </div>";
    }
    
    return "
    <div class='task-card consistent-card {$cardClass}'>
        <div class='task-header'>
            <div style='flex: 1;'>
                <div style='display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;'>
                    <h3 class='task-title'>{$task['title']}</h3>
                    <div class='task-actions'>
                        {$addSubtaskButton}
                        {$editButton}
                        {$completeButton}
                        {$deleteButton}
                    </div>
                </div>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <div>
                        <span class='task-date-range'>{$dateRange}</span>
                        <span class='task-time-range'>{$timeRange}</span>
                    </div>
                    <div class='task-time-display' 
                         data-start-time='{$startTime}' 
                         data-end-time='{$endTime}'
                         data-status='{$task['status']}'
                         data-time-display='{$task['time_display']}'
                         data-is-active='" . ($task['is_active'] ?? true ? 'true' : 'false') . "'></div>
                </div>
            </div>
        </div>
        " . (!empty($description) ? "<p class='task-description'>{$description}</p>" : "") . "
        
        " . ($nextOccurrenceHtml) . "
        
        " . ($progressHtml ? $progressHtml : "") . "
        
        " . ($subtasksHtml ? $subtasksHtml : "") . "
        
        <div class='task-meta'>
            {$repeatBadge}
            {$priorityBadge}
            {$notifyBadge}
        </div>
    </div>";
}

function renderHistoryCard($item) {
    $completionDetails = date('F j, Y, g:i A', strtotime($item['completedAt'] ?? 'now'));
    $description = !empty($item['description']) ? formatText($item['description']) : '';
    $icon = 'fas fa-tasks';
    
    $subitemsHtml = "";
    if (isset($item['subtasks']) && !empty($item['subtasks'])) {
        $subitemsHtml .= "<div class='history-subitems'>";
        foreach ($item['subtasks'] as $subtask) {
             $subtaskDescription = !empty($subtask['description']) ? 
                "<div class='history-stage-description'>" . formatText($subtask['description']) . "</div>" : "";
            $subitemsHtml .= "
            <div class='history-stage-item'>
                <div class='history-stage-header'>
                     <span class='history-stage-title'>{$subtask['title']}</span>
                </div>
               {$subtaskDescription}
            </div>";
        }
        $subitemsHtml .= "</div>";
    }
    
    return "
    <div class='history-card'>
        <div class='history-card-header'>
            <div class='history-card-title'>
                <i class='{$icon}'></i>
                {$item['title']}
            </div>
            <div class='history-card-time'>{$completionDetails}</div>
        </div>
        " . (!empty($description) ? "<div class='history-card-description'>{$description}</div>" : "") . "
        <div class='history-card-meta'>
            " . (isset($item['bucket']) ? "<span class='history-meta-item'>Bucket: " . ucfirst($item['bucket']) . "</span>" : "") . "
            " . (isset($item['repeat']) ? "<span class='history-meta-item'>Repeat: " . ($item['repeat'] === 'none' ? 'No' : ucfirst($item['repeat'])) . "</span>" : "") . "
            " . (isset($item['time_range']) ? "<span class='history-meta-item'>Time: {$item['time_range']}</span>" : "") . "
            " . (isset($item['priority']) ? "<span class='history-meta-item'>Priority: P{$item['priority']}</span>" : "") . "
        </div>
        {$subitemsHtml}
    </div>";
}

function renderNoteCard($note) {
    $noteId = $note['id'];
    $csrfToken = generateCSRFToken();
    
    $createdAt = date('M j, Y', strtotime($note['createdAt'] ?? 'now'));
    $updatedAt = date('M j, Y', strtotime($note['updatedAt'] ?? $note['createdAt'] ?? 'now'));
    
    $notifyBadge = "";
    if ($note['notify_enabled'] ?? false) {
        $interval = $note['notify_interval'] ?? 0;
        $notifyBadge = "<span class='notify-badge'><i class='fas fa-bell'></i> Every {$interval}h</span>";
    }
    
    $editButton = "<button class='note-action-btn' onclick='openEditNoteModal(\"{$noteId}\")' title='Edit Note'><i class='fas fa-edit'></i></button>";

    $deleteButton = "
    <form method='POST' style='display:inline;'>
        <input type='hidden' name='action' value='delete_note'>
        <input type='hidden' name='note_id' value='{$noteId}'>
        <input type='hidden' name='csrf_token' value='{$csrfToken}'>
        <button type='submit' class='note-action-btn delete' title='Delete Note'>
            <i class='fas fa-trash'></i>
        </button>
    </form>";

    $moveUpButton = "
    <form method='POST' style='display:inline;'>
        <input type='hidden' name='action' value='move_note'>
        <input type='hidden' name='direction' value='up'>
        <input type='hidden' name='note_id' value='{$noteId}'>
        <input type='hidden' name='csrf_token' value='{$csrfToken}'>
        <button type='submit' class='note-move-btn' title='Move Up' style='margin-left: 6px;'>
            <i class='fas fa-arrow-up'></i>
        </button>
    </form>";

    $moveDownButton = "
    <form method='POST' style='display:inline;'>
        <input type='hidden' name='action' value='move_note'>
        <input type='hidden' name='direction' value='down'>
        <input type='hidden' name='note_id' value='{$noteId}'>
        <input type='hidden' name='csrf_token' value='{$csrfToken}'>
        <button type='submit' class='note-move-btn' title='Move Down'>
            <i class='fas fa-arrow-down'></i>
        </button>
    </form>";

    $description = !empty($note['description']) 
        ? "<div class='note-description'>" . formatText($note['description']) . "</div>" 
        : "";

    return "
    <div class='note-card'>
        <details class='note-details'>
            <summary class='note-summary'>
                <div class='note-header'>
                    <h3 class='note-title'>{$note['title']}</h3>
                    <div class='note-date'>Updated: {$updatedAt}</div>
                </div>
            </summary>
            <div class='note-content'>
                {$description}
                <div class='note-footer'>
                    <div class='note-meta'>
                        <span class='note-date-badge'>Created: {$createdAt}</span>
                        {$notifyBadge}
                    </div>
                    <div class='note-actions'>
                        {$moveDownButton}
                        {$moveUpButton}
                        {$editButton}
                        {$deleteButton}
                    </div>
                </div>
            </div>
        </details>
    </div>";
}

$currentView = $_GET['view'] ?? 'tasks';
?>

<!DOCTYPE html>
<html lang="en" id="theme-element">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Task Tracker</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --primary: #4361ee; --primary-light: #4895ef; --secondary: #3f37c9; --success: #4cc9f0; --danger: #f72585; --warning: #f8961e; --info: #4895ef; --light: #f8f9fa; --dark: #212529; --gray: #6c757d; --gray-light: #adb5bd; --border-radius: 12px; --shadow: 0 4px 6px rgba(0, 0, 0, 0.1); --transition: all 0.3s ease;
            --pink-bg: rgba(255, 182, 193, 0.1); --blue-bg: rgba(173, 216, 230, 0.15); --blue-bg-hover: rgba(173, 216, 230, 0.25);
            --note-bg: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            --note-shadow: 0 8px 32px rgba(31, 38, 135, 0.1);
            --completed-bg: rgba(108, 117, 125, 0.1);
            --completed-text: #6c757d;
            --notify-bg: rgba(248, 150, 30, 0.1);
            --notify-color: #f8961e;
        }
        
        @media (prefers-color-scheme: dark) {
            :root {
                --primary: #5a6ff0; --primary-light: #6a80f2; --secondary: #4f46e5; --success: #5fd3f0; --danger: #ff2d8e; --warning: #ffa94d; --info: #6a80f2; --light: #121212; --dark: #ffffff; --gray: #94a3b8; --gray-light: #475569; --shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
                --pink-bg: rgba(255, 182, 193, 0.05); --blue-bg: rgba(173, 216, 230, 0.08); --blue-bg-hover: rgba(173, 216, 230, 0.15);
                --note-bg: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                --note-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                --completed-bg: rgba(108, 117, 125, 0.2);
                --completed-text: #94a3b8;
                --notify-bg: rgba(248, 150, 30, 0.2);
                --notify-color: #ffa94d;
            }
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background-color: var(--light); color: var(--dark); transition: var(--transition); min-height: 100vh; display: flex; flex-direction: column; font-size: 14px; }
        
        /* Header Styles */
        .header { 
            background-color: var(--light); 
            padding: 8px 16px; 
            display: flex; 
            align-items: center; 
            justify-content: space-around; 
            box-shadow: var(--shadow); 
            position: sticky; 
            top: 0; 
            z-index: 100; 
            gap: 8px;
            flex-wrap: wrap;
        }
        
        .header-action-btn {
            display: flex;
            flex-direction: row;
            align-items: center;
            justify-content: center;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 20px;
            padding: 8px 16px;
            cursor: pointer;
            transition: var(--transition);
            box-shadow: var(--shadow);
            gap: 8px;
            flex: 1;
            max-width: 120px;
            margin: 0 4px;
        }
        
        .header-action-btn i { font-size: 1rem; }
        .header-action-btn span { font-size: 0.8rem; font-weight: 600; }
        .header-action-btn:hover { background: var(--primary-light); transform: translateY(-2px); }
        .header-action-btn:active, .action-btn:active, .btn:active, button:active { transform: none !important; box-shadow: var(--shadow) !important; }
        
        .settings-btn {
            position: absolute;
            right: 16px;
            top: 50%;
            transform: translateY(-50%);
            background: var(--info);
            color: white;
            border: none;
            border-radius: 50%;
            width: 36px;
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }

        @media (max-width: 768px) {
            .header { padding: 8px; gap: 4px; }
            .header-action-btn { 
                width: 100%;
                max-width: none;
                padding: 10px;
                margin: 2px;
                border-radius: 12px;
            }
            .header-action-btn span { display: block; font-size: 0.75rem; }
            .header-action-btn i { margin-right: 4px; font-size: 0.9rem; }
            .settings-btn { position: static; margin-left: auto; }
        }

        /* Floating Action Buttons */
        .fab {
            position: fixed;
            width: 60px;
            height: 60px;
            background-color: var(--primary);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            cursor: pointer;
            transition: var(--transition);
            z-index: 1000;
            border: none;
        }
        
        .fab:hover {
            background-color: var(--primary-light);
            transform: scale(1.1);
            box-shadow: 0 6px 16px rgba(0, 0, 0, 0.3);
        }
        
        .fab-tasks {
            bottom: 30px;
            right: 30px;
        }
        
        .fab-notes {
            bottom: 30px;
            right: 30px;
        }
        
        @media (max-width: 768px) {
            .fab {
                width: 50px;
                height: 50px;
                font-size: 1.3rem;
            }
            
            .fab-tasks {
                bottom: 20px;
                right: 20px;
            }
            
            .fab-notes {
                bottom: 20px;
                right: 20px;
            }
        }

        .login-container { display: flex; justify-content: center; align-items: center; min-height: 80vh; padding: 20px; }
        .auth-section { background-color: var(--light); padding: 30px; border-radius: var(--border-radius); box-shadow: var(--shadow); border-bottom: 4px solid var(--danger); width: 100%; max-width: 400px; }
        .auth-container { margin: 0 auto; }
        .auth-message { padding: 10px; margin-bottom: 15px; border-radius: 6px; text-align: center; font-weight: 600; }
        .auth-message.success { background-color: rgba(76, 201, 240, 0.2); color: var(--success); border: 1px solid var(--success); }
        .auth-message.error { background-color: rgba(247, 37, 133, 0.2); color: var(--danger); border: 1px solid var(--danger); }
        .tab-buttons { display: flex; margin-bottom: 20px; border-bottom: 1px solid var(--gray-light); }
        .tab-button { flex: 1; padding: 12px; background: none; border: none; cursor: pointer; font-weight: 600; color: var(--gray); transition: var(--transition); border-bottom: 3px solid transparent; }
        .tab-button.active { color: var(--primary); border-bottom: 3px solid var(--primary); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        .main-content { flex-grow: 1; padding: 16px; overflow-y: auto; padding-bottom: 100px; }
        .view-content { display: none; }
        .view-content.active { display: block; animation: fadeIn 0.5s ease; }
        .content-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
        .page-title { font-size: 1.5rem; font-weight: 700; color: var(--dark); }
        
        .bucket-header { display: flex; align-items: center; margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--gray-light); flex-wrap: wrap; gap: 10px;}
        .bucket-title { font-size: 1.2rem; font-weight: 600; color: var(--dark); display: flex; align-items: center; gap: 8px; }
        .bucket-count { background-color: var(--primary); color: white; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-size: 0.8rem; }
        
        .items-container { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; width: 100%; }
        @media (max-width: 1200px) { .items-container { grid-template-columns: repeat(2, 1fr) !important; } }
        @media (max-width: 768px) { .items-container { grid-template-columns: 1fr !important; } }
        
        .task-card { 
            background-color: var(--pink-bg); 
            border-radius: var(--border-radius); 
            padding: 16px; 
            box-shadow: var(--shadow); 
            transition: var(--transition); 
            animation: slideIn 0.3s ease; 
            display: flex; 
            flex-direction: column; 
            min-height: 140px;
            position: relative;
        }
        
        .task-card.completed-repeating {
            background-color: var(--completed-bg);
            opacity: 0.8;
        }
        
        .task-card.completed-repeating .task-title,
        .task-card.completed-repeating .task-description,
        .task-card.completed-repeating .task-date-range,
        .task-card.completed-repeating .task-time-range,
        .task-card.completed-repeating .repeat-badge,
        .task-card.completed-repeating .priority-badge {
            color: var(--completed-text);
        }
        
        .task-card.completed-repeating .action-btn {
            background-color: var(--completed-text);
        }
        
        .task-card.completed-repeating .action-btn:hover {
            background-color: var(--completed-text);
            transform: scale(1);
        }
        
        .notify-badge {
            background-color: var(--notify-bg);
            color: var(--notify-color);
            padding: 2px 8px;
            border-radius: 20px;
            font-size: 0.65rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        
        .next-occurrence-info {
            background-color: rgba(67, 97, 238, 0.1);
            border-radius: 8px;
            padding: 8px 12px;
            margin-bottom: 12px;
            font-size: 0.75rem;
            color: var(--primary);
            display: flex;
            align-items: center;
            gap: 8px;
            border-left: 3px solid var(--primary);
        }
        
        .next-occurrence-info i {
            font-size: 0.9rem;
        }
        
        @media (prefers-color-scheme: dark) {
            .task-card {
                box-shadow: rgba(255, 255, 255, 0.05) 0px -23px 25px 0px inset, rgba(255, 255, 255, 0.04) 0px -36px 30px 0px inset, rgba(255, 255, 255, 0.03) 0px -79px 40px 0px inset, rgba(255, 255, 255, 0.02) 0px 2px 1px, rgba(255, 255, 255, 0.02) 0px 4px 2px, rgba(255, 255, 255, 0.02) 0px 8px 4px, rgba(255, 255, 255, 0.02) 0px 16px 8px, rgba(255, 255, 255, 0.02) 0px 32px 16px;
            }
        }
        
        .task-card:hover { transform: translateY(-5px); box-shadow: 0 10px 15px rgba(0, 0, 0, 0.1); }
        
        .task-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 8px; }
        .task-title { font-size: 1rem !important; font-weight: 600; color: var(--dark); margin-bottom: 4px; line-height: 1.4 !important; }
        .task-description { font-size: 0.8rem !important; color: var(--gray); margin-bottom: 12px; line-height: 1.4 !important; flex-grow: 1; }
        .task-description:empty { display: none !important; margin-bottom: 0 !important; }
        
        .task-actions { display: flex; gap: 8px; }
        .action-btn { background-color: var(--primary); color: white; border: none; border-radius: 50%; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: var(--transition); font-size: 0.8rem; }
        .action-btn:hover { background-color: var(--primary); transform: scale(1.1); }
        
        .action-btn.disabled {
            background-color: var(--gray-light);
            cursor: not-allowed;
            opacity: 0.6;
        }
        
        .action-btn.disabled:hover {
            transform: none;
            background-color: var(--gray-light);
        }
        
        .task-meta { display: flex; align-items: center; justify-content: space-between; font-size: 0.75rem; color: var(--gray); margin-top: auto; padding-top: 12px; }
        .repeat-badge { background-color: rgba(67, 97, 238, 0.1); color: var(--primary); padding: 2px 8px; border-radius: 20px; font-size: 0.65rem; font-weight: 600; display: flex; align-items: center; gap: 4px; }
        .priority-badge { background-color: rgba(108, 117, 125, 0.2); color: var(--gray); padding: 2px 8px; border-radius: 20px; font-size: 0.65rem; font-weight: 600; display: flex; align-items: center; gap: 4px; }
        
        .task-date-range { font-size: 0.75rem; color: var(--gray); margin-right: 8px; }
        .task-time-range { font-size: 0.75rem; color: var(--gray); font-weight: 500; }
        
        .subtask-number-badge { width: 22px; height: 22px; border-radius: 50%; background-color: var(--gray-light); color: var(--dark); display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: bold; transition: var(--transition); }
        .subtask-number-badge.completed { background-color: var(--primary); color: white; }
        .subtask-complete-btn { background: none; border: none; cursor: pointer; padding: 0; margin-right: 8px;}
        .edit-subtask-btn, .delete-subtask-btn { background: none; border: none; color: var(--primary); cursor: pointer; font-size: 0.7rem; opacity: 0.7; transition: var(--transition); padding: 2px 4px; }
        .edit-subtask-btn:hover, .delete-subtask-btn:hover { opacity: 1; transform: scale(1.1); }
        .delete-subtask-btn { color: var(--danger); }

        .subtasks-details { margin-top: 12px; border-top: 1px solid var(--gray-light); padding-top: 12px; }
        .subtasks-details summary { cursor: pointer; display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 0.85rem; color: var(--primary); padding: 4px 0; transition: var(--transition); }
        .subtasks-details summary:hover { color: var(--primary-light); }
        .details-toggle { margin-left: auto; transition: var(--transition); }
        .subtasks-details[open] .details-toggle { transform: rotate(90deg); }
        .subtasks-content { margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(0,0,0,0.05); }
        @media (prefers-color-scheme: dark) {
            .subtasks-content { border-top-color: rgba(255,255,255,0.05); }
        }
        .subtask-item { display: flex; align-items: flex-start; margin-bottom: 8px; padding: 8px; background: rgba(0,0,0,0.03); border-radius: 6px; }
        @media (prefers-color-scheme: dark) {
            .subtask-item { background: rgba(255,255,255,0.05); }
        }
        .subtask-details-container { flex: 1; margin-right: 8px;}
        .subtask-title { font-size: 0.85rem; color: var(--dark); cursor: pointer; }
        .subtask-completed { text-decoration: line-through; color: var(--gray); }
        .subtask-description { font-size: 0.75rem; color: var(--gray); margin-top: 4px; padding-left: 8px; border-left: 2px solid var(--primary-light); line-height: 1.4; }
        .subtask-actions { display: flex; align-items: center; margin-left: auto; }
        
        .progress-display-container { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
        .progress-bar-container { flex: 1; background: var(--gray-light); border-radius: 20px; height: 10px; overflow: hidden; }
        .progress-bar-fill { height: 100%; background: var(--primary); transition: width 0.3s ease; }
        .progress-circle { width: 36px; height: 36px; border-radius: 50%; background: conic-gradient(var(--primary) 0%, var(--gray-light) 0%); display: flex; align-items: center; justify-content: center; position: relative; flex-shrink: 0; }
        .progress-circle::before { content: ''; position: absolute; width: 26px; height: 26px; background-color: var(--light); border-radius: 50%; }
        .progress-text { font-size: 0.75rem; color: var(--gray); }
        
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.5); z-index: 1000; align-items: center; justify-content: center; animation: fadeIn 0.3s ease; }
        .modal-content { background-color: var(--light); border-radius: var(--border-radius); width: 90%; max-width: 500px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2); animation: scaleIn 0.3s ease; overflow: hidden; max-height: 90vh; overflow-y: auto; }
        .modal-header { padding: 16px; border-bottom: 1px solid var(--gray-light); display: flex; align-items: center; justify-content: space-between; }
        .modal-title { font-size: 1.2rem; font-weight: 600; color: var(--dark); }
        .close-modal { background: none; border: none; font-size: 1.3rem; color: var(--gray); cursor: pointer; transition: var(--transition); }
        .close-modal:hover { color: var(--danger); }
        .modal-body { padding: 16px; }
        .form-group { margin-bottom: 12px; }
        .form-label { display: block; margin-bottom: 4px; font-weight: 600; color: var(--dark); font-size: 0.9rem; }
        .form-input, .form-select, .form-textarea { width: 100%; padding: 8px; border: 1px solid var(--gray-light); border-radius: 6px; background-color: var(--light); color: var(--dark); transition: var(--transition); font-size: 0.9rem; }
        .form-input:focus, .form-select:focus, .form-textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2); }
        .form-textarea { min-height: 80px; resize: vertical; line-height: 1.4; }
        .form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
        .btn { padding: 8px 16px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; transition: var(--transition); font-size: 0.9rem; }
        .btn-primary { background-color: var(--primary); color: white; }
        .btn-primary:hover { background-color: var(--secondary); }
        .btn-secondary { background-color: var(--gray-light); color: white; }
        .btn-secondary:hover { background-color: var(--gray); }
        .time-input-group { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
        .date-input-group { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
        
        .checkbox-group { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
        .checkbox-label { font-weight: 500; color: var(--dark); }
        .form-checkbox { width: 18px; height: 18px; }
        
        /* History styles */
        .history-date-details { margin-bottom: 15px; }
        .history-date-summary { padding: 12px 16px; background-color: var(--blue-bg); border-radius: var(--border-radius); cursor: pointer; font-weight: 600; display: flex; align-items: center; gap: 10px; transition: var(--transition); border: 1px solid transparent; }
        .history-date-summary:hover { background-color: var(--blue-bg-hover); border-color: var(--primary-light); }
        .history-date-content { padding: 10px 0 0 15px; }
        .history-items-container { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; margin: 10px 0; }
        .history-card { background-color: var(--blue-bg); border-radius: var(--border-radius); padding: 16px; box-shadow: var(--shadow); transition: var(--transition); border: 1px solid rgba(0,0,0,0.05); border-left: 4px solid var(--success); }
        .history-card:hover { transform: translateY(-3px); box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15); }
        .history-card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
        .history-card-title { font-weight: 600; color: var(--dark); font-size: 0.8rem; display: flex; align-items: center; gap: 8px; flex: 1; }
        .history-card-title i { color: var(--primary); font-size: 0.9rem; }
        .history-card-time { font-size: 0.75rem; color: var(--gray); background: rgba(0,0,0,0.05); padding: 3px 8px; border-radius: 12px; white-space: nowrap; margin-left: 10px; }
        .history-card-description { font-size: 0.8rem; color: var(--gray); margin-bottom: 12px; line-height: 1.4; }
        .history-card-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
        .history-meta-item { background: rgba(0,0,0,0.05); color: var(--gray); padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 500; }
        .history-subitems { margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(0,0,0,0.1); }
        .history-stage-item { font-size: 0.8rem; color: var(--gray); margin-bottom: 8px; padding: 8px; background: rgba(0,0,0,0.03); border-radius: 6px; }
        .history-stage-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
        .history-stage-title { font-weight: 600; color: var(--dark); flex: 1; }
        .history-stage-description { font-size: 0.75rem; color: var(--gray); margin-top: 4px; padding-left: 8px; border-left: 2px solid var(--success); line-height: 1.4; }
        
        @media (prefers-color-scheme: dark) {
            .history-card { background-color: rgba(173, 216, 230, 0.08); border: 1px solid rgba(255,255,255,0.05); }
            .history-card-time, .history-meta-item { background: rgba(255,255,255,0.1); }
            .history-subitems { border-top-color: rgba(255,255,255,0.1); }
            .history-stage-item { background: rgba(255,255,255,0.05); }
        }
        
        /* Notes Styles */
        .notes-container { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
        .note-card {
            background: var(--note-bg);
            border-radius: var(--border-radius);
            padding: 0;
            box-shadow: var(--note-shadow);
            transition: var(--transition);
            border: 1px solid rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
        }
        
        .note-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15);
        }
        
        .note-details {
            width: 100%;
        }
        
        .note-summary {
            list-style: none;
            padding: 20px;
            cursor: pointer;
        }
        
        .note-summary::-webkit-details-marker {
            display: none;
        }
        
        .note-header {
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }
        
        .note-title {
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--dark);
            margin-bottom: 4px;
            line-height: 1.3;
        }
        
        .note-date {
            font-size: 0.75rem;
            color: var(--gray);
            font-weight: 500;
        }
        
        .note-content {
            padding: 0 20px 20px 20px;
        }
        
        .note-description {
            font-size: 0.9rem;
            color: var(--dark);
            line-height: 1.5;
            margin-bottom: 16px;
        }
        
        .note-description strong {
            font-weight: 700;
            color: var(--primary);
        }
        
        .note-description em {
            font-style: italic;
            color: var(--secondary);
        }
        
        .note-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: auto;
            padding-top: 12px;
            border-top: 1px solid rgba(0,0,0,0.05);
        }
        
        @media (prefers-color-scheme: dark) {
            .note-footer {
                border-top-color: rgba(255,255,255,0.05);
            }
        }
        
        .note-meta {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .note-date-badge {
            background: rgba(67, 97, 238, 0.1);
            color: var(--primary);
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.7rem;
            font-weight: 500;
        }
        
        .note-actions {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .note-action-btn, .note-move-btn {
            background: none;
            border: none;
            color: var(--primary);
            cursor: pointer;
            font-size: 0.9rem;
            transition: var(--transition);
            opacity: 0.7;
            padding: 4px;
            border-radius: 4px;
        }
        
        .note-action-btn:hover, .note-move-btn:hover {
            opacity: 1;
            transform: scale(1.1);
            background: rgba(67, 97, 238, 0.1);
        }
        
        .note-action-btn.delete {
            color: var(--danger);
        }
        
        .note-action-btn.delete:hover {
            background: rgba(247, 37, 133, 0.1);
        }
        
        /* Settings View */
        .settings-card {
            background: var(--blue-bg);
            border-radius: var(--border-radius);
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
        }
        
        .settings-title {
            font-size: 1.2rem;
            font-weight: 600;
            color: var(--dark);
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .settings-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid rgba(0,0,0,0.1);
        }
        
        .settings-item:last-child {
            border-bottom: none;
        }
        
        .settings-label {
            font-weight: 500;
            color: var(--dark);
        }
        
        .toggle-switch {
            position: relative;
            display: inline-block;
            width: 50px;
            height: 24px;
        }
        
        .toggle-switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        
        .toggle-slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: var(--gray-light);
            transition: .4s;
            border-radius: 24px;
        }
        
        .toggle-slider:before {
            position: absolute;
            content: "";
            height: 16px;
            width: 16px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }
        
        input:checked + .toggle-slider {
            background-color: var(--success);
        }
        
        input:checked + .toggle-slider:before {
            transform: translateX(26px);
        }
        
        .empty-state { text-align: center; padding: 32px 16px; color: var(--gray); }
        .empty-state i { font-size: 2.5rem; margin-bottom: 12px; opacity: 0.5; }
        
        .time-remaining-badge { background-color: rgba(67, 97, 238, 0.1); color: var(--primary); padding: 4px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: 600; }
        .time-remaining-badge.upcoming { background-color: rgba(108, 117, 125, 0.2); color: var(--gray); }
        .time-remaining-badge.starting_soon { background-color: rgba(248, 150, 30, 0.1); color: var(--warning); }
        .time-remaining-badge.active { background-color: rgba(76, 201, 240, 0.2); color: var(--success); }
        .time-remaining-badge.due { background-color: rgba(248, 150, 30, 0.1); color: var(--warning); }
        .time-remaining-badge.overdue { background-color: rgba(247, 37, 133, 0.1); color: var(--danger); }
        .time-remaining-badge.expired { background-color: rgba(108, 117, 125, 0.2); color: var(--gray); }
        
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes scaleIn { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }
        @keyframes slideIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        
        @media (max-width: 768px) {
            .history-items-container { grid-template-columns: 1fr; }
            .notes-container { grid-template-columns: 1fr; }
            .task-description, .history-card-description { font-size: 0.75rem; }
            .task-card { min-height: 120px !important; }
        }
    </style>
</head>
<body>
    <div class="header">
        <?php if (isUserLoggedIn()): ?>
            <button class="header-action-btn" onclick="switchView('tasks')" title="Tasks">
                <i class="fas fa-tasks"></i>
                <span>Tasks</span>
            </button>
            <button class="header-action-btn" onclick="switchView('notes')" title="Notes">
                <i class="fas fa-wand-magic-sparkles"></i>
                <span>Notes</span>
            </button>
            <button class="header-action-btn" onclick="switchView('history')" title="History">
                <i class="fas fa-history"></i>
                <span>History</span>
            </button>
            <button class="settings-btn" onclick="switchView('settings')" title="Settings">
                <i class="fas fa-cog"></i>
            </button>
        <?php endif; ?>
    </div>

    <?php if (isUserLoggedIn()): ?>
        <!-- Show FAB based on current view -->
        <div id="fabContainer">
            <?php if ($currentView === 'tasks'): ?>
                <button class="fab fab-tasks" onclick="openAddTaskModal()" title="Add Task">
                    <i class="fas fa-plus"></i>
                </button>
            <?php elseif ($currentView === 'notes'): ?>
                <button class="fab fab-notes" onclick="openAddNoteModal()" title="Add Note">
                    <i class="fas fa-plus"></i>
                </button>
            <?php endif; ?>
        </div>
    <?php endif; ?>

    <?php if (!isUserLoggedIn()): ?>
    <div class="login-container">
        <div class="auth-section">
            <div class="auth-container">
                <?php if ($authenticationMessage): ?>
                    <div class="auth-message <?php echo strpos($authenticationMessage, 'successful') !== false || strpos($authenticationMessage, 'changed') !== false ? 'success' : 'error'; ?>">
                        <?php echo $authenticationMessage; ?>
                    </div>
                <?php endif; ?>
                
                <div class="tab-buttons">
                    <button class="tab-button active" onclick="switchTab('login')">Login</button>
                    <button class="tab-button" onclick="switchTab('changeCode')">Change Code</button>
                </div>
                
                <div class="tab-content active" id="loginTab">
                    <form method="POST" class="auth-form">
                        <input type="hidden" name="action" value="login">
                        <input type="hidden" name="csrf_token" value="<?php echo generateCSRFToken(); ?>">
                        <div class="form-group">
                            <label class="form-label">Access Code</label>
                            <input type="password" class="form-input" name="access_code" required placeholder="Enter access code">
                        </div>
                        <div class="form-actions">
                            <button type="submit" class="btn btn-primary">Access System</button>
                        </div>
                    </form>
                </div>
                
                <div class="tab-content" id="changeCodeTab">
                    <form method="POST" class="auth-form">
                        <input type="hidden" name="action" value="change_code">
                        <input type="hidden" name="csrf_token" value="<?php echo generateCSRFToken(); ?>">
                        <div class="form-group">
                            <label class="form-label">Current Access Code</label>
                            <input type="password" class="form-input" name="current_code" required placeholder="Enter current code">
                        </div>
                        <div class="form-group">
                            <label class="form-label">New Access Code</label>
                            <input type="password" class="form-input" name="new_code" required placeholder="Enter new code">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Confirm New Code</label>
                            <input type="password" class="form-input" name="confirm_code" required placeholder="Confirm new code">
                        </div>
                        <div class="form-actions">
                            <button type="submit" class="btn btn-primary">Change Access Code</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
    <?php else: ?>
    <div class="main-content">
        <!-- Tasks View -->
        <div class="view-content <?php echo $currentView === 'tasks' ? 'active' : ''; ?>" id="tasksView">
            <div class="content-header">
                <h1 class="page-title">Tasks</h1>
            </div>
            
            <div class="bucket-header">
                <h2 class="bucket-title">
                    <i class="fas fa-tasks"></i>
                    Active Tasks
                    <span class="bucket-count"><?php echo count(array_filter($filteredTasksList, function($task) { return $task['is_active'] ?? true; })); ?></span>
                </h2>
            </div>
            
            <div class="items-container">
                <?php
                $activeTasks = array_filter($filteredTasksList, function($task) { return $task['is_active'] ?? true; });
                $completedRepeatingTasks = array_filter($filteredTasksList, function($task) { return $task['is_completed_repeating'] ?? false; });
                
                if (empty($activeTasks) && empty($completedRepeatingTasks)) {
                    echo '
                    <div class="empty-state" style="grid-column: 1 / -1;">
                        <i class="fas fa-clipboard-list"></i>
                        <p>No tasks for today. Add a new one to get started!</p>
                    </div>';
                } else {
                    // Show active tasks first
                    foreach ($activeTasks as $item) {
                        echo renderTaskCard($item);
                    }
                    
                    // Show completed repeating tasks
                    if (!empty($completedRepeatingTasks)) {
                        echo '<div style="grid-column: 1 / -1; margin-top: 20px; padding-top: 20px; border-top: 2px solid var(--gray-light);">
                                <h3 class="bucket-title">
                                    <i class="fas fa-check-circle"></i>
                                    Completed (Next Occurrences)
                                    <span class="bucket-count">' . count($completedRepeatingTasks) . '</span>
                                </h3>
                              </div>';
                        
                        foreach ($completedRepeatingTasks as $item) {
                            echo renderTaskCard($item);
                        }
                    }
                }
                ?>
            </div>
        </div>

        <!-- Notes View -->
        <div class="view-content <?php echo $currentView === 'notes' ? 'active' : ''; ?>" id="notesView">
            <div class="content-header">
                <h1 class="page-title">Notes</h1>
            </div>
            <div class="notes-container">
                <?php
                if (empty($userNotes)) {
                    echo '
                    <div class="empty-state" style="grid-column: 1 / -1;">
                        <i class="fas fa-wand-magic-sparkles"></i>
                        <p>No notes yet. Add one to get started!</p>
                    </div>';
                } else {
                    foreach ($userNotes as $note) {
                        echo renderNoteCard($note);
                    }
                }
                ?>
            </div>
        </div>

        <!-- History View -->
        <div class="view-content <?php echo $currentView === 'history' ? 'active' : ''; ?>" id="historyView">
            <div class="content-header">
                <h1 class="page-title">History</h1>
            </div>
            
            <div id="historyContainer">
                <?php
                if (empty($historyRecords)) {
                    echo '
                    <div class="empty-state">
                        <i class="fas fa-history"></i>
                        <p>No completed items yet. Complete some items to see them here!</p>
                    </div>';
                } else {
                    // Group history by date
                    $groupedHistory = [];
                    foreach ($historyRecords as $item) {
                        $date = date('F j, Y', strtotime($item['completedAt'] ?? 'now'));
                        
                        if (!isset($groupedHistory[$date])) {
                            $groupedHistory[$date] = [];
                        }
                        
                        $groupedHistory[$date][] = $item;
                    }
                    
                    // Sort dates newest first
                    uksort($groupedHistory, function($a, $b) {
                        return strtotime($b) <=> strtotime($a);
                    });
                    
                    foreach ($groupedHistory as $date => $items) {
                        echo "<div class='history-date-group'>";
                        echo "<details class='history-date-details'>";
                        echo "<summary class='history-date-summary'><i class='fas fa-calendar'></i>{$date}<span class='details-toggle'>▼</span></summary>";
                        echo "<div class='history-date-content'>";
                        echo "<div class='history-items-container'>";
                        foreach ($items as $item) {
                            echo renderHistoryCard($item);
                        }
                        echo "</div>";
                        echo "</div></details></div>";
                    }
                }
                ?>
            </div>
        </div>
        
        <!-- Settings View -->
        <div class="view-content <?php echo $currentView === 'settings' ? 'active' : ''; ?>" id="settingsView">
            <div class="content-header">
                <h1 class="page-title">Settings</h1>
            </div>
            
            <div class="settings-card">
                <h2 class="settings-title">
                    <i class="fas fa-bell"></i>
                    Notification Settings
                </h2>
                
                <div class="settings-item">
                    <span class="settings-label">Hourly Task Status Reports</span>
                    <form method="POST" id="hourlyReportForm">
                        <input type="hidden" name="action" value="toggle_hourly_report">
                        <input type="hidden" name="csrf_token" value="<?php echo generateCSRFToken(); ?>">
                        <label class="toggle-switch">
                            <input type="checkbox" name="enabled" <?php echo ($notificationSettings['hourly_report'] ?? true) ? 'checked' : ''; ?> onchange="this.form.submit()">
                            <span class="toggle-slider"></span>
                        </label>
                    </form>
                </div>
                
                <p style="margin-top: 16px; color: var(--gray); font-size: 0.85rem;">
                    <i class="fas fa-info-circle"></i> 
                    Hourly reports send task status updates (completed/pending) to Telegram every hour.
                </p>
            </div>
            
            <div class="settings-card">
                <h2 class="settings-title">
                    <i class="fas fa-info-circle"></i>
                    System Information
                </h2>
                
                <div class="settings-item">
                    <span class="settings-label">PHP Version</span>
                    <span class="settings-value"><?php echo phpversion(); ?></span>
                </div>
                
                <div class="settings-item">
                    <span class="settings-label">Server Time</span>
                    <span class="settings-value"><?php echo date('Y-m-d H:i:s'); ?></span>
                </div>
                
                <div class="settings-item">
                    <span class="settings-label">Total Tasks</span>
                    <span class="settings-value"><?php echo count($userTasks ?? []); ?></span>
                </div>
                
                <div class="settings-item">
                    <span class="settings-label">Total Notes</span>
                    <span class="settings-value"><?php echo count($userNotes ?? []); ?></span>
                </div>
            </div>
            
            <div class="settings-card">
                <h2 class="settings-title">
                    <i class="fas fa-robot"></i>
                    Telegram Integration
                </h2>
                
                <div class="settings-item">
                    <span class="settings-label">Notifications</span>
                    <span class="settings-value">✅ Active</span>
                </div>
                
                <div class="settings-item">
                    <span class="settings-label">Task Reminders</span>
                    <span class="settings-value">10 messages before start</span>
                </div>
                
                <div class="settings-item">
                    <span class="settings-label">Note Reminders</span>
                    <span class="settings-value">Custom intervals</span>
                </div>
                
                <p style="margin-top: 16px; color: var(--gray); font-size: 0.85rem;">
                    <i class="fas fa-key"></i> 
                    Telegram User ID: <?php echo TELEGRAM_USER_ID; ?>
                </p>
            </div>
        </div>
    </div>

    <!-- Modals -->
    <div class="modal" id="addTaskModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 class="modal-title">Add Task</h2>
                <button type="button" class="close-modal" onclick="closeAddTaskModal()">&times;</button>
            </div>
            <div class="modal-body">
                <form method="POST" id="addTaskForm">
                    <input type="hidden" name="action" value="add_task">
                    <input type="hidden" name="csrf_token" value="<?php echo generateCSRFToken(); ?>">
                    <div class="form-group">
                        <label class="form-label">Title</label>
                        <input type="text" class="form-input" name="title" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Description</label>
                        <textarea class="form-textarea" name="description" placeholder="Optional details"></textarea>
                        <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Priority</label>
                        <select class="form-select" name="priority">
                            <?php for($i = 1; $i <= 15; $i++): ?>
                                <option value="<?php echo $i; ?>" <?php if($i==15) echo 'selected'; ?>><?php echo $i; ?></option>
                            <?php endfor; ?>
                        </select>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" class="form-checkbox" name="notify_enabled" id="notifyEnabled" checked>
                        <label class="checkbox-label" for="notifyEnabled">Enable Telegram notifications (10 reminders before start time)</label>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Repeat</label>
                        <select class="form-select" name="repeat" id="repeatSelect">
                            <option value="none">None</option>
                            <option value="daily">Daily</option>
                            <option value="weekly">Weekly</option>
                        </select>
                    </div>
                    <div class="date-input-group">
                        <div class="form-group">
                            <label class="form-label">Start Date</label>
                            <input type="date" class="form-input" name="start_date" id="startDate" value="<?php echo date('Y-m-d'); ?>">
                        </div>
                        <div class="form-group">
                            <label class="form-label">End Date</label>
                            <input type="date" class="form-input" name="end_date" id="endDate" value="<?php echo date('Y-m-d'); ?>">
                        </div>
                    </div>
                    <div class="time-input-group">
                        <div class="form-group">
                            <label class="form-label">Start Time</label>
                            <input type="time" class="form-input" name="start_time" id="startTime" value="<?php echo date('H:i'); ?>">
                        </div>
                        <div class="form-group">
                            <label class="form-label">End Time</label>
                            <input type="time" class="form-input" name="end_time" id="endTime" value="<?php echo date('H:i', strtotime('+1 hour')); ?>">
                        </div>
                    </div>
                    <div class="form-group" id="repeatEndDateGroup">
                        <label class="form-label">End of Repeat Date (Leave empty for infinite)</label>
                        <input type="date" class="form-input" name="repeat_end_date" id="repeatEndDate">
                    </div>
                    <div class="form-actions">
                        <button type="button" class="btn btn-secondary" onclick="closeAddTaskModal()">Cancel</button>
                        <button type="submit" class="btn btn-primary">Add Task</button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    <div class="modal" id="addNoteModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 class="modal-title">Add Note</h2>
                <button type="button" class="close-modal" onclick="closeAddNoteModal()">&times;</button>
            </div>
            <div class="modal-body">
                <form method="POST">
                    <input type="hidden" name="action" value="add_note">
                    <input type="hidden" name="csrf_token" value="<?php echo generateCSRFToken(); ?>">
                    <div class="form-group">
                        <label class="form-label">Title</label>
                        <input type="text" class="form-input" name="title" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Description</label>
                        <textarea class="form-textarea" name="description" placeholder="Optional details"></textarea>
                        <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" class="form-checkbox" name="notify_enabled" id="noteNotifyEnabled">
                        <label class="checkbox-label" for="noteNotifyEnabled">Enable regular Telegram notifications</label>
                    </div>
                    <div class="form-group" id="noteIntervalGroup" style="display: none;">
                        <label class="form-label">Notification Interval (hours)</label>
                        <input type="number" class="form-input" name="notify_interval" min="1" max="24" value="12" placeholder="Enter interval in hours">
                    </div>
                    <div class="form-actions">
                        <button type="button" class="btn btn-secondary" onclick="closeAddNoteModal()">Cancel</button>
                        <button type="submit" class="btn btn-primary">Save Note</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    
    <div class="modal" id="editNoteModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 class="modal-title">Edit Note</h2>
                <button type="button" class="close-modal" onclick="closeEditNoteModal()">&times;</button>
            </div>
            <div class="modal-body">
                <form method="POST" id="editNoteForm">
                    <input type="hidden" name="action" value="update_note">
                    <input type="hidden" name="csrf_token" value="<?php echo generateCSRFToken(); ?>">
                    <input type="hidden" name="note_id" id="editNoteId">
                    <div class="form-group">
                        <label class="form-label">Title</label>
                        <input type="text" class="form-input" name="title" id="editNoteTitle" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Description</label>
                        <textarea class="form-textarea" name="description" id="editNoteDescription"></textarea>
                        <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" class="form-checkbox" name="notify_enabled" id="editNoteNotifyEnabled">
                        <label class="checkbox-label" for="editNoteNotifyEnabled">Enable regular Telegram notifications</label>
                    </div>
                    <div class="form-group" id="editNoteIntervalGroup" style="display: none;">
                        <label class="form-label">Notification Interval (hours)</label>
                        <input type="number" class="form-input" name="notify_interval" id="editNoteInterval" min="1" max="24" value="12" placeholder="Enter interval in hours">
                    </div>
                    <div class="form-actions">
                        <button type="button" class="btn btn-secondary" onclick="closeEditNoteModal()">Cancel</button>
                        <button type="submit" class="btn btn-primary">Update Note</button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    <div class="modal" id="addSubtaskModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 class="modal-title">Add Subtask</h2>
                <button type="button" class="close-modal" onclick="closeAddSubtaskModal()">&times;</button>
            </div>
            <div class="modal-body">
                <form method="POST" id="addSubtaskForm">
                    <input type="hidden" name="action" value="add_subtask">
                    <input type="hidden" name="csrf_token" value="<?php echo generateCSRFToken(); ?>">
                    <input type="hidden" name="task_id" id="addSubtaskTaskId">
                    <div class="form-group">
                        <label class="form-label">Subtask Title</label>
                        <input type="text" class="form-input" name="title" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Description</label>
                        <textarea class="form-textarea" name="description" placeholder="Optional details"></textarea>
                        <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                    </div>
                    <div class="form-actions">
                        <button type="button" class="btn btn-secondary" onclick="closeAddSubtaskModal()">Cancel</button>
                        <button type="submit" class="btn btn-primary">Add Subtask</button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    <div class="modal" id="editTaskModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 class="modal-title">Edit Task</h2>
                <button type="button" class="close-modal" onclick="closeEditTaskModal()">&times;</button>
            </div>
            <div class="modal-body">
                <form method="POST" id="editTaskForm">
                    <input type="hidden" name="action" value="update_task">
                    <input type="hidden" name="csrf_token" value="<?php echo generateCSRFToken(); ?>">
                    <input type="hidden" name="task_id" id="editTaskId">
                    <div class="form-group">
                        <label class="form-label">Title</label>
                        <input type="text" class="form-input" name="title" id="editTaskTitle" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Description</label>
                        <textarea class="form-textarea" name="description" id="editTaskDescription"></textarea>
                        <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Priority</label>
                        <select class="form-select" name="priority" id="editTaskPriority">
                            <?php for($i = 1; $i <= 15; $i++): ?><option value="<?php echo $i; ?>"><?php echo $i; ?></option><?php endfor; ?>
                        </select>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" class="form-checkbox" name="notify_enabled" id="editTaskNotifyEnabled">
                        <label class="checkbox-label" for="editTaskNotifyEnabled">Enable Telegram notifications (10 reminders before start time)</label>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Repeat</label>
                        <select class="form-select" name="repeat" id="editTaskRepeat">
                            <option value="none">None</option>
                            <option value="daily">Daily</option>
                            <option value="weekly">Weekly</option>
                        </select>
                    </div>
                    <div class="date-input-group">
                        <div class="form-group">
                            <label class="form-label">Start Date</label>
                            <input type="date" class="form-input" name="start_date" id="editTaskStartDate">
                        </div>
                        <div class="form-group">
                            <label class="form-label">End Date</label>
                            <input type="date" class="form-input" name="end_date" id="editTaskEndDate">
                        </div>
                    </div>
                    <div class="time-input-group">
                        <div class="form-group">
                            <label class="form-label">Start Time</label>
                            <input type="time" class="form-input" name="start_time" id="editTaskStartTime">
                        </div>
                        <div class="form-group">
                            <label class="form-label">End Time</label>
                            <input type="time" class="form-input" name="end_time" id="editTaskEndTime">
                        </div>
                    </div>
                    <div class="form-group" id="editRepeatEndDateGroup">
                        <label class="form-label">End of Repeat Date (Leave empty for infinite)</label>
                        <input type="date" class="form-input" name="repeat_end_date" id="editRepeatEndDate">
                    </div>
                    <div class="form-actions">
                        <button type="button" class="btn btn-secondary" onclick="closeEditTaskModal()">Cancel</button>
                        <button type="submit" class="btn btn-primary">Update Task</button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    <div class="modal" id="editSubtaskModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 class="modal-title">Edit Subtask</h2>
                <button type="button" class="close-modal" onclick="closeEditSubtaskModal()">&times;</button>
            </div>
            <div class="modal-body">
                <form method="POST" id="editSubtaskForm">
                    <input type='hidden' name='action' value='update_subtask'> <input type='hidden' name='csrf_token' value='<?php echo generateCSRFToken(); ?>'>
                    <input type='hidden' name='task_id' id='editSubtaskTaskId'> <input type='hidden' name='subtask_id' id='editSubtaskId'>
                    <div class='form-group'>
                        <label class='form-label'>Subtask Title</label>
                        <input type='text' class='form-input' name='title' id='editSubtaskTitle' required>
                    </div>
                    <div class='form-group'>
                        <label class='form-label'>Subtask Description</label>
                        <textarea class='form-textarea' name='description' id='editSubtaskDescription'></textarea>
                        <small style="color: var(--gray); font-size: 0.75rem;">Use *text* for <strong>bold</strong> and _text_ for <em>italic</em></small>
                    </div>
                    <div class='form-group'>
                        <label class='form-label'>Priority</label>
                        <select class='form-select' name='priority' id='editSubtaskPriority'>
                            <?php for($i = 1; $i <= 15; $i++): ?><option value='<?php echo $i; ?>'><?php echo $i; ?></option><?php endfor; ?>
                        </select>
                    </div>
                    <div class='form-actions'>
                        <button type='button' class='btn btn-secondary' onclick='closeEditSubtaskModal()'>Cancel</button>
                        <button type='submit' class='btn btn-primary'>Update Subtask</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
    <?php endif; ?>

    <script>
        function switchTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-button').forEach(button => button.classList.remove('active'));
            document.getElementById(tabName + 'Tab').classList.add('active');
            event.target.classList.add('active');
        }

        function switchView(viewName) {
            const url = new URL(window.location);
            url.searchParams.set('view', viewName);
            window.history.replaceState({}, '', url);
            document.querySelectorAll('.view-content').forEach(view => view.classList.remove('active'));
            document.getElementById(viewName + 'View').classList.add('active');
            
            // Update FAB based on view
            updateFAB(viewName);
        }
        
        function updateFAB(viewName) {
            const fabContainer = document.getElementById('fabContainer');
            if (fabContainer) {
                if (viewName === 'tasks') {
                    fabContainer.innerHTML = '<button class="fab fab-tasks" onclick="openAddTaskModal()" title="Add Task"><i class="fas fa-plus"></i></button>';
                } else if (viewName === 'notes') {
                    fabContainer.innerHTML = '<button class="fab fab-notes" onclick="openAddNoteModal()" title="Add Note"><i class="fas fa-plus"></i></button>';
                } else {
                    fabContainer.innerHTML = '';
                }
            }
        }

        function openModal(modalId) { document.getElementById(modalId).style.display = 'flex'; }
        function closeModal(modalId) { document.getElementById(modalId).style.display = 'none'; }

        function openAddTaskModal() { 
            // Set default date and time
            const now = new Date();
            const today = now.toISOString().split('T')[0];
            const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000);
            const endTime = oneHourLater.toTimeString().split(':').slice(0, 2).join(':');
            
            document.getElementById('startDate').value = today;
            document.getElementById('endDate').value = today;
            document.getElementById('startTime').value = now.toTimeString().split(':').slice(0, 2).join(':');
            document.getElementById('endTime').value = endTime;
            
            openModal('addTaskModal'); 
        }
        
        function closeAddTaskModal() { closeModal('addTaskModal'); }
        function closeEditTaskModal() { closeModal('editTaskModal'); }
        function closeEditSubtaskModal() { closeModal('editSubtaskModal'); }
        
        function openAddNoteModal() { 
            openModal('addNoteModal'); 
            // Show/hide interval input based on checkbox
            const checkbox = document.getElementById('noteNotifyEnabled');
            const intervalGroup = document.getElementById('noteIntervalGroup');
            checkbox.addEventListener('change', function() {
                intervalGroup.style.display = this.checked ? 'block' : 'none';
            });
        }
        
        function closeAddNoteModal() { closeModal('addNoteModal'); }
        function closeEditNoteModal() { closeModal('editNoteModal'); }
        
        function openAddSubtaskModal(taskId) {
            document.getElementById('addSubtaskTaskId').value = taskId;
            openModal('addSubtaskModal');
        }
        function closeAddSubtaskModal() { closeModal('addSubtaskModal'); }

        function openEditTaskModal(taskId) {
            const taskData = <?php echo json_encode($filteredTasksList ?? []); ?>.find(t => t.id === taskId);
            if (taskData) {
                document.getElementById('editTaskId').value = taskId;
                document.getElementById('editTaskTitle').value = taskData.title || '';
                document.getElementById('editTaskDescription').value = taskData.description || '';
                document.getElementById('editTaskPriority').value = taskData.priority || 15;
                document.getElementById('editTaskRepeat').value = taskData.repeat || 'none';
                document.getElementById('editTaskNotifyEnabled').checked = taskData.notify_enabled || false;
                
                // Set date values
                const startDate = new Date(taskData.start_time);
                const endDate = new Date(taskData.end_time);
                document.getElementById('editTaskStartDate').value = startDate.toISOString().split('T')[0];
                document.getElementById('editTaskEndDate').value = endDate.toISOString().split('T')[0];
                
                // Set time values
                document.getElementById('editTaskStartTime').value = startDate.toTimeString().slice(0,5);
                document.getElementById('editTaskEndTime').value = endDate.toTimeString().slice(0,5);
                
                // Set repeat end date
                if (taskData.repeat_end_date) {
                    const repeatEndDate = new Date(taskData.repeat_end_date);
                    document.getElementById('editRepeatEndDate').value = repeatEndDate.toISOString().split('T')[0];
                } else {
                    document.getElementById('editRepeatEndDate').value = '';
                }
                
                openModal('editTaskModal');
            }
        }
        
        function openEditNoteModal(noteId) {
            const noteData = <?php echo json_encode($userNotes ?? []); ?>.find(n => n.id === noteId);
            if (noteData) {
                document.getElementById('editNoteId').value = noteId;
                document.getElementById('editNoteTitle').value = noteData.title || '';
                document.getElementById('editNoteDescription').value = noteData.description || '';
                document.getElementById('editNoteNotifyEnabled').checked = noteData.notify_enabled || false;
                document.getElementById('editNoteInterval').value = noteData.notify_interval || 12;
                
                const intervalGroup = document.getElementById('editNoteIntervalGroup');
                intervalGroup.style.display = noteData.notify_enabled ? 'block' : 'none';
                
                openModal('editNoteModal');
                
                // Add change event for checkbox
                document.getElementById('editNoteNotifyEnabled').addEventListener('change', function() {
                    intervalGroup.style.display = this.checked ? 'block' : 'none';
                });
            }
        }

        function openEditSubtaskModal(taskId, subtaskId) {
            const taskData = <?php echo json_encode($userTasks ?? []); ?>.find(t => t.id === taskId);
            if (taskData && taskData.subtasks) {
                const subtaskData = taskData.subtasks.find(s => s.id === subtaskId);
                if (subtaskData) {
                    document.getElementById('editSubtaskTaskId').value = taskId;
                    document.getElementById('editSubtaskId').value = subtaskId;
                    document.getElementById('editSubtaskTitle').value = subtaskData.title || '';
                    document.getElementById('editSubtaskDescription').value = subtaskData.description || '';
                    document.getElementById('editSubtaskPriority').value = subtaskData.priority || 15;
                    openModal('editSubtaskModal');
                }
            }
        }

        <?php if (isUserLoggedIn()): ?>
        function calculateTimeDisplay(startTime, endTime, isActive) {
            if (!isActive) {
                return {
                    text: 'Completed',
                    status: 'completed',
                    class: 'upcoming'
                };
            }
            
            const now = new Date();
            const start = new Date(startTime * 1000);
            const end = new Date(endTime * 1000);
            
            // Convert to minutes for easier comparison
            const currentMinutes = now.getHours() * 60 + now.getMinutes();
            const startMinutes = start.getHours() * 60 + start.getMinutes();
            const endMinutes = end.getHours() * 60 + end.getMinutes();
            
            const twoHours = 120; // 2 hours in minutes
            
            if (currentMinutes < (startMinutes - twoHours)) {
                // More than 2 hours before start
                return {
                    text: 'Upcoming',
                    status: 'upcoming',
                    class: 'upcoming'
                };
            } else if (currentMinutes >= (startMinutes - twoHours) && currentMinutes < startMinutes) {
                // Within 2 hours of start
                const minutesBefore = startMinutes - currentMinutes;
                const hours = Math.floor(minutesBefore / 60);
                const minutes = minutesBefore % 60;
                
                if (hours > 0) {
                    return {
                        text: `Starts in ${hours}h ${minutes}m`,
                        status: 'starting_soon',
                        class: 'starting_soon'
                    };
                } else {
                    return {
                        text: `Starts in ${minutes}m`,
                        status: 'starting_soon',
                        class: 'starting_soon'
                    };
                }
            } else if (currentMinutes >= startMinutes && currentMinutes <= endMinutes) {
                // During task time
                const minutesLeft = endMinutes - currentMinutes;
                const hours = Math.floor(minutesLeft / 60);
                const minutes = minutesLeft % 60;
                
                if (hours > 0) {
                    return {
                        text: `${hours}h ${minutes}m left`,
                        status: 'active',
                        class: 'active'
                    };
                } else {
                    return {
                        text: `${minutes}m left`,
                        status: 'active',
                        class: 'active'
                    };
                }
            } else if (currentMinutes > endMinutes && currentMinutes <= (endMinutes + twoHours)) {
                // Within 2 hours after end
                const minutesOver = currentMinutes - endMinutes;
                const hours = Math.floor(minutesOver / 60);
                const minutes = minutesOver % 60;
                
                if (hours > 0) {
                    return {
                        text: `Due by ${hours}h ${minutes}m`,
                        status: 'due',
                        class: 'due'
                    };
                } else {
                    return {
                        text: `Due by ${minutes}m`,
                        status: 'due',
                        class: 'due'
                    };
                }
            } else {
                // More than 2 hours after end
                return {
                    text: 'Overdue',
                    status: 'overdue',
                    class: 'overdue'
                };
            }
        }

        function updateTimeRemaining() {
            const now = Date.now();
            
            document.querySelectorAll('.task-time-display').forEach(el => {
                const startTime = parseInt(el.dataset.startTime);
                const endTime = parseInt(el.dataset.endTime);
                const isActive = el.dataset.isActive === 'true';
                
                const timeInfo = calculateTimeDisplay(startTime, endTime, isActive);
                el.innerHTML = timeInfo.text;
                el.className = 'task-time-display time-remaining-badge ' + timeInfo.class;
            });
        }
        
        document.addEventListener('DOMContentLoaded', () => {
            updateTimeRemaining();
            setInterval(updateTimeRemaining, 60000); // Update every minute
            
            const urlParams = new URLSearchParams(window.location.search);
            const viewParam = urlParams.get('view');
            if (viewParam) {
                switchView(viewParam);
            } else {
                // Initialize FAB for current view
                updateFAB('tasks');
            }
            
            // Date validation for add task form
            const startDateInput = document.getElementById('startDate');
            const endDateInput = document.getElementById('endDate');
            const startTimeInput = document.getElementById('startTime');
            const endTimeInput = document.getElementById('endTime');
            const repeatSelect = document.getElementById('repeatSelect');
            const repeatEndDateGroup = document.getElementById('repeatEndDateGroup');
            
            if (startDateInput && endDateInput) {
                startDateInput.addEventListener('change', function() {
                    const startDate = new Date(this.value);
                    const endDate = new Date(endDateInput.value);
                    const maxEndDate = new Date(startDate);
                    maxEndDate.setDate(maxEndDate.getDate() + 1);
                    
                    if (endDate > maxEndDate) {
                        endDateInput.value = maxEndDate.toISOString().split('T')[0];
                    }
                    
                    // Ensure end date is not before start date
                    if (endDate < startDate) {
                        endDateInput.value = this.value;
                    }
                });
                
                endDateInput.addEventListener('change', function() {
                    const startDate = new Date(startDateInput.value);
                    const endDate = new Date(this.value);
                    const maxEndDate = new Date(startDate);
                    maxEndDate.setDate(maxEndDate.getDate() + 1);
                    
                    if (endDate > maxEndDate) {
                        this.value = maxEndDate.toISOString().split('T')[0];
                    }
                    
                    // Ensure end date is not before start date
                    if (endDate < startDate) {
                        this.value = startDateInput.value;
                    }
                });
            }
            
            // Time validation
            if (startTimeInput && endTimeInput) {
                startTimeInput.addEventListener('change', function() {
                    const startTime = this.value;
                    const endTime = endTimeInput.value;
                    
                    if (startDateInput.value === endDateInput.value && startTime >= endTime) {
                        // If same day and start time is after end time, add 1 hour to end time
                        const start = new Date(`2000-01-01T${startTime}`);
                        start.setHours(start.getHours() + 1);
                        endTimeInput.value = start.toTimeString().slice(0,5);
                    }
                });
                
                endTimeInput.addEventListener('change', function() {
                    const startTime = startTimeInput.value;
                    const endTime = this.value;
                    
                    if (startDateInput.value === endDateInput.value && endTime <= startTime) {
                        // If same day and end time is before start time, add 1 hour to start time
                        const end = new Date(`2000-01-01T${endTime}`);
                        if (end.getHours() === 0) {
                            // If end time is midnight, make start time 11 PM
                            startTimeInput.value = '23:00';
                        } else {
                            const start = new Date(`2000-01-01T${endTime}`);
                            start.setHours(start.getHours() - 1);
                            startTimeInput.value = start.toTimeString().slice(0,5);
                        }
                    }
                });
            }
            
            // Show/hide repeat end date based on repeat selection
            if (repeatSelect && repeatEndDateGroup) {
                repeatSelect.addEventListener('change', function() {
                    if (this.value === 'none') {
                        repeatEndDateGroup.style.display = 'none';
                    } else {
                        repeatEndDateGroup.style.display = 'block';
                    }
                });
                
                // Initial state
                if (repeatSelect.value === 'none') {
                    repeatEndDateGroup.style.display = 'none';
                }
            }
            
            // Similar for edit form
            const editRepeatSelect = document.getElementById('editTaskRepeat');
            const editRepeatEndDateGroup = document.getElementById('editRepeatEndDateGroup');
            
            if (editRepeatSelect && editRepeatEndDateGroup) {
                editRepeatSelect.addEventListener('change', function() {
                    if (this.value === 'none') {
                        editRepeatEndDateGroup.style.display = 'none';
                    } else {
                        editRepeatEndDateGroup.style.display = 'block';
                    }
                });
                
                // Initial state for edit form
                if (editRepeatSelect.value === 'none') {
                    editRepeatEndDateGroup.style.display = 'none';
                }
            }
            
            // Handle note notification checkbox
            const noteNotifyCheckbox = document.getElementById('noteNotifyEnabled');
            const noteIntervalGroup = document.getElementById('noteIntervalGroup');
            
            if (noteNotifyCheckbox && noteIntervalGroup) {
                noteNotifyCheckbox.addEventListener('change', function() {
                    noteIntervalGroup.style.display = this.checked ? 'block' : 'none';
                });
            }
        });
        <?php endif; ?>
    </script>
</body>
</html>
