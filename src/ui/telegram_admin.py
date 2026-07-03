"""Telegram session management — API + UI page."""

import logging
from typing import List
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_telegram_tool():
    from src.app import agent
    if not agent or not hasattr(agent, "telegram_tool") or not agent.telegram_tool:
        return None
    return agent.telegram_tool


# ──────────── API ────────────

@router.get("/api/telegram/status")
async def telegram_status():
    tool = _get_telegram_tool()
    if not tool:
        return JSONResponse(
            {"status": "not_configured", "error": "Telegram not configured in .env"},
            status_code=200,
        )
    return await tool.get_session_status()


@router.post("/api/telegram/send-code")
async def telegram_send_code():
    tool = _get_telegram_tool()
    if not tool:
        return JSONResponse({"success": False, "error": "Telegram not configured"}, status_code=400)
    try:
        result = await tool.send_auth_code()
        return result
    except Exception as e:
        logger.error(f"send_auth_code failed: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


class VerifyCodeRequest(BaseModel):
    code: str


@router.post("/api/telegram/verify-code")
async def telegram_verify_code(req: VerifyCodeRequest):
    tool = _get_telegram_tool()
    if not tool:
        return JSONResponse({"success": False, "error": "Telegram not configured"}, status_code=400)
    return await tool.verify_code(req.code)


class Verify2FARequest(BaseModel):
    password: str


@router.post("/api/telegram/verify-2fa")
async def telegram_verify_2fa(req: Verify2FARequest):
    tool = _get_telegram_tool()
    if not tool:
        return JSONResponse({"success": False, "error": "Telegram not configured"}, status_code=400)
    return await tool.verify_2fa(req.password)


@router.post("/api/telegram/reconnect")
async def telegram_reconnect():
    tool = _get_telegram_tool()
    if not tool:
        return JSONResponse({"success": False, "error": "Telegram not configured"}, status_code=400)
    return await tool.reconnect()


@router.post("/api/telegram/disconnect")
async def telegram_disconnect():
    tool = _get_telegram_tool()
    if not tool:
        return JSONResponse({"success": False, "error": "Telegram not configured"}, status_code=400)
    await tool.disconnect()
    return {"success": True}


@router.get("/api/telegram/dialogs")
async def telegram_list_dialogs():
    """List ALL dialogs for diagnostics (no allowed_chats filter)."""
    tool = _get_telegram_tool()
    if not tool:
        return JSONResponse({"error": "Telegram not configured"}, status_code=400)
    try:
        client = await tool._get_client()
        dialogs = []
        async for d in client.iter_dialogs(limit=50):
            dialogs.append({
                "id": d.id,
                "title": d.title,
                "type": "group" if d.is_group else "channel" if d.is_channel else "user",
                "username": getattr(d.entity, "username", None),
            })
        return {"count": len(dialogs), "dialogs": dialogs}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/telegram/destroy-session")
async def telegram_destroy_session():
    tool = _get_telegram_tool()
    if not tool:
        return JSONResponse({"success": False, "error": "Telegram not configured"}, status_code=400)
    return await tool.destroy_session()


# ──────────── ALLOWED CHATS API ────────────

@router.get("/api/telegram/chats")
async def telegram_list_chats():
    """List all dialogs with allowed/not-allowed flag."""
    tool = _get_telegram_tool()
    if not tool:
        return JSONResponse({"error": "Telegram not configured"}, status_code=400)
    try:
        client = await tool._get_client()
        allowed = set(str(c).strip() for c in tool.allowed_chats)
        chats = []
        async for d in client.iter_dialogs(limit=50):
            chats.append({
                "id": d.id,
                "title": d.title,
                "type": "group" if d.is_group else "channel" if d.is_channel else "user",
                "username": getattr(d.entity, "username", None),
                "allowed": str(d.id) in allowed,
            })
        return {"chats": chats, "allowed_ids": list(allowed)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


class AllowedChatsRequest(BaseModel):
    chat_ids: List[str]


@router.post("/api/telegram/allowed-chats")
async def telegram_set_allowed_chats(req: AllowedChatsRequest):
    """Replace the entire allowed chats list."""
    tool = _get_telegram_tool()
    if not tool:
        return JSONResponse({"error": "Telegram not configured"}, status_code=400)
    tool.set_allowed_chats(req.chat_ids)
    return {"success": True, "count": len(tool.allowed_chats), "allowed": tool.allowed_chats}


class ToggleChatRequest(BaseModel):
    chat_id: str
    allowed: bool


@router.post("/api/telegram/toggle-chat")
async def telegram_toggle_chat(req: ToggleChatRequest):
    """Add or remove a single chat from the allowed list."""
    tool = _get_telegram_tool()
    if not tool:
        return JSONResponse({"error": "Telegram not configured"}, status_code=400)
    if req.allowed:
        tool.add_allowed_chat(req.chat_id)
    else:
        tool.remove_allowed_chat(req.chat_id)
    return {"success": True, "allowed": tool.get_allowed_chats()}


# ──────────── UI PAGE ────────────

@router.get("/ui/telegram", response_class=HTMLResponse)
async def telegram_admin_page():
    return HTMLResponse(_TELEGRAM_ADMIN_HTML)


_TELEGRAM_ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Telegram Admin — Team Assistant</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;justify-content:center;padding:40px 16px}
.container{width:520px;max-width:100%;display:flex;flex-direction:column;gap:20px}
.card{background:#fff;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,.3);overflow:hidden}
.card-header{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:20px 28px;display:flex;justify-content:space-between;align-items:center}
.card-header h1{font-size:20px;font-weight:600}
.card-header a{color:rgba(255,255,255,.8);text-decoration:none;font-size:13px;transition:color .2s}
.card-header a:hover{color:#fff}
.card-body{padding:28px}
.status-box{display:flex;align-items:center;gap:12px;padding:16px;border-radius:12px;margin-bottom:20px;font-size:14px}
.status-box.connected{background:#dcfce7;color:#166534}
.status-box.disconnected{background:#fef3c7;color:#92400e}
.status-box.error{background:#fee2e2;color:#991b1b}
.status-box.loading{background:#e0e7ff;color:#3730a3}
.dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.connected .dot{background:#22c55e}
.disconnected .dot{background:#f59e0b}
.error .dot{background:#ef4444}
.loading .dot{background:#6366f1;animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.info-row{display:flex;justify-content:space-between;padding:8px 0;font-size:14px;border-bottom:1px solid #f3f4f6}
.info-row:last-child{border-bottom:none}
.info-label{color:#6b7280;font-weight:500}
.info-value{color:#111827;font-weight:600}
.actions{display:flex;flex-direction:column;gap:10px;margin-top:24px}
.btn{padding:12px 20px;border:none;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;transition:all .2s;text-align:center}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-primary{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff}
.btn-primary:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 4px 12px rgba(102,126,234,.4)}
.btn-danger{background:#fee2e2;color:#dc2626}
.btn-danger:hover:not(:disabled){background:#fecaca}
.btn-secondary{background:#f3f4f6;color:#374151}
.btn-secondary:hover:not(:disabled){background:#e5e7eb}
.btn-row{display:flex;gap:10px}
.btn-row .btn{flex:1}
.input-group{margin-bottom:16px}
.input-group label{display:block;font-size:13px;color:#6b7280;margin-bottom:6px;font-weight:500}
.input-group input{width:100%;padding:12px 16px;border:2px solid #e5e7eb;border-radius:10px;font-size:16px;letter-spacing:3px;text-align:center;transition:border-color .2s;outline:none}
.input-group input:focus{border-color:#667eea}
.hidden{display:none}
.msg{padding:12px 16px;border-radius:10px;margin-bottom:16px;font-size:13px}
.msg.success{background:#dcfce7;color:#166534}
.msg.error{background:#fee2e2;color:#991b1b}
.spinner{display:inline-block;width:16px;height:16px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite;margin-right:6px;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
/* Chats section */
.section-title{font-size:16px;font-weight:600;color:#111827;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.chat-list{display:flex;flex-direction:column;gap:8px}
.chat-item{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-radius:12px;background:#f9fafb;transition:background .2s}
.chat-item:hover{background:#f3f4f6}
.chat-info{display:flex;flex-direction:column;gap:2px;flex:1;min-width:0}
.chat-title{font-size:14px;font-weight:600;color:#111827;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-meta{font-size:12px;color:#6b7280}
.chat-toggle{position:relative;width:44px;height:24px;flex-shrink:0;margin-left:12px}
.chat-toggle input{opacity:0;width:0;height:0}
.chat-toggle .slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#d1d5db;border-radius:12px;transition:.3s}
.chat-toggle .slider:before{position:absolute;content:"";height:18px;width:18px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.3s}
.chat-toggle input:checked + .slider{background:#667eea}
.chat-toggle input:checked + .slider:before{transform:translateX(20px)}
.chats-empty{text-align:center;padding:24px;color:#9ca3af;font-size:14px}
.chats-loading{text-align:center;padding:24px;color:#6366f1;font-size:14px}
.badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;text-transform:uppercase}
.badge-group{background:#dbeafe;color:#1d4ed8}
.badge-channel{background:#fef3c7;color:#92400e}
.badge-user{background:#e0e7ff;color:#4338ca}
</style>
</head>
<body>
<div class="container">

<!-- SESSION CARD -->
<div class="card">
  <div class="card-header">
    <h1>📱 Telegram Session</h1>
    <a href="/ui">&larr; Назад к чату</a>
  </div>
  <div class="card-body">
    <div id="msg" class="msg hidden"></div>
    <div id="status-box" class="status-box loading">
      <div class="dot"></div>
      <span>Проверяем сессию...</span>
    </div>
    <div id="info-block" class="hidden"></div>

    <div id="auth-step-code" class="hidden">
      <div class="input-group">
        <label>Код подтверждения из Telegram</label>
        <input type="text" id="auth-code" maxlength="6" placeholder="12345" autofocus>
      </div>
      <button class="btn btn-primary" onclick="verifyCode()">Подтвердить код</button>
    </div>

    <div id="auth-step-2fa" class="hidden">
      <div class="input-group">
        <label>Пароль двухфакторной аутентификации</label>
        <input type="password" id="auth-2fa" placeholder="Пароль">
      </div>
      <button class="btn btn-primary" onclick="verify2FA()">Подтвердить</button>
    </div>

    <div id="actions" class="actions hidden"></div>
  </div>
</div>

<!-- CHATS CARD -->
<div class="card">
  <div class="card-header">
    <h1>💬 Разрешённые чаты</h1>
    <span id="chats-count" style="color:rgba(255,255,255,.8);font-size:13px"></span>
  </div>
  <div class="card-body">
    <div id="chats-msg" class="msg hidden"></div>
    <div id="chats-container">
      <div class="chats-loading">Загрузка чатов...</div>
    </div>
  </div>
</div>

</div>

<script>
const API = '';

function $(id) { return document.getElementById(id); }

function showMsg(text, type) {
  const el = $('msg');
  el.textContent = text;
  el.className = 'msg ' + type;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 6000);
}

function showChatsMsg(text, type) {
  const el = $('chats-msg');
  el.textContent = text;
  el.className = 'msg ' + type;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 4000);
}

function setStatus(cls, text) {
  const box = $('status-box');
  box.className = 'status-box ' + cls;
  box.innerHTML = '<div class="dot"></div><span>' + text + '</span>';
}

function showInfo(data) {
  const block = $('info-block');
  let html = '';
  if (data.user) html += infoRow('Пользователь', data.user);
  if (data.username) html += infoRow('Username', '@' + data.username);
  if (data.phone) html += infoRow('Телефон', data.phone);
  block.innerHTML = html;
  block.classList.toggle('hidden', !html);
}

function infoRow(label, value) {
  return '<div class="info-row"><span class="info-label">' + label + '</span><span class="info-value">' + value + '</span></div>';
}

function showActions(buttons) {
  const el = $('actions');
  el.innerHTML = buttons.map(b =>
    '<button class="btn ' + b.cls + '"' + (b.id ? ' id="'+b.id+'"' : '') + ' onclick="' + b.action + '">' + b.label + '</button>'
  ).join('');
  el.classList.remove('hidden');
}

function hideAuth() {
  $('auth-step-code').classList.add('hidden');
  $('auth-step-2fa').classList.add('hidden');
}

async function apiPost(path, body) {
  const opts = {method: 'POST', headers: {'Content-Type':'application/json'}};
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  return res.json();
}

async function checkStatus() {
  setStatus('loading', 'Проверяем сессию...');
  hideAuth();
  try {
    const data = await (await fetch(API + '/api/telegram/status')).json();

    if (data.status === 'connected' || data.status === 'session_valid') {
      setStatus('connected', 'Подключено');
      showInfo(data);
      showActions([
        {label: 'Переподключить', cls: 'btn-secondary', action: 'doReconnect()'},
        {label: 'Новая сессия', cls: 'btn-primary', action: 'startAuth()'},
        {label: 'Удалить сессию', cls: 'btn-danger', action: 'destroySession()'},
      ]);
      loadChats();
    } else if (data.status === 'session_expired') {
      setStatus('disconnected', 'Сессия истекла');
      showInfo({});
      showActions([
        {label: 'Переподключить', cls: 'btn-secondary', action: 'doReconnect()'},
        {label: 'Новая авторизация', cls: 'btn-primary', action: 'startAuth()'},
        {label: 'Удалить сессию', cls: 'btn-danger', action: 'destroySession()'},
      ]);
    } else if (data.status === 'no_session') {
      setStatus('disconnected', 'Нет сессии');
      showInfo({});
      showActions([
        {label: 'Авторизоваться', cls: 'btn-primary', action: 'startAuth()'},
      ]);
    } else if (data.status === 'not_configured') {
      setStatus('error', 'Telegram не настроен в .env');
      showInfo({});
      $('actions').classList.add('hidden');
    } else {
      setStatus('error', data.error || 'Ошибка');
      showInfo({});
      showActions([
        {label: 'Новая авторизация', cls: 'btn-primary', action: 'startAuth()'},
        {label: 'Удалить сессию', cls: 'btn-danger', action: 'destroySession()'},
      ]);
    }
  } catch (e) {
    setStatus('error', 'Сервер недоступен');
  }
}

async function loadChats() {
  const container = $('chats-container');
  container.innerHTML = '<div class="chats-loading">Загрузка чатов...</div>';
  try {
    const data = await (await fetch(API + '/api/telegram/chats')).json();
    if (data.error) {
      container.innerHTML = '<div class="chats-empty">' + data.error + '</div>';
      return;
    }
    const chats = data.chats || [];
    if (chats.length === 0) {
      container.innerHTML = '<div class="chats-empty">Нет доступных чатов</div>';
      $('chats-count').textContent = '';
      return;
    }
    const allowedCount = chats.filter(c => c.allowed).length;
    $('chats-count').textContent = allowedCount + ' из ' + chats.length;
    let html = '<div class="chat-list">';
    for (const c of chats) {
      const badgeCls = c.type === 'group' ? 'badge-group' : c.type === 'channel' ? 'badge-channel' : 'badge-user';
      const typeLabel = c.type === 'group' ? 'Группа' : c.type === 'channel' ? 'Канал' : 'Личный';
      html += '<div class="chat-item">';
      html += '<div class="chat-info">';
      html += '<div class="chat-title">' + escHtml(c.title) + '</div>';
      html += '<div class="chat-meta"><span class="badge ' + badgeCls + '">' + typeLabel + '</span> ID: ' + c.id + '</div>';
      html += '</div>';
      html += '<label class="chat-toggle"><input type="checkbox" data-chat-id="' + c.id + '"' + (c.allowed ? ' checked' : '') + ' onchange="toggleChat(this)"><span class="slider"></span></label>';
      html += '</div>';
    }
    html += '</div>';
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<div class="chats-empty">Ошибка загрузки: ' + e.message + '</div>';
  }
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

async function toggleChat(el) {
  const chatId = el.getAttribute('data-chat-id');
  const allowed = el.checked;
  el.disabled = true;
  try {
    const data = await apiPost('/api/telegram/toggle-chat', {chat_id: chatId, allowed});
    if (data.success) {
      const count = (data.allowed || []).length;
      const total = document.querySelectorAll('.chat-toggle input').length;
      $('chats-count').textContent = count + ' из ' + total;
      showChatsMsg(allowed ? 'Чат добавлен в разрешённые' : 'Чат удалён из разрешённых', 'success');
    } else {
      el.checked = !allowed;
      showChatsMsg(data.error || 'Ошибка', 'error');
    }
  } catch (e) {
    el.checked = !allowed;
    showChatsMsg('Ошибка сети', 'error');
  }
  el.disabled = false;
}

async function startAuth() {
  setStatus('loading', 'Отправляем код...');
  $('actions').classList.add('hidden');
  hideAuth();
  try {
    const data = await apiPost('/api/telegram/send-code');
    if (data.success) {
      setStatus('disconnected', 'Код отправлен — проверьте Telegram');
      $('auth-step-code').classList.remove('hidden');
      $('auth-code').value = '';
      $('auth-code').focus();
    } else {
      showMsg(data.error || 'Не удалось отправить код', 'error');
      checkStatus();
    }
  } catch (e) {
    showMsg('Ошибка сети', 'error');
    checkStatus();
  }
}

async function verifyCode() {
  const code = $('auth-code').value.trim();
  if (!code) return;
  setStatus('loading', 'Проверяем код...');
  try {
    const data = await apiPost('/api/telegram/verify-code', {code});
    if (data.success) {
      showMsg('Авторизация успешна: ' + data.user, 'success');
      hideAuth();
      checkStatus();
    } else if (data.needs_2fa) {
      setStatus('disconnected', 'Требуется пароль 2FA');
      hideAuth();
      $('auth-step-2fa').classList.remove('hidden');
      $('auth-2fa').focus();
    } else {
      showMsg(data.error || 'Неверный код', 'error');
      setStatus('disconnected', 'Попробуйте ещё раз');
    }
  } catch (e) {
    showMsg('Ошибка сети', 'error');
  }
}

async function verify2FA() {
  const pw = $('auth-2fa').value.trim();
  if (!pw) return;
  setStatus('loading', 'Проверяем пароль...');
  try {
    const data = await apiPost('/api/telegram/verify-2fa', {password: pw});
    if (data.success) {
      showMsg('Авторизация успешна: ' + data.user, 'success');
      hideAuth();
      checkStatus();
    } else {
      showMsg(data.error || 'Неверный пароль', 'error');
      setStatus('disconnected', 'Попробуйте ещё раз');
    }
  } catch (e) {
    showMsg('Ошибка сети', 'error');
  }
}

async function doReconnect() {
  setStatus('loading', 'Переподключаемся...');
  try {
    const data = await apiPost('/api/telegram/reconnect');
    if (data.success) {
      showMsg('Переподключено: ' + data.user, 'success');
    } else {
      showMsg(data.error || 'Не удалось переподключиться', 'error');
    }
  } catch (e) {
    showMsg('Ошибка сети', 'error');
  }
  checkStatus();
}

async function destroySession() {
  if (!confirm('Удалить сессию? Потребуется повторная авторизация.')) return;
  setStatus('loading', 'Удаляем...');
  try {
    await apiPost('/api/telegram/destroy-session');
    showMsg('Сессия удалена', 'success');
  } catch (e) {
    showMsg('Ошибка', 'error');
  }
  checkStatus();
}

document.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    if (!$('auth-step-code').classList.contains('hidden')) verifyCode();
    if (!$('auth-step-2fa').classList.contains('hidden')) verify2FA();
  }
});

checkStatus();
</script>
</body>
</html>
"""
