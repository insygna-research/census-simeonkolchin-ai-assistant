"""
Telegram Tool - Integration with Telegram API using Telethon
"""

import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class TelegramTool:
    """Tool for reading messages from Telegram chats"""
    
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        phone: str,
        session_path: str = "./data/sessions",
        allowed_chats: Optional[List[str]] = None
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.session_path = Path(session_path)
        self.allowed_chats = allowed_chats or []
        self._allowed_chats_file = self.session_path.parent / "allowed_chats.json"
        self._load_allowed_chats()
        self._client = None
        self._me = None
        self._initialized = False
        self._phone_code_hash = None

    # ── Allowed chats persistence ──

    def _load_allowed_chats(self):
        """Overlay persisted allowed_chats on top of .env defaults."""
        if self._allowed_chats_file.exists():
            try:
                data = json.loads(self._allowed_chats_file.read_text())
                if isinstance(data, list):
                    self.allowed_chats = [str(c) for c in data]
                    logger.info(f"Loaded {len(self.allowed_chats)} allowed chats from {self._allowed_chats_file}")
            except Exception as e:
                logger.warning(f"Failed to load allowed_chats.json: {e}")

    def _save_allowed_chats(self):
        """Persist current allowed_chats to a JSON file."""
        try:
            self._allowed_chats_file.parent.mkdir(parents=True, exist_ok=True)
            self._allowed_chats_file.write_text(json.dumps(self.allowed_chats, ensure_ascii=False, indent=2))
            logger.info(f"Saved {len(self.allowed_chats)} allowed chats to {self._allowed_chats_file}")
        except Exception as e:
            logger.error(f"Failed to save allowed_chats.json: {e}")

    def get_allowed_chats(self) -> List[str]:
        return list(self.allowed_chats)

    def set_allowed_chats(self, chat_ids: List[str]):
        self.allowed_chats = [str(c).strip() for c in chat_ids if str(c).strip()]
        self._save_allowed_chats()

    def add_allowed_chat(self, chat_id: str) -> bool:
        chat_id = str(chat_id).strip()
        if chat_id not in self.allowed_chats:
            self.allowed_chats.append(chat_id)
            self._save_allowed_chats()
            return True
        return False

    def remove_allowed_chat(self, chat_id: str) -> bool:
        chat_id = str(chat_id).strip()
        if chat_id in self.allowed_chats:
            self.allowed_chats.remove(chat_id)
            self._save_allowed_chats()
            return True
        return False

    # ── Telegram client ──

    async def _get_client(self):
        """Get or create Telegram client (non-interactive)."""
        if self._client is None:
            try:
                from telethon import TelegramClient

                self.session_path.mkdir(parents=True, exist_ok=True)
                session_file = self.session_path / "telegram_session"

                self._client = TelegramClient(
                    str(session_file),
                    self.api_id,
                    self.api_hash
                )

                await self._client.connect()

                if not await self._client.is_user_authorized():
                    logger.warning("Telegram session not authorized — use /ui/telegram to authenticate")
                    await self._client.disconnect()
                    self._client = None
                    raise RuntimeError(
                        "Telegram session not authorized. "
                        "Open /ui/telegram to create or renew the session."
                    )

                self._me = await self._client.get_me()
                self._initialized = True
                logger.info(f"Telegram client initialized for {self._me.first_name}")

            except ImportError:
                logger.error("telethon not installed. Run: pip install telethon")
                raise
            except RuntimeError:
                raise
            except Exception as e:
                logger.error(f"Failed to initialize Telegram client: {e}")
                self._client = None
                raise

        return self._client
    
    def _is_chat_allowed(self, chat_id: str) -> bool:
        """Check if chat is in allowed list"""
        if not self.allowed_chats:
            return True
        
        chat_id_str = str(chat_id).lower()
        
        for allowed in self.allowed_chats:
            allowed_str = str(allowed).lower().strip()
            if allowed_str == chat_id_str:
                return True
            if allowed_str.lstrip('@') == chat_id_str.lstrip('@'):
                return True
            if chat_id_str.startswith('-100') and allowed_str == chat_id_str[4:]:
                return True
            if allowed_str.startswith('-100') and chat_id_str == allowed_str[4:]:
                return True
        
        return False
    
    async def _resolve_entity(self, chat_identifier: str):
        """Resolve chat entity from various formats"""
        client = await self._get_client()
        
        if chat_identifier.startswith('@'):
            return await client.get_entity(chat_identifier)
        
        if 't.me/' in chat_identifier:
            parts = chat_identifier.split('t.me/')[-1].split('/')
            if parts[0].startswith('+'):
                return await client.get_entity(chat_identifier)
            elif parts[0].startswith('c'):
                chat_id = int('-100' + parts[1]) if len(parts) > 1 else int('-100' + parts[0][1:])
                return await client.get_entity(chat_id)
            else:
                return await client.get_entity('@' + parts[0])
        
        try:
            chat_id = int(chat_identifier)
            return await client.get_entity(chat_id)
        except ValueError:
            pass
        
        return await client.get_entity(chat_identifier)
    
    async def list_chats(self) -> Dict[str, Any]:
        """List allowed chats/dialogs"""
        try:
            client = await self._get_client()
            
            dialogs = []
            async for dialog in client.iter_dialogs(limit=100):
                chat_id = str(dialog.id)
                
                if self.allowed_chats and not self._is_chat_allowed(chat_id):
                    title_match = any(
                        allowed.lower() in dialog.title.lower()
                        for allowed in self.allowed_chats
                    )
                    username = getattr(dialog.entity, 'username', None)
                    username_match = username and any(
                        allowed.lower().lstrip('@') == username.lower()
                        for allowed in self.allowed_chats
                    )
                    if not title_match and not username_match:
                        continue
                
                chat_type = "unknown"
                if dialog.is_user:
                    chat_type = "user"
                elif dialog.is_group:
                    chat_type = "group"
                elif dialog.is_channel:
                    chat_type = "channel"
                
                dialogs.append({
                    'id': dialog.id,
                    'title': dialog.title,
                    'type': chat_type,
                    'username': getattr(dialog.entity, 'username', None),
                    'unread_count': dialog.unread_count,
                    'last_message_date': dialog.date.isoformat() if dialog.date else None
                })
            
            return {
                "success": True,
                "count": len(dialogs),
                "chats": dialogs
            }
        except Exception as e:
            logger.error(f"Failed to list chats: {e}")
            return {"error": f"Failed to list chats: {str(e)}"}
    
    async def get_messages(
        self,
        chat_id: str,
        limit: int = 50,
        days: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get messages from a chat"""
        try:
            if not self._is_chat_allowed(chat_id):
                return {"error": f"Chat {chat_id} is not in allowed list"}
            
            client = await self._get_client()
            entity = await self._resolve_entity(chat_id)
            
            kwargs = {'limit': limit}
            if days:
                offset_date = datetime.utcnow() - timedelta(days=days)
                kwargs['offset_date'] = offset_date
            
            messages = []
            async for msg in client.iter_messages(entity, **kwargs):
                sender_name = "Unknown"
                if msg.sender:
                    if hasattr(msg.sender, 'first_name'):
                        sender_name = f"{msg.sender.first_name or ''} {msg.sender.last_name or ''}".strip()
                    elif hasattr(msg.sender, 'title'):
                        sender_name = msg.sender.title
                
                messages.append({
                    'id': msg.id,
                    'date': msg.date.isoformat() if msg.date else None,
                    'sender_id': msg.sender_id,
                    'sender_name': sender_name,
                    'text': msg.text or '',
                    'is_reply': msg.is_reply,
                    'reply_to_msg_id': msg.reply_to_msg_id,
                    'has_media': msg.media is not None
                })
            
            return {
                "success": True,
                "chat_id": str(entity.id),
                "chat_title": getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown')),
                "count": len(messages),
                "messages": messages
            }
        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
            return {"error": f"Failed to get messages: {str(e)}"}
    
    async def search_messages(
        self,
        chat_id: str,
        query: str,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Search for messages in a chat"""
        try:
            if not self._is_chat_allowed(chat_id):
                return {"error": f"Chat {chat_id} is not in allowed list"}
            
            client = await self._get_client()
            entity = await self._resolve_entity(chat_id)
            
            messages = []
            async for msg in client.iter_messages(entity, search=query, limit=limit):
                sender_name = "Unknown"
                if msg.sender:
                    if hasattr(msg.sender, 'first_name'):
                        sender_name = f"{msg.sender.first_name or ''} {msg.sender.last_name or ''}".strip()
                    elif hasattr(msg.sender, 'title'):
                        sender_name = msg.sender.title
                
                messages.append({
                    'id': msg.id,
                    'date': msg.date.isoformat() if msg.date else None,
                    'sender_name': sender_name,
                    'text': msg.text or '',
                    'has_media': msg.media is not None
                })
            
            return {
                "success": True,
                "chat_id": str(entity.id),
                "query": query,
                "count": len(messages),
                "messages": messages
            }
        except Exception as e:
            logger.error(f"Failed to search messages: {e}")
            return {"error": f"Failed to search messages: {str(e)}"}
    
    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Get information about a chat"""
        try:
            if not self._is_chat_allowed(chat_id):
                return {"error": f"Chat {chat_id} is not in allowed list"}
            
            client = await self._get_client()
            entity = await self._resolve_entity(chat_id)
            full = await client.get_entity(entity)
            
            info = {
                'id': full.id,
                'title': getattr(full, 'title', None) or getattr(full, 'first_name', 'Unknown'),
                'username': getattr(full, 'username', None),
                'type': 'unknown'
            }
            
            if hasattr(full, 'megagroup') and full.megagroup:
                info['type'] = 'supergroup'
            elif hasattr(full, 'broadcast') and full.broadcast:
                info['type'] = 'channel'
            elif hasattr(full, 'gigagroup') and full.gigagroup:
                info['type'] = 'gigagroup'
            elif hasattr(full, 'first_name'):
                info['type'] = 'user'
            else:
                info['type'] = 'group'
            
            if hasattr(full, 'participants_count'):
                info['members_count'] = full.participants_count
            if hasattr(full, 'about'):
                info['description'] = full.about
            
            return {
                "success": True,
                "chat": info
            }
        except Exception as e:
            logger.error(f"Failed to get chat info: {e}")
            return {"error": f"Failed to get chat info: {str(e)}"}
    
    async def send_message(
        self,
        chat_id: str,
        message: str,
        reply_to: Optional[int] = None
    ) -> Dict[str, Any]:
        """Send a message to an allowed Telegram chat"""
        try:
            if not self._is_chat_allowed(chat_id):
                return {"error": f"Chat {chat_id} is not in allowed list. Sending is only permitted to allowed chats."}
            
            client = await self._get_client()
            entity = await self._resolve_entity(chat_id)
            
            kwargs = {}
            if reply_to:
                kwargs['reply_to'] = reply_to
            
            sent = await client.send_message(entity, message, **kwargs)
            
            chat_title = getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown'))
            
            logger.info(f"Message sent to {chat_title} (ID: {entity.id})")
            
            return {
                "success": True,
                "message_id": sent.id,
                "chat_id": str(entity.id),
                "chat_title": chat_title,
                "message": f"Сообщение отправлено в '{chat_title}'"
            }
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return {"error": f"Failed to send message: {str(e)}"}

    # ── Session management ──

    async def get_session_status(self) -> dict:
        """Return current Telegram session status without triggering full auth."""
        from telethon import TelegramClient

        self.session_path.mkdir(parents=True, exist_ok=True)
        session_file = self.session_path / "telegram_session"
        session_exists = (self.session_path / "telegram_session.session").exists()

        if self._client and self._initialized:
            try:
                me = await self._client.get_me()
                if me:
                    return {
                        "status": "connected",
                        "user": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                        "username": me.username,
                        "phone": me.phone,
                        "session_file": session_exists,
                    }
            except Exception:
                pass

        if not session_exists:
            return {"status": "no_session", "session_file": False}

        tmp = TelegramClient(str(session_file), self.api_id, self.api_hash)
        try:
            await tmp.connect()
            if await tmp.is_user_authorized():
                me = await tmp.get_me()
                await tmp.disconnect()
                return {
                    "status": "session_valid",
                    "user": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                    "username": me.username,
                    "phone": me.phone,
                    "session_file": True,
                }
            await tmp.disconnect()
            return {"status": "session_expired", "session_file": True}
        except Exception as e:
            try:
                await tmp.disconnect()
            except Exception:
                pass
            return {"status": "error", "error": str(e), "session_file": session_exists}

    async def send_auth_code(self) -> dict:
        """Send verification code to the configured phone number."""
        from telethon import TelegramClient

        await self.disconnect()

        self.session_path.mkdir(parents=True, exist_ok=True)
        session_file = self.session_path / "telegram_session"

        self._client = TelegramClient(str(session_file), self.api_id, self.api_hash)
        await self._client.connect()

        result = await self._client.send_code_request(self.phone)
        self._phone_code_hash = result.phone_code_hash
        return {"success": True, "phone_code_hash": result.phone_code_hash}

    async def verify_code(self, code: str) -> dict:
        """Verify the auth code. Returns status indicating success or 2FA required."""
        if not self._client:
            return {"success": False, "error": "No pending auth — call send_auth_code first"}

        from telethon.errors import SessionPasswordNeededError
        try:
            await self._client.sign_in(
                self.phone, code, phone_code_hash=self._phone_code_hash
            )
            me = await self._client.get_me()
            self._me = me
            self._initialized = True
            return {
                "success": True,
                "user": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                "username": me.username,
            }
        except SessionPasswordNeededError:
            return {"success": False, "needs_2fa": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def verify_2fa(self, password: str) -> dict:
        """Verify 2FA password to complete sign-in."""
        if not self._client:
            return {"success": False, "error": "No pending auth"}

        try:
            await self._client.sign_in(password=password)
            me = await self._client.get_me()
            self._me = me
            self._initialized = True
            return {
                "success": True,
                "user": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                "username": me.username,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def reconnect(self) -> dict:
        """Reconnect using existing session file (no interactive auth)."""
        from telethon import TelegramClient

        await self.disconnect()

        self.session_path.mkdir(parents=True, exist_ok=True)
        session_file = self.session_path / "telegram_session"

        try:
            client = TelegramClient(str(session_file), self.api_id, self.api_hash)
            await client.connect()

            if not await client.is_user_authorized():
                await client.disconnect()
                return {"success": False, "error": "Сессия невалидна — требуется новая авторизация"}

            me = await client.get_me()
            self._client = client
            self._me = me
            self._initialized = True
            return {
                "success": True,
                "user": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                "username": me.username,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def destroy_session(self) -> dict:
        """Disconnect and delete the session file."""
        await self.disconnect()
        session_file = self.session_path / "telegram_session.session"
        if session_file.exists():
            session_file.unlink()
        return {"success": True}

    async def disconnect(self):
        """Disconnect the Telegram client"""
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._initialized = False
            self._me = None


# Tool definitions for the agent
TELEGRAM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "telegram_list_chats",
            "description": "Получить список доступных Telegram чатов и групп. Показывает только чаты из разрешённого списка.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "telegram_get_messages",
            "description": "Получить сообщения из Telegram чата. Можно указать количество сообщений или период в днях.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "ID чата, username (@username) или ссылка (t.me/...)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество сообщений (по умолчанию 50)",
                        "default": 50
                    },
                    "days": {
                        "type": "integer",
                        "description": "Получить сообщения за последние N дней"
                    }
                },
                "required": ["chat_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "telegram_search_messages",
            "description": "Поиск сообщений в Telegram чате по тексту.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "ID чата, username или ссылка"
                    },
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество результатов (по умолчанию 20)",
                        "default": 20
                    }
                },
                "required": ["chat_id", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "telegram_get_chat_info",
            "description": "Получить информацию о Telegram чате (тип, количество участников, описание).",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "ID чата, username или ссылка"
                    }
                },
                "required": ["chat_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "telegram_send_message",
            "description": "Отправить сообщение в разрешённый Telegram чат. Можно ответить на конкретное сообщение через reply_to.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": "ID чата, username (@username) или ссылка (t.me/...)"
                    },
                    "message": {
                        "type": "string",
                        "description": "Текст сообщения (поддерживает markdown)"
                    },
                    "reply_to": {
                        "type": "integer",
                        "description": "ID сообщения, на которое нужно ответить (опционально)"
                    }
                },
                "required": ["chat_id", "message"]
            }
        }
    }
]
