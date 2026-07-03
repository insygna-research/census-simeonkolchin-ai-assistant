"""
iCloud Tool — интеграция с iCloud Календарём и Напоминаниями через CalDAV.

Авторизация — Apple ID + пароль приложения (app-specific password,
appleid.apple.com → Безопасность → Пароли приложений). Двухфакторка при этом
не мешает, поэтому подходит для запуска на сервере: доступ полностью по кредам.

Заметки (Apple Notes) сознательно не поддержаны: у Apple нет API для Notes,
а CalDAV/IMAP современные заметки не отдают. Сценарий «заметка» закрывается
напоминанием с текстом в поле notes.
"""

import uuid
import asyncio
import logging
from datetime import datetime, timedelta, date, timezone
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

logger = logging.getLogger(__name__)


class ICloudTool:
    """CalDAV-клиент к iCloud для календаря и напоминаний."""

    def __init__(
        self,
        username: str,
        password: str,
        caldav_url: str = "https://caldav.icloud.com",
        tz_name: str = "Europe/Moscow",
        verify_ssl: bool = True,
    ) -> None:
        self.username = username
        self.password = password
        self.caldav_url = caldav_url
        self.tz_name = tz_name
        self.verify_ssl = verify_ssl
        self._principal = None  # lazy

    # ---------- низкоуровневое ----------

    def _get_principal(self):
        """Ленивое подключение к CalDAV (кешируется в пределах процесса)."""
        if self._principal is not None:
            return self._principal
        import caldav

        client = caldav.DAVClient(
            url=self.caldav_url,
            username=self.username,
            password=self.password,
            ssl_verify_cert=self.verify_ssl,
        )
        self._principal = client.principal()
        return self._principal

    @staticmethod
    def _supports(cal, component: str) -> bool:
        try:
            return component in (cal.get_supported_components() or [])
        except Exception:
            # Если сервер не сообщил компоненты — считаем, что поддерживает.
            return True

    def _find_calendar(self, name: Optional[str], component: str):
        """Найти календарь/список по имени или взять первый, поддерживающий компонент."""
        principal = self._get_principal()
        calendars = principal.calendars()
        matches = [c for c in calendars if self._supports(c, component)]
        if name:
            wanted = name.strip().lower()
            for c in matches or calendars:
                try:
                    if (c.name or "").strip().lower() == wanted:
                        return c
                except Exception:
                    continue
            raise ValueError(f"Календарь/список '{name}' не найден")
        if not matches:
            raise ValueError(f"Нет календаря, поддерживающего {component}")
        return matches[0]

    def _tz(self):
        if ZoneInfo is not None:
            try:
                return ZoneInfo(self.tz_name)
            except Exception:
                pass
        return timezone.utc

    def _parse_dt(self, value: Any) -> datetime:
        """Разобрать ISO-строку в tz-aware datetime; наивное время локализуем."""
        if isinstance(value, datetime):
            dt = value
        else:
            s = str(value).strip().replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(s)
            except ValueError:
                d = date.fromisoformat(s[:10])
                dt = datetime(d.year, d.month, d.day)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self._tz())
        return dt

    # ---------- парсинг компонентов ----------

    @staticmethod
    def _ical_value(comp, key: str) -> Optional[str]:
        val = comp.get(key)
        if val is None:
            return None
        try:
            dt = getattr(val, "dt", None)
            if dt is not None:
                return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
            return str(val)
        except Exception:
            return str(val)

    def _iter_components(self, raw_obj, comp_type: str):
        from icalendar import Calendar as ICalendar

        data = getattr(raw_obj, "data", None) or getattr(raw_obj, "_data", None)
        if not data:
            return
        try:
            cal = ICalendar.from_ical(data)
        except Exception:
            return
        for comp in cal.walk(comp_type):
            yield comp

    # ---------- КАЛЕНДАРЬ ----------

    def list_calendars(self) -> Dict[str, Any]:
        try:
            principal = self._get_principal()
            out = []
            for c in principal.calendars():
                try:
                    comps = c.get_supported_components()
                except Exception:
                    comps = []
                out.append({
                    "name": c.name,
                    "supports": comps,
                    "kind": "reminders" if "VTODO" in (comps or []) else "calendar",
                })
            return {"calendars": out, "count": len(out)}
        except Exception as e:
            logger.error("iCloud list_calendars failed: %s", e, exc_info=True)
            return {"error": str(e)}

    def list_events(
        self,
        days_ahead: int = 7,
        calendar: Optional[str] = None,
        days_back: int = 0,
    ) -> Dict[str, Any]:
        try:
            start = datetime.now(self._tz()) - timedelta(days=max(0, days_back))
            end = start + timedelta(days=max(1, days_ahead) + max(0, days_back))
            cal = self._find_calendar(calendar, "VEVENT")
            try:
                results = cal.search(start=start, end=end, event=True, expand=True)
            except TypeError:
                results = cal.date_search(start=start, end=end)

            events = []
            for r in results:
                for comp in self._iter_components(r, "VEVENT"):
                    events.append({
                        "uid": self._ical_value(comp, "uid"),
                        "title": self._ical_value(comp, "summary"),
                        "start": self._ical_value(comp, "dtstart"),
                        "end": self._ical_value(comp, "dtend"),
                        "location": self._ical_value(comp, "location"),
                        "description": self._ical_value(comp, "description"),
                    })
            events.sort(key=lambda e: e.get("start") or "")
            return {"calendar": cal.name, "count": len(events), "events": events}
        except Exception as e:
            logger.error("iCloud list_events failed: %s", e, exc_info=True)
            return {"error": str(e)}

    def create_event(
        self,
        title: str,
        start: str,
        end: Optional[str] = None,
        duration_minutes: int = 60,
        calendar: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            from icalendar import Calendar as ICalendar, Event

            start_dt = self._parse_dt(start)
            end_dt = self._parse_dt(end) if end else start_dt + timedelta(minutes=duration_minutes)
            cal = self._find_calendar(calendar, "VEVENT")

            ics = ICalendar()
            ics.add("prodid", "-//team-assistant//icloud//RU")
            ics.add("version", "2.0")
            ev = Event()
            uid = str(uuid.uuid4())
            ev.add("uid", uid)
            ev.add("summary", title)
            ev.add("dtstart", start_dt)
            ev.add("dtend", end_dt)
            ev.add("dtstamp", datetime.now(timezone.utc))
            if description:
                ev.add("description", description)
            if location:
                ev.add("location", location)
            ics.add_component(ev)

            cal.save_event(ics.to_ical().decode("utf-8"))
            return {
                "success": True,
                "uid": uid,
                "calendar": cal.name,
                "title": title,
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            }
        except Exception as e:
            logger.error("iCloud create_event failed: %s", e, exc_info=True)
            return {"error": str(e)}

    # ---------- НАПОМИНАНИЯ / ЗАДАЧИ ----------

    def list_reminders(
        self,
        calendar: Optional[str] = None,
        include_completed: bool = False,
    ) -> Dict[str, Any]:
        try:
            cal = self._find_calendar(calendar, "VTODO")
            try:
                todos = cal.todos(include_completed=include_completed)
            except TypeError:
                todos = cal.todos()

            items = []
            for t in todos:
                for comp in self._iter_components(t, "VTODO"):
                    status = self._ical_value(comp, "status")
                    if not include_completed and status and status.upper() == "COMPLETED":
                        continue
                    items.append({
                        "uid": self._ical_value(comp, "uid"),
                        "title": self._ical_value(comp, "summary"),
                        "due": self._ical_value(comp, "due"),
                        "status": status,
                        "notes": self._ical_value(comp, "description"),
                    })
            return {"list": cal.name, "count": len(items), "reminders": items}
        except Exception as e:
            logger.error("iCloud list_reminders failed: %s", e, exc_info=True)
            return {"error": str(e)}

    def create_reminder(
        self,
        title: str,
        due: Optional[str] = None,
        calendar: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            from icalendar import Calendar as ICalendar, Todo

            cal = self._find_calendar(calendar, "VTODO")
            ics = ICalendar()
            ics.add("prodid", "-//team-assistant//icloud//RU")
            ics.add("version", "2.0")
            todo = Todo()
            uid = str(uuid.uuid4())
            todo.add("uid", uid)
            todo.add("summary", title)
            todo.add("dtstamp", datetime.now(timezone.utc))
            todo.add("status", "NEEDS-ACTION")
            due_iso = None
            if due:
                due_dt = self._parse_dt(due)
                todo.add("due", due_dt)
                due_iso = due_dt.isoformat()
            if notes:
                todo.add("description", notes)
            ics.add_component(todo)

            cal.save_todo(ics.to_ical().decode("utf-8"))
            return {"success": True, "uid": uid, "list": cal.name, "title": title, "due": due_iso}
        except Exception as e:
            logger.error("iCloud create_reminder failed: %s", e, exc_info=True)
            return {"error": str(e)}

    def complete_reminder(self, uid: str, calendar: Optional[str] = None) -> Dict[str, Any]:
        try:
            principal = self._get_principal()
            cals = [self._find_calendar(calendar, "VTODO")] if calendar else [
                c for c in principal.calendars() if self._supports(c, "VTODO")
            ]
            for cal in cals:
                try:
                    obj = cal.object_by_uid(uid)
                except Exception:
                    obj = None
                if obj is not None:
                    if hasattr(obj, "complete"):
                        obj.complete()
                    else:
                        obj.icalendar_component["status"] = "COMPLETED"
                        obj.save()
                    return {"success": True, "uid": uid, "list": cal.name}
            return {"error": f"Напоминание с uid={uid} не найдено"}
        except Exception as e:
            logger.error("iCloud complete_reminder failed: %s", e, exc_info=True)
            return {"error": str(e)}

    # ---------- async-обёртки (CalDAV блокирующий) ----------

    async def alist_calendars(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self.list_calendars)

    async def alist_events(self, **kwargs) -> Dict[str, Any]:
        return await asyncio.to_thread(lambda: self.list_events(**kwargs))

    async def acreate_event(self, **kwargs) -> Dict[str, Any]:
        return await asyncio.to_thread(lambda: self.create_event(**kwargs))

    async def alist_reminders(self, **kwargs) -> Dict[str, Any]:
        return await asyncio.to_thread(lambda: self.list_reminders(**kwargs))

    async def acreate_reminder(self, **kwargs) -> Dict[str, Any]:
        return await asyncio.to_thread(lambda: self.create_reminder(**kwargs))

    async def acomplete_reminder(self, **kwargs) -> Dict[str, Any]:
        return await asyncio.to_thread(lambda: self.complete_reminder(**kwargs))


ICLOUD_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "icloud_list_calendars",
            "description": "Список календарей и списков напоминаний в iCloud (с указанием, что это — календарь или напоминания).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "icloud_list_events",
            "description": "Получить события из iCloud-календаря на ближайшие дни.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "description": "На сколько дней вперёд смотреть (по умолчанию 7)"},
                    "days_back": {"type": "integer", "description": "На сколько дней назад захватить (по умолчанию 0)"},
                    "calendar": {"type": "string", "description": "Имя календаря (по умолчанию — первый доступный)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "icloud_create_event",
            "description": "Создать событие в iCloud-календаре.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Название события"},
                    "start": {"type": "string", "description": "Начало в ISO, напр. 2026-07-10T15:00:00 (без зоны — берётся часовой пояс из настроек)"},
                    "end": {"type": "string", "description": "Конец в ISO (опционально)"},
                    "duration_minutes": {"type": "integer", "description": "Длительность в минутах, если не задан end (по умолчанию 60)"},
                    "calendar": {"type": "string", "description": "Имя календаря (опционально)"},
                    "description": {"type": "string", "description": "Описание (опционально)"},
                    "location": {"type": "string", "description": "Место (опционально)"},
                },
                "required": ["title", "start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "icloud_list_reminders",
            "description": "Список напоминаний/задач из iCloud.",
            "parameters": {
                "type": "object",
                "properties": {
                    "calendar": {"type": "string", "description": "Имя списка напоминаний (опционально)"},
                    "include_completed": {"type": "boolean", "description": "Включать выполненные (по умолчанию false)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "icloud_create_reminder",
            "description": "Создать напоминание/задачу в iCloud. Подходит и для 'заметки' — текст кладётся в notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Текст напоминания/задачи"},
                    "due": {"type": "string", "description": "Срок в ISO (опционально)"},
                    "calendar": {"type": "string", "description": "Имя списка (опционально)"},
                    "notes": {"type": "string", "description": "Заметка/детали (опционально)"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "icloud_complete_reminder",
            "description": "Отметить напоминание/задачу выполненным по его uid.",
            "parameters": {
                "type": "object",
                "properties": {
                    "uid": {"type": "string", "description": "UID напоминания (из icloud_list_reminders)"},
                    "calendar": {"type": "string", "description": "Имя списка (опционально)"},
                },
                "required": ["uid"],
            },
        },
    },
]
