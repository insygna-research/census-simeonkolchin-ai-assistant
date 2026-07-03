"""
Web UI routes with WebSocket chat
"""

import logging
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class ReasoningToggle(BaseModel):
    enabled: bool


@router.get("/api/reasoning")
async def get_reasoning_status():
    """Get current reasoning mode status"""
    from src.app import agent
    from src.config import settings
    if agent:
        return JSONResponse({
            "enabled": agent.is_reasoning_enabled(),
            "provider": settings.LLM_PROVIDER
        })
    return JSONResponse({"enabled": False, "provider": "unknown"})


@router.post("/api/reasoning")
async def set_reasoning_status(toggle: ReasoningToggle):
    """Toggle reasoning mode on/off"""
    from src.app import agent
    if agent:
        agent.set_reasoning_enabled(toggle.enabled)
        return JSONResponse({
            "success": True,
            "enabled": agent.is_reasoning_enabled()
        })
    return JSONResponse({"success": False, "error": "Agent not initialized"}, status_code=500)


class StopRequest(BaseModel):
    session_id: str


@router.post("/api/stop")
async def stop_execution(request: StopRequest):
    """Stop the current execution for a session"""
    from src.app import agent
    if agent:
        success = agent.stop_session(request.session_id)
        return JSONResponse({
            "success": success,
            "message": "Stop requested" if success else "Session not found"
        })
    return JSONResponse({"success": False, "error": "Agent not initialized"}, status_code=500)


@router.get("/api/docs/projects")
async def list_docs_projects():
    """Return the list of GitLab projects configured for documentation analysis."""
    from src.config import settings as s
    from src.app import agent
    projects = s.get_docs_analyzed_projects() or [f"{s.DOCS_ANALYZED_GROUP}/*"]
    return {
        "group": s.DOCS_ANALYZED_GROUP,
        "projects": projects,
        "change_window_days": s.DOCS_CHANGE_WINDOW_DAYS,
        "state_file": s.DOCS_STATE_FILE,
    }


@router.get("/ui")
async def ui_page():
    """Serve the chat UI with agent activity panel"""
    html_content = r"""
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Team Assistant</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);height:100vh;display:flex;justify-content:center;align-items:center}
.container{width:95%;max-width:1500px;height:92vh;background:#fff;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,.3);display:flex;flex-direction:column;overflow:hidden}

/* HEADER */
.header{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:12px 20px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;gap:12px}
.header h1{font-size:20px;font-weight:600;white-space:nowrap}
.hdr-right{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.hdr-btn{color:rgba(255,255,255,.75);text-decoration:none;font-size:12px;padding:4px 10px;border:1px solid rgba(255,255,255,.3);border-radius:8px;transition:all .2s;white-space:nowrap;cursor:pointer;background:none}
.hdr-btn:hover{color:#fff;border-color:rgba(255,255,255,.6)}
.status{display:flex;align-items:center;gap:6px;font-size:12px}
.status-dot{width:8px;height:8px;border-radius:50%;background:#4ade80;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

/* ── Update Docs button ── */
.update-docs-btn {
    display:inline-flex;align-items:center;gap:6px;padding:5px 14px;
    background:linear-gradient(135deg,#6366f1,#8b5cf6);
    border:none;border-radius:18px;color:#fff;font-size:12px;font-weight:500;
    cursor:pointer;transition:all .2s;white-space:nowrap;
}
.update-docs-btn:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(99,102,241,.4)}
.update-docs-btn.success{background:#4ade80}
.update-docs-btn.error{background:#ef4444}
.update-docs-btn.loading{opacity:.85;pointer-events:none;animation:docs-pulse 1.5s ease-in-out infinite}
@keyframes docs-pulse{0%,100%{box-shadow:0 0 0 0 rgba(99,102,241,.4)}50%{box-shadow:0 0 0 8px rgba(99,102,241,0)}}
.docs-phase-text{font-size:11px;color:#a1a1aa;margin-left:4px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.timer-container{display:none;align-items:center;gap:6px;padding:4px 12px;background:rgba(255,255,255,.15);border-radius:16px;font-size:12px}
.timer-container.visible{display:flex}
.timer-value{font-family:'Courier New',monospace;min-width:40px}

/* MODEL SELECTOR */
.model-select{padding:4px 8px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(255,255,255,.15);color:#fff;font-size:12px;outline:none;cursor:pointer}
.model-select option{color:#333;background:#fff}

/* REASONING TOGGLE */
.reasoning-toggle{display:flex;align-items:center;gap:8px;padding:4px 12px;background:rgba(255,255,255,.15);border-radius:16px;font-size:12px}
.reasoning-toggle label{cursor:pointer;display:flex;align-items:center;gap:6px}
.toggle-switch{position:relative;width:36px;height:18px;background:rgba(255,255,255,.3);border-radius:9px;cursor:pointer;transition:background .3s}
.toggle-switch.active{background:#4ade80}
.toggle-switch::after{content:'';position:absolute;width:14px;height:14px;background:#fff;border-radius:50%;top:2px;left:2px;transition:transform .3s}
.toggle-switch.active::after{transform:translateX(18px)}

/* MAIN AREA */
.main{flex:1;display:flex;overflow:hidden}

/* LEFT SIDEBAR — CHAT LIST */
.sidebar{width:260px;background:#f8fafc;border-right:1px solid #e2e8f0;display:flex;flex-direction:column;flex-shrink:0}
.sidebar-header{padding:12px 14px;border-bottom:1px solid #e2e8f0;display:flex;gap:8px;align-items:center;background:#f1f5f9}
.sidebar-header button{flex:1;padding:8px;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;transition:transform .2s}
.sidebar-header button:hover{transform:translateY(-1px)}
.chat-list{flex:1;overflow-y:auto;padding:8px}
.chat-item{padding:10px 12px;border-radius:10px;cursor:pointer;font-size:13px;margin-bottom:4px;display:flex;justify-content:space-between;align-items:center;transition:background .15s;color:#374151}
.chat-item:hover{background:#e5e7eb}
.chat-item.active{background:#667eea;color:#fff}
.chat-item .chat-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chat-item .chat-delete{opacity:0;border:none;background:none;cursor:pointer;font-size:14px;padding:2px 4px;border-radius:4px;transition:opacity .15s}
.chat-item:hover .chat-delete{opacity:.6}
.chat-item .chat-delete:hover{opacity:1}
.chat-item.active .chat-delete{color:#fff}

/* CHAT PANEL */
.chat-panel{flex:1;display:flex;flex-direction:column;min-width:0}
.chat-container{flex:1;overflow-y:auto;padding:20px 24px;background:#f9fafb}

/* ACTIVITY PANEL (right) */
.activity-panel{width:320px;background:#f8fafc;border-left:1px solid #e2e8f0;display:flex;flex-direction:column;flex-shrink:0}
.activity-header{padding:12px 16px;font-weight:600;font-size:13px;color:#475569;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;background:#f1f5f9}
.activity-header .badge{background:#667eea;color:#fff;font-size:11px;padding:2px 8px;border-radius:10px}
.activity-list{flex:1;overflow-y:auto;padding:10px}
.activity-empty{color:#94a3b8;font-size:12px;text-align:center;padding:30px 16px;line-height:1.6}
.activity-item{padding:8px 12px;margin-bottom:6px;border-radius:8px;font-size:12px;line-height:1.5;animation:fadeSlideIn .25s ease-out}
@keyframes fadeSlideIn{from{opacity:0;transform:translateX(10px)}to{opacity:1;transform:translateX(0)}}
.activity-item.thinking{background:#eff6ff;border:1px solid #bfdbfe;color:#1e40af}
.activity-item.tool-running{background:#fefce8;border:1px solid #fde68a;color:#854d0e}
.activity-item.tool-running .spinner{display:inline-block;width:11px;height:11px;border:2px solid #d97706;border-top-color:transparent;border-radius:50%;animation:spin .7s linear infinite;margin-right:4px;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
.activity-item.tool-success{background:#f0fdf4;border:1px solid #bbf7d0;color:#166534}
.activity-item.tool-error{background:#fef2f2;border:1px solid #fecaca;color:#991b1b}
.activity-item.done{background:#f0f9ff;border:1px solid #bae6fd;color:#075985}
.activity-item.reasoning{background:#faf5ff;border:1px solid #e9d5ff;color:#6b21a8}
.activity-item.reasoning .reasoning-content{max-height:180px;overflow-y:auto;font-size:11px;line-height:1.4;margin-top:4px;padding:6px;background:rgba(255,255,255,.5);border-radius:4px;white-space:pre-wrap;word-break:break-word}
.activity-item.reasoning .reasoning-toggle-btn{font-size:11px;color:#9333ea;cursor:pointer;text-decoration:underline;margin-top:4px;display:inline-block}
.activity-item .label{font-weight:600;display:block;margin-bottom:2px}
.activity-item .detail{font-size:11px;opacity:.85;word-break:break-word}
.activity-item .time{font-size:10px;opacity:.5;margin-top:2px}

/* MESSAGES */
.message{margin-bottom:16px;display:flex;gap:10px;animation:slideIn .3s ease-out}
@keyframes slideIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.message.user{flex-direction:row-reverse}
.avatar{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:12px;flex-shrink:0}
.message.user .avatar{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}
.message.assistant .avatar{background:linear-gradient(135deg,#4ade80,#22c55e);color:#fff}
.message-content{max-width:75%;padding:12px 16px;border-radius:14px;line-height:1.6;font-size:14px}
.message.user .message-content{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border-bottom-right-radius:4px}
.message.assistant .message-content{background:#fff;color:#1f2937;border:1px solid #e5e7eb;border-bottom-left-radius:4px}
.message.system .message-content{background:#fef3c7;color:#92400e;border:1px solid #fde68a;max-width:100%;text-align:center;font-size:13px}

/* MD styles */
.message-content h1,.message-content h2,.message-content h3{margin-top:12px;margin-bottom:6px}
.message-content h1{font-size:1.3em}.message-content h2{font-size:1.2em}.message-content h3{font-size:1.05em}
.message-content ul,.message-content ol{margin:6px 0 6px 18px}
.message-content li{margin-bottom:3px}
.message-content code{background:#f3f4f6;padding:2px 5px;border-radius:4px;font-family:'Courier New',monospace;font-size:.86em}
.message-content pre{background:#1f2937;color:#f9fafb;padding:12px;border-radius:8px;overflow-x:auto;margin:8px 0}
.message-content pre code{background:none;padding:0;color:#f9fafb}
.message-content blockquote{border-left:3px solid #667eea;padding-left:12px;margin:8px 0;color:#6b7280}
.message-content a{color:#667eea;text-decoration:none}
.message-content a:hover{text-decoration:underline}
.message-content table{border-collapse:collapse;margin:8px 0;width:100%}
.message-content th,.message-content td{border:1px solid #e5e7eb;padding:6px 10px;text-align:left;font-size:13px}
.message-content th{background:#f3f4f6;font-weight:600}

/* INPUT */
.input-container{padding:12px 20px;background:#fff;border-top:1px solid #e5e7eb;display:flex;gap:8px;flex-shrink:0;align-items:flex-end}
.input-wrapper{flex:1;display:flex;align-items:flex-end;border:2px solid #e5e7eb;border-radius:18px;transition:border-color .3s;padding:4px 4px 4px 14px;gap:6px}
.input-wrapper:focus-within{border-color:#667eea}
#messageInput{flex:1;border:none;outline:none;font-size:14px;line-height:1.4;resize:none;max-height:140px;min-height:24px;padding:6px 0;font-family:inherit;background:transparent}
.attach-btn{background:none;border:none;cursor:pointer;font-size:18px;padding:4px;border-radius:50%;transition:background .15s;flex-shrink:0;align-self:flex-end;margin-bottom:2px}
.attach-btn:hover{background:#f3f4f6}
#fileInput{display:none}
.file-badge{display:flex;align-items:center;gap:4px;padding:2px 8px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px;font-size:11px;color:#1e40af;margin-bottom:4px}
.file-badge .remove-file{cursor:pointer;font-size:14px;margin-left:2px}
#sendButton{padding:10px 22px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:18px;font-size:14px;font-weight:600;cursor:pointer;transition:transform .2s,box-shadow .2s;white-space:nowrap}
#sendButton:hover{transform:translateY(-1px);box-shadow:0 6px 14px rgba(102,126,234,.3)}
#sendButton:disabled{opacity:.5;cursor:not-allowed;transform:none}
#stopButton{padding:10px 18px;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;border:none;border-radius:18px;font-size:14px;font-weight:600;cursor:pointer;display:none}
#stopButton.visible{display:block}

/* EXPORT BUTTONS */
.message-wrapper{position:relative}
.export-btns{display:flex;gap:4px;margin-top:6px}
.export-btn{display:inline-flex;align-items:center;gap:3px;padding:3px 8px;background:#f3f4f6;border:1px solid #e5e7eb;border-radius:6px;font-size:10px;color:#6b7280;cursor:pointer;transition:all .2s;user-select:none}
.export-btn:hover{background:#e5e7eb;color:#374151}
.export-btn.copied{background:#dcfce7;border-color:#bbf7d0;color:#166534}

/* SETTINGS PANEL (overlay) */
.settings-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.4);z-index:100;justify-content:center;align-items:center}
.settings-overlay.visible{display:flex}
.settings-modal{background:#fff;border-radius:16px;width:560px;max-width:92vw;max-height:80vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,.3)}
.settings-modal-header{padding:16px 20px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;align-items:center}
.settings-modal-header h2{font-size:18px;font-weight:600}
.settings-modal-close{background:none;border:none;font-size:20px;cursor:pointer;color:#6b7280}
.settings-modal-body{padding:20px}
.settings-section{margin-bottom:24px}
.settings-section h3{font-size:14px;font-weight:600;margin-bottom:12px;color:#374151;display:flex;align-items:center;gap:6px}
.token-item{display:flex;align-items:center;gap:8px;padding:10px 12px;background:#f9fafb;border-radius:10px;margin-bottom:6px}
.token-item .token-name{flex:1;font-size:13px;font-weight:500}
.token-toggle{position:relative;width:40px;height:22px;flex-shrink:0}
.token-toggle input{opacity:0;width:0;height:0}
.token-toggle .slider{position:absolute;cursor:pointer;inset:0;background:#d1d5db;border-radius:11px;transition:.3s}
.token-toggle .slider:before{position:absolute;content:"";height:16px;width:16px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.3s}
.token-toggle input:checked+.slider{background:#667eea}
.token-toggle input:checked+.slider:before{transform:translateX(18px)}
.token-delete{background:none;border:none;cursor:pointer;color:#ef4444;font-size:16px;padding:2px 4px}
.add-token-form{display:flex;gap:8px;margin-top:10px}
.add-token-form input{flex:1;padding:8px 12px;border:1px solid #e5e7eb;border-radius:8px;font-size:13px;outline:none}
.add-token-form input:focus{border-color:#667eea}
.add-token-form button{padding:8px 16px;background:#667eea;color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer}
.cat-badge{font-size:10px;padding:2px 6px;border-radius:4px;font-weight:500;vertical-align:middle}
.cat-internal{background:#dbeafe;color:#1d4ed8}
.cat-external{background:#fef3c7;color:#92400e}
.type-badge{font-size:10px;padding:2px 6px;border-radius:4px;font-weight:500;margin-left:6px}
.type-yougile{background:#e0e7ff;color:#4338ca}
.type-outline{background:#d1fae5;color:#065f46}
.add-source-form{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.add-source-form select,.add-source-form input{padding:8px 12px;border:1px solid #e5e7eb;border-radius:8px;font-size:13px;outline:none}
.add-source-form select{min-width:120px}
.add-source-form input{flex:1;min-width:140px}
.add-source-form button{padding:8px 16px;background:#667eea;color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer}
#srcConfigFields{display:flex;gap:8px;width:100%;flex-wrap:wrap}
#srcConfigFields input{flex:1;padding:8px 12px;border:1px solid #e5e7eb;border-radius:8px;font-size:13px;outline:none;min-width:140px}
/* TG chats in settings */
.tg-chat-item{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:#f9fafb;border-radius:8px;margin-bottom:4px;font-size:13px}
.tg-chat-title{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tg-badge{font-size:10px;padding:1px 6px;border-radius:4px;font-weight:600;margin-left:6px}
.tg-badge-group{background:#dbeafe;color:#1d4ed8}
.tg-badge-channel{background:#fef3c7;color:#92400e}
.tg-badge-user{background:#e0e7ff;color:#4338ca}

@keyframes bounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}
@media(max-width:1000px){.activity-panel{display:none}}
@media(max-width:700px){.sidebar{display:none}.container{width:100%;height:100vh;border-radius:0}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Team Assistant</h1>
    <div class="hdr-right">
      <div class="timer-container" id="timerContainer"><span>⏱️</span><span class="timer-value" id="timerValue">0:00</span></div>
      <select class="model-select" id="modelSelect" title="Выбор модели"></select>
      <div class="reasoning-toggle" id="reasoningToggleContainer" style="display:none"><label><span>🧠 Reasoning</span><div class="toggle-switch" id="reasoningSwitch" onclick="toggleReasoning()"></div></label></div>
      <div class="reasoning-toggle"><label><span>🌐 Браузер</span><div class="toggle-switch active" id="browserSwitch" onclick="toggleBrowser()"></div></label></div>
      <div class="status"><span class="status-dot"></span><span id="statusText">Подключено</span></div>
      <button class="update-docs-btn" id="updateDocsBtn" onclick="runDocTask()" title="Проанализировать код и обновить документацию">\U0001f4dd Документация</button>
      <span class="docs-phase-text" id="docsPhaseText" style="display:none"></span>
      <button class="hdr-btn" onclick="openSettings()">⚙️ Настройки</button>
      <a class="hdr-btn" href="/ui/telegram">📱 Telegram</a>
      <a class="hdr-btn" href="/logout">🚪 Выйти</a>
    </div>
  </div>

  <div class="main">
    <!-- LEFT SIDEBAR: chat history -->
    <div class="sidebar">
      <div class="sidebar-header"><button onclick="newChat()">＋ Новый чат</button></div>
      <div class="chat-list" id="chatList"></div>
    </div>

    <!-- CHAT PANEL -->
    <div class="chat-panel">
      <div class="chat-container" id="chatContainer">
        <div class="message system"><div class="message-content"><strong>Добро пожаловать!</strong> Я Team Assistant — ИИ-помощник команды разработки.</div></div>
      </div>
      <div id="filePreview"></div>
      <div class="input-container">
        <div class="input-wrapper">
          <textarea id="messageInput" placeholder="Введите сообщение... (Shift+Enter — новая строка)" rows="1" autocomplete="off"></textarea>
          <button class="attach-btn" onclick="document.getElementById('fileInput').click()" title="Прикрепить файл">📎</button>
          <input type="file" id="fileInput" accept=".txt,.md,.csv,.json,.xml,.html,.py,.js,.ts,.yaml,.yml,.toml,.ini,.cfg,.log,.docx,.doc,.pdf,.xlsx">
        </div>
        <button id="sendButton">Отправить</button>
        <button id="stopButton">⏹ Стоп</button>
      </div>
    </div>

    <!-- RIGHT: activity -->
    <div class="activity-panel">
      <div class="activity-header"><span>Действия агента</span><span class="badge" id="stepCounter" style="display:none">0</span></div>
      <div class="activity-list" id="activityList">
        <div class="activity-empty" id="activityEmpty">Здесь будут действия агента<br>в реальном времени</div>
      </div>
    </div>
  </div>
</div>

<!-- SETTINGS OVERLAY -->
<div class="settings-overlay" id="settingsOverlay">
  <div class="settings-modal">
    <div class="settings-modal-header"><h2>⚙️ Настройки</h2><button class="settings-modal-close" onclick="closeSettings()">✕</button></div>
    <div class="settings-modal-body">
      <div class="settings-section">
        <h3>🏠 Мои источники <span class="cat-badge cat-internal">internal</span></h3>
        <div id="srcInternal"></div>
      </div>
      <div class="settings-section">
        <h3>🌐 Внешние источники <span class="cat-badge cat-external">external</span></h3>
        <div id="srcExternal"></div>
      </div>
      <div class="settings-section">
        <h3>➕ Добавить источник</h3>
        <div class="add-source-form">
          <select id="srcNewType"><option value="yougile">📋 YouGile</option><option value="outline">📝 Outline</option></select>
          <select id="srcNewCat"><option value="internal">🏠 Мой</option><option value="external">🌐 Внешний</option></select>
          <input type="text" id="srcNewName" placeholder="Название">
          <div id="srcConfigFields"></div>
          <button onclick="addSource()">Добавить</button>
        </div>
      </div>
      <div class="settings-section">
        <h3>💬 Telegram чаты</h3>
        <div id="tgChatsList"><div style="color:#9ca3af;font-size:13px;padding:12px">Загрузка...</div></div>
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
let sessionId = 'web-' + Math.random().toString(36).substring(7);
let ws = null, isConnected = false, stepCount = 0, reasoningEnabled = false, isProcessing = false, browserEnabled = true;
let timerInterval = null, startTime = null;
let pendingFileText = null, pendingFileName = null;
let selectedModel = '';

const chatContainer = document.getElementById('chatContainer');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const stopButton = document.getElementById('stopButton');
const statusText = document.getElementById('statusText');
const activityList = document.getElementById('activityList');
const activityEmpty = document.getElementById('activityEmpty');
const stepCounter = document.getElementById('stepCounter');
const timerContainer = document.getElementById('timerContainer');
const timerValue = document.getElementById('timerValue');
const modelSelect = document.getElementById('modelSelect');
const fileInput = document.getElementById('fileInput');
const filePreview = document.getElementById('filePreview');

/* ── Auto-grow textarea ── */
messageInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 140) + 'px';
});

/* ── File upload ── */
fileInput.addEventListener('change', async function() {
    const file = this.files[0];
    if (!file) return;
    filePreview.innerHTML = '<div class="file-badge" style="margin:0 20px 4px 20px">📄 ' + escHtml(file.name) + ' <span class="remove-file" onclick="clearFile()">✕</span></div>';
    const formData = new FormData();
    formData.append('file', file);
    try {
        const resp = await fetch('/api/upload', { method: 'POST', body: formData });
        const data = await resp.json();
        if (data.error) {
            filePreview.innerHTML = '<div class="file-badge" style="margin:0 20px 4px 20px;background:#fee2e2;border-color:#fecaca;color:#991b1b">❌ ' + data.error + ' <span class="remove-file" onclick="clearFile()">✕</span></div>';
            return;
        }
        pendingFileText = data.text;
        pendingFileName = data.filename;
    } catch(e) {
        filePreview.innerHTML = '';
    }
    this.value = '';
});

function clearFile() {
    pendingFileText = null;
    pendingFileName = null;
    filePreview.innerHTML = '';
}

/* ── Models ── */
async function loadModels() {
    try {
        const resp = await fetch('/api/models');
        const data = await resp.json();
        const models = data.models || [];
        modelSelect.innerHTML = '';
        models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.name;
            modelSelect.appendChild(opt);
        });
        if (data.default) modelSelect.value = data.default;
        selectedModel = modelSelect.value;
    } catch(e) { console.error('Models load failed:', e); }
}
modelSelect.addEventListener('change', () => { selectedModel = modelSelect.value; });
loadModels();

/* ── Chat list ── */
async function loadChats() {
    try {
        const resp = await fetch('/api/chats');
        const data = await resp.json();
        const list = document.getElementById('chatList');
        list.innerHTML = '';
        (data.chats || []).forEach(c => {
            const item = document.createElement('div');
            item.className = 'chat-item' + (c.id === sessionId ? ' active' : '');
            item.innerHTML = '<span class="chat-title">' + escHtml(c.title) + '</span><button class="chat-delete" onclick="event.stopPropagation();deleteChat(\'' + c.id + '\')" title="Удалить">✕</button>';
            item.addEventListener('click', () => switchChat(c.id));
            list.appendChild(item);
        });
    } catch(e) {}
}

function newChat() {
    sessionId = 'web-' + Math.random().toString(36).substring(7);
    chatContainer.innerHTML = '<div class="message system"><div class="message-content"><strong>Новый чат</strong> — задайте вопрос.</div></div>';
    clearActivity();
    reconnectWS();
    loadChats();
}

async function switchChat(chatId) {
    sessionId = chatId;
    chatContainer.innerHTML = '';
    clearActivity();
    try {
        const resp = await fetch('/api/chats/' + chatId + '/messages');
        const data = await resp.json();
        (data.messages || []).forEach(m => {
            if (m.role === 'user' || m.role === 'assistant') addMessage(m.role, m.content);
        });
    } catch(e) {}
    reconnectWS();
    loadChats();
}

async function deleteChat(chatId) {
    if (!confirm('Удалить этот чат?')) return;
    await fetch('/api/chats/' + chatId, { method: 'DELETE' });
    if (chatId === sessionId) newChat();
    else loadChats();
}

loadChats();

/* ── Timer ── */
function startTimer() { startTime = Date.now(); timerContainer.classList.add('visible'); updateTimerDisplay(); timerInterval = setInterval(updateTimerDisplay, 1000); }
function stopTimer() { if (timerInterval) { clearInterval(timerInterval); timerInterval = null; } setTimeout(() => { if (!isProcessing) timerContainer.classList.remove('visible'); }, 3000); }
function updateTimerDisplay() { if (!startTime) return; const el = Math.floor((Date.now() - startTime) / 1000); timerValue.textContent = Math.floor(el/60) + ':' + (el%60).toString().padStart(2,'0'); }

/* ── Reasoning ── */
async function loadReasoningStatus() {
    try {
        const resp = await fetch('/api/reasoning');
        const data = await resp.json();
        reasoningEnabled = data.enabled;
        const sw = document.getElementById('reasoningSwitch');
        if (data.enabled) sw.classList.add('active'); else sw.classList.remove('active');
        if (data.provider === 'deepseek') document.getElementById('reasoningToggleContainer').style.display = '';
    } catch(e) {}
}
async function toggleReasoning() {
    const newState = !reasoningEnabled;
    try {
        const resp = await fetch('/api/reasoning', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({enabled: newState}) });
        const data = await resp.json();
        if (data.success) { reasoningEnabled = data.enabled; const sw = document.getElementById('reasoningSwitch'); if (data.enabled) sw.classList.add('active'); else sw.classList.remove('active'); }
    } catch(e) {}
}
function toggleBrowser() {
    browserEnabled = !browserEnabled;
    const sw = document.getElementById('browserSwitch');
    if (browserEnabled) sw.classList.add('active'); else sw.classList.remove('active');
}
loadReasoningStatus();

/* ── WebSocket ── */
function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(protocol + '//' + location.host + '/ws/' + sessionId);
    ws.onopen = () => { isConnected = true; statusText.textContent = 'Подключено'; sendButton.disabled = false; };
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'progress') addActivityItem(data);
        else if (data.type === 'response') { removeLoading(); addMessage('assistant', data.message); finalizeActivity(); loadChats(); }
        else if (data.type === 'error') { removeLoading(); addMessage('system', 'Ошибка: ' + data.message); finalizeActivity(); }
        else if (data.type === 'doc_progress') handleDocProgress(data);
        else if (data.type === 'doc_completed') handleDocCompleted(data);
        else if (data.type === 'doc_error') handleDocError(data);
    };
    ws.onerror = () => { statusText.textContent = 'Ошибка'; };
    ws.onclose = () => { isConnected = false; statusText.textContent = 'Отключено'; sendButton.disabled = true; setTimeout(connect, 3000); };
}

function reconnectWS() {
    if (ws) { ws.onclose = null; ws.close(); }
    connect();
}

/* ── Update Docs Pipeline ── */
function runDocTask() {
    const btn = document.getElementById('updateDocsBtn');
    const phaseEl = document.getElementById('docsPhaseText');
    if (!btn || btn.classList.contains('loading')) return;
    btn.classList.add('loading');
    btn.classList.remove('success', 'error');
    btn.innerHTML = '\u23f3 Анализ...';
    phaseEl.style.display = 'inline';
    phaseEl.textContent = '';
    ws.send(JSON.stringify({ type: 'run_doc_task' }));
}

function handleDocProgress(data) {
    const btn = document.getElementById('updateDocsBtn');
    const phaseEl = document.getElementById('docsPhaseText');
    const phase = data.phase || '';
    if (phase === 'analysis') {
        const svc = data.service ? ' (' + data.service + ')' : '';
        btn.innerHTML = '\u23f3 Анализ кода' + svc;
        if (data.current && data.total) phaseEl.textContent = data.current + '/' + data.total;
    } else if (phase === 'generation') {
        const sec = data.section || '';
        btn.innerHTML = '\u23f3 Генерация' + (sec ? ': ' + sec : '');
        if (data.current && data.total) phaseEl.textContent = data.current + '/' + data.total;
    } else if (phase === 'save') {
        btn.innerHTML = '\u23f3 Сохранение...';
        phaseEl.textContent = '';
    }
}

function handleDocCompleted(data) {
    const btn = document.getElementById('updateDocsBtn');
    const phaseEl = document.getElementById('docsPhaseText');
    btn.classList.remove('loading');
    phaseEl.style.display = 'none';
    if (data.status === 'no_changes') {
        btn.classList.add('success');
        btn.innerHTML = '\u2705 Изменений нет';
    } else {
        btn.classList.add('success');
        btn.innerHTML = '\u2705 Документация обновлена';
        if (data.message) addMessage('assistant', data.message);
    }
    setTimeout(() => {
        btn.classList.remove('success', 'error');
        btn.innerHTML = '\uD83D\uDCDD Документация';
    }, 8000);
}

function handleDocError(data) {
    const btn = document.getElementById('updateDocsBtn');
    const phaseEl = document.getElementById('docsPhaseText');
    btn.classList.remove('loading');
    btn.classList.add('error');
    phaseEl.style.display = 'none';
    btn.innerHTML = '\u274C Ошибка';
    if (data.message) addMessage('system', data.message);
    setTimeout(() => {
        btn.classList.remove('error');
        btn.innerHTML = '\uD83D\uDCDD Документация';
    }, 8000);
}

/* ── Activity ── */
function addActivityItem(data) {
    if (activityEmpty) activityEmpty.style.display = 'none';
    const item = document.createElement('div');
    item.className = 'activity-item';
    const now = new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
    const evt = data.event || '';
    if (evt === 'tool_done') {
        stepCount++; stepCounter.style.display = ''; stepCounter.textContent = stepCount;
        item.className += data.success ? ' tool-success' : ' tool-error';
        item.innerHTML = '<span class="label">' + (data.success?'✅':'❌') + ' ' + escHtml(data.description||data.tool) + '</span><span class="detail">' + escHtml(data.result) + '</span><span class="time">' + now + '</span>';
        const running = document.getElementById('running-' + css(data.tool));
        if (running) running.remove();
    } else if (evt === 'tool_start') {
        item.className += ' tool-running'; item.id = 'running-' + css(data.tool);
        item.innerHTML = '<span class="label"><span class="spinner"></span>' + escHtml(data.description||data.tool) + '</span><span class="detail">Выполняется...</span><span class="time">' + now + '</span>';
    } else if (evt === 'done') {
        item.className += ' done';
        item.innerHTML = '<span class="label">✨ ' + escHtml(data.message) + '</span><span class="time">' + now + '</span>';
    } else if (evt === 'thinking') {
        item.className += ' thinking';
        item.innerHTML = '<span class="label">💭 ' + escHtml(data.message) + '</span><span class="time">' + now + '</span>';
    } else if (evt === 'reasoning') {
        item.className += ' reasoning';
        const rid = 'reasoning-' + Date.now();
        const full = data.reasoning || '';
        const needsToggle = full.length > 150;
        item.innerHTML = '<span class="label">🧠 ' + escHtml(data.message) + '</span><div class="reasoning-content" id="' + rid + '" style="' + (needsToggle?'display:none;':'') + '">' + escHtml(full) + '</div>' + (needsToggle ? '<span class="reasoning-toggle-btn" onclick="toggleReasoningContent(\'' + rid + '\',this)">Показать (' + full.length + ' сим.)</span>' : '') + '<span class="time">' + now + '</span>';
    } else if (evt === 'stopped') {
        item.className += ' tool-error';
        item.innerHTML = '<span class="label">⏹️ ' + escHtml(data.message) + '</span><span class="time">' + now + '</span>';
    }
    activityList.appendChild(item);
    activityList.scrollTop = activityList.scrollHeight;
    updateLoadingText(data);
}

function css(s) { return (s||'').replace(/[^a-zA-Z0-9_-]/g,'_'); }
function updateLoadingText(data) {
    const sp = document.querySelector('#loading-message .loading span');
    if (!sp) return;
    if (data.tool && !data.result) sp.textContent = data.description || data.tool;
    else if (data.message) sp.textContent = data.message;
}
function finalizeActivity() { isProcessing = false; sendButton.disabled = false; stopButton.classList.remove('visible'); messageInput.disabled = false; messageInput.focus(); stopTimer(); }
async function stopExecution() {
    try {
        const resp = await fetch('/api/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId})});
        const data = await resp.json();
        if (data.success) addActivityItem({event:'stopped',message:'Запрос на остановку...'});
    } catch(e) {}
}
function clearActivity() { activityList.innerHTML = ''; if (activityEmpty) { activityList.appendChild(activityEmpty); activityEmpty.style.display = 'none'; } stepCount = 0; stepCounter.style.display = 'none'; }
function escHtml(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
function toggleReasoningContent(id, btn) { const el = document.getElementById(id); if (!el) return; if (el.style.display === 'none') { el.style.display = ''; btn.textContent = 'Скрыть'; } else { el.style.display = 'none'; btn.textContent = 'Показать'; } }

/* ── Messages ── */
function addMessage(role, content) {
    const msg = document.createElement('div');
    msg.className = 'message ' + role;
    if (role !== 'system') { const av = document.createElement('div'); av.className = 'avatar'; av.textContent = role === 'user' ? 'Вы' : 'AI'; msg.appendChild(av); }
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper';
    const cd = document.createElement('div');
    cd.className = 'message-content';
    if (role === 'assistant') cd.innerHTML = marked.parse(content); else cd.textContent = content;
    wrapper.appendChild(cd);
    if (role === 'assistant') {
        const btns = document.createElement('div');
        btns.className = 'export-btns';
        const mdBtn = document.createElement('button');
        mdBtn.className = 'export-btn';
        mdBtn.innerHTML = '📋 MD';
        mdBtn.addEventListener('click', () => copyClip(content, mdBtn));
        btns.appendChild(mdBtn);
        const htmlBtn = document.createElement('button');
        htmlBtn.className = 'export-btn';
        htmlBtn.innerHTML = '🌐 HTML';
        htmlBtn.addEventListener('click', () => copyClip(cd.innerHTML, htmlBtn));
        btns.appendChild(htmlBtn);
        wrapper.appendChild(btns);
    }
    msg.appendChild(wrapper);
    chatContainer.appendChild(msg);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function copyClip(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
        btn.classList.add('copied'); const orig = btn.innerHTML; btn.innerHTML = '✅ Готово';
        setTimeout(() => { btn.classList.remove('copied'); btn.innerHTML = orig; }, 1500);
    }).catch(() => {
        const ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
        btn.classList.add('copied'); const orig = btn.innerHTML; btn.innerHTML = '✅ Готово';
        setTimeout(() => { btn.classList.remove('copied'); btn.innerHTML = orig; }, 1500);
    });
}

function addLoading() {
    const ld = document.createElement('div'); ld.className = 'message assistant'; ld.id = 'loading-message';
    const av = document.createElement('div'); av.className = 'avatar'; av.textContent = 'AI'; ld.appendChild(av);
    const inner = document.createElement('div'); inner.className = 'loading active';
    inner.style.cssText = 'display:flex;align-items:center;gap:8px;padding:12px 16px;background:#fff;border:1px solid #e5e7eb;border-radius:14px;max-width:280px';
    inner.innerHTML = '<div style="display:flex;gap:4px"><div style="width:6px;height:6px;border-radius:50%;background:#667eea;animation:bounce 1.4s infinite ease-in-out both;animation-delay:-.32s"></div><div style="width:6px;height:6px;border-radius:50%;background:#667eea;animation:bounce 1.4s infinite ease-in-out both;animation-delay:-.16s"></div><div style="width:6px;height:6px;border-radius:50%;background:#667eea;animation:bounce 1.4s infinite ease-in-out both"></div></div><span style="color:#6b7280;font-size:13px">Анализирую...</span>';
    ld.appendChild(inner);
    chatContainer.appendChild(ld);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}
function removeLoading() { const el = document.getElementById('loading-message'); if (el) el.remove(); }

/* ── Send ── */
function sendMessage() {
    let msg = messageInput.value.trim();
    if (!msg && !pendingFileText) return;
    if (!isConnected || isProcessing) return;
    if (pendingFileText) {
        msg = (msg ? msg + '\n\n' : '') + 'Содержимое файла ' + pendingFileName + ':\n' + pendingFileText;
        clearFile();
    }
    isProcessing = true;
    addMessage('user', messageInput.value.trim() || '📄 Файл загружен');
    messageInput.value = '';
    messageInput.style.height = 'auto';
    sendButton.disabled = true;
    stopButton.classList.add('visible');
    messageInput.disabled = true;
    clearActivity();
    addLoading();
    startTimer();
    ws.send(JSON.stringify({ type: 'message', message: msg, model: selectedModel, browser_enabled: browserEnabled }));
}

sendButton.addEventListener('click', sendMessage);
stopButton.addEventListener('click', stopExecution);
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

/* ── Settings ── */
function openSettings() { document.getElementById('settingsOverlay').classList.add('visible'); loadSources(); loadTgChats(); updateConfigFields(); }
function closeSettings() { document.getElementById('settingsOverlay').classList.remove('visible'); }
document.getElementById('settingsOverlay').addEventListener('click', (e) => { if (e.target === document.getElementById('settingsOverlay')) closeSettings(); });
document.getElementById('srcNewType').addEventListener('change', updateConfigFields);

function updateConfigFields() {
    const type = document.getElementById('srcNewType').value;
    const container = document.getElementById('srcConfigFields');
    if (type === 'yougile') {
        container.innerHTML = '<input type="text" id="srcCfgToken" placeholder="API токен YouGile">';
    } else if (type === 'outline') {
        container.innerHTML = '<input type="text" id="srcCfgUrl" placeholder="URL (https://outline.example.com)"><input type="text" id="srcCfgToken" placeholder="API токен Outline">';
    }
}

function renderSourceItem(s) {
    const typeLabel = s.type === 'yougile' ? '📋 YouGile' : '📝 Outline';
    const typeCls = 'type-' + s.type;
    const urlInfo = s.config && s.config.url ? ' <span style="color:#9ca3af;font-size:11px">' + escHtml(s.config.url) + '</span>' : '';
    return '<div class="token-item"><span class="token-name">' + escHtml(s.name) + '<span class="type-badge ' + typeCls + '">' + typeLabel + '</span>' + urlInfo + '</span><label class="token-toggle"><input type="checkbox" ' + (s.enabled ? 'checked' : '') + ' onchange="toggleSource(\'' + s.id + '\',this.checked)"><span class="slider"></span></label><button class="token-delete" onclick="deleteSource(\'' + s.id + '\')" title="Удалить">✕</button></div>';
}

async function loadSources() {
    try {
        const resp = await fetch('/api/integrations');
        const data = await resp.json();
        const sources = data.sources || [];
        const intContainer = document.getElementById('srcInternal');
        const extContainer = document.getElementById('srcExternal');
        intContainer.innerHTML = '';
        extContainer.innerHTML = '';
        const internal = sources.filter(s => s.category === 'internal');
        const external = sources.filter(s => s.category === 'external');
        if (internal.length === 0) intContainer.innerHTML = '<div style="color:#9ca3af;font-size:13px;padding:8px">Нет источников</div>';
        else internal.forEach(s => intContainer.innerHTML += renderSourceItem(s));
        if (external.length === 0) extContainer.innerHTML = '<div style="color:#9ca3af;font-size:13px;padding:8px">Нет источников</div>';
        else external.forEach(s => extContainer.innerHTML += renderSourceItem(s));
    } catch(e) { console.error('loadSources error', e); }
}

async function addSource() {
    const type = document.getElementById('srcNewType').value;
    const category = document.getElementById('srcNewCat').value;
    const name = document.getElementById('srcNewName').value.trim();
    if (!name) { alert('Укажите название'); return; }
    const config = {};
    if (type === 'yougile') {
        const token = document.getElementById('srcCfgToken')?.value?.trim();
        if (!token) { alert('Укажите API токен'); return; }
        config.token = token;
    } else if (type === 'outline') {
        const url = document.getElementById('srcCfgUrl')?.value?.trim();
        const token = document.getElementById('srcCfgToken')?.value?.trim();
        if (!url || !token) { alert('Укажите URL и API токен'); return; }
        config.url = url;
        config.api_token = token;
    }
    await fetch('/api/integrations', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({type, name, category, config}) });
    document.getElementById('srcNewName').value = '';
    const cfgFields = document.getElementById('srcConfigFields');
    cfgFields.querySelectorAll('input').forEach(i => i.value = '');
    loadSources();
}

async function toggleSource(id, enabled) {
    await fetch('/api/integrations/' + id, { method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify({enabled}) });
}

async function deleteSource(id) {
    if (!confirm('Удалить источник?')) return;
    await fetch('/api/integrations/' + id, { method: 'DELETE' });
    loadSources();
}

async function loadTgChats() {
    const container = document.getElementById('tgChatsList');
    try {
        const resp = await fetch('/api/telegram/chats');
        const data = await resp.json();
        if (data.error) { container.innerHTML = '<div style="color:#9ca3af;font-size:13px;padding:8px">' + data.error + '</div>'; return; }
        container.innerHTML = '';
        (data.chats || []).forEach(c => {
            const badgeCls = c.type==='group'?'tg-badge-group':c.type==='channel'?'tg-badge-channel':'tg-badge-user';
            const typeLabel = c.type==='group'?'Группа':c.type==='channel'?'Канал':'Личный';
            const item = document.createElement('div');
            item.className = 'tg-chat-item';
            item.innerHTML = '<span class="tg-chat-title">' + escHtml(c.title) + '<span class="tg-badge ' + badgeCls + '">' + typeLabel + '</span></span><label class="token-toggle"><input type="checkbox" ' + (c.allowed?'checked':'') + ' onchange="toggleTgChat(\'' + c.id + '\',this.checked)"><span class="slider"></span></label>';
            container.appendChild(item);
        });
    } catch(e) { container.innerHTML = '<div style="color:#9ca3af;font-size:13px;padding:8px">Telegram не подключён</div>'; }
}

async function toggleTgChat(chatId, allowed) {
    await fetch('/api/telegram/toggle-chat', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({chat_id: chatId, allowed}) });
}

connect();
</script>
</body>
</html>
"""
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time chat with progress streaming
    """
    await websocket.accept()
    logger.info(f"WebSocket connection established: {session_id}")
    
    try:
        # Get agent from app state
        from src.app import agent
        
        if not agent:
            await websocket.send_json({
                "type": "error",
                "message": "Agent not initialized"
            })
            await websocket.close()
            return
        
        while True:
            # Receive message
            data = await websocket.receive_json()
            
            if data.get("type") == "message":
                message = data.get("message", "")
                model = data.get("model") or None
                browser_enabled = data.get("browser_enabled", True)
                
                if not message:
                    continue
                
                try:
                    async def on_progress(event: dict):
                        await websocket.send_json({
                            "type": "progress",
                            **event
                        })
                    
                    response = await agent.chat(
                        message, session_id,
                        on_progress=on_progress,
                        model=model,
                        browser_enabled=browser_enabled,
                    )
                    
                    await websocket.send_json({
                        "type": "response",
                        "message": response
                    })
                
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Ошибка обработки: {str(e)}"
                    })

            elif data.get("type") == "run_doc_task":
                # ── Documentation pipeline ──
                try:
                    from src.docs.pipeline import DocPipeline
                    from src.app import agent as _agent

                    if not _agent or not hasattr(_agent, "gitlab_tool"):
                        await websocket.send_json({
                            "type": "doc_error",
                            "message": "GitLab tool is not configured",
                        })
                        continue

                    outline = getattr(_agent, "outline_tool", None)
                    if not outline:
                        await websocket.send_json({
                            "type": "doc_error",
                            "message": "Outline tool is not configured",
                        })
                        continue

                    async def _doc_progress(event: dict):
                        await websocket.send_json({
                            "type": "doc_progress",
                            **event,
                        })

                    pipeline = DocPipeline(
                        gitlab_tool=_agent.gitlab_tool,
                        outline_tool=outline,
                        llm_client=_agent.llm,
                        on_progress=_doc_progress,
                    )

                    result = await pipeline.run()

                    if result.get("status") == "no_changes":
                        await websocket.send_json({
                            "type": "doc_completed",
                            "status": "no_changes",
                            "message": "Изменений не обнаружено — документация актуальна.",
                        })
                    else:
                        await websocket.send_json({
                            "type": "doc_completed",
                            "status": "success",
                            "message": (
                                f"Документация обновлена.\n"
                                f"Сервисов проанализировано: {result.get('services_count', 0)}\n"
                                f"Коммитов: {result.get('total_commits', 0)}\n"
                                f"Файлов изменено: {result.get('total_files', 0)}"
                            ),
                            "document_url": result.get("document_url"),
                            "document_title": result.get("document_title"),
                        })

                except Exception as exc:
                    logger.error(
                        "Documentation pipeline failed: %s", exc, exc_info=True
                    )
                    await websocket.send_json({
                        "type": "doc_error",
                        "message": f"Ошибка генерации документации: {str(exc)}",
                    })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}", exc_info=True)
        try:
            await websocket.close()
        except:
            pass
