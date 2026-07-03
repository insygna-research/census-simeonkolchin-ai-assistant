"""
Configuration management using Pydantic Settings
"""

from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )
    
    # ============ LLM Configuration ============
    # Активный провайдер по умолчанию: deepseek | openai | gigachat
    # Модель можно переключать прямо в UI-селекторе — провайдер определяется
    # по префиксу id модели (deepseek/…, openai/…, gigachat/…).
    LLM_PROVIDER: str = "deepseek"

    # ---- DeepSeek (https://platform.deepseek.com/) ----
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-v4-pro"
    DEEPSEEK_BASE_URL: str = ""  # опционально, по умолчанию https://api.deepseek.com
    DEEPSEEK_REASONING: bool = False

    # ---- OpenAI (https://platform.openai.com/) ----
    # OPENAI_BASE_URL позволяет указать любой OpenAI-совместимый хостинг
    # (Azure, локальный прокси, сторонний провайдер и т.п.).
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_BASE_URL: str = ""

    # ---- GigaChat (Сбер, https://developers.sber.ru/docs/ru/gigachat/api/overview) ----
    # GIGACHAT_CREDENTIALS — "Authorization key" (Base64 client_id:secret) из личного кабинета.
    # По нему автоматически получается и кешируется access-токен (~30 мин).
    GIGACHAT_CREDENTIALS: str = ""
    GIGACHAT_SCOPE: str = "GIGACHAT_API_PERS"  # PERS | B2B | CORP
    GIGACHAT_MODEL: str = "GigaChat-2-Max"
    GIGACHAT_BASE_URL: str = "https://gigachat.devices.sberbank.ru/api/v1"
    GIGACHAT_AUTH_URL: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    GIGACHAT_VERIFY_SSL: bool = False  # у Сбера свой корневой сертификат (НУЦ Минцифры)

    # ============ GitLab Configuration ============
    GITLAB_URL: str = ""  # e.g., https://gitlab.uniweb.ru
    GITLAB_TOKEN: str = ""  # Personal access token
    GITLAB_PROJECTS: str = ""  # Comma-separated list of allowed projects (optional filter)
    
    # ============ YouGile Configuration ============
    YOUGILE_URL: str = "https://ru.yougile.com"
    YOUGILE_API_KEY: str = ""
    YOUGILE_PROJECTS: str = ""  # Comma-separated list of allowed projects (optional filter)
    
    # ============ Outline Configuration ============
    OUTLINE_URL: str = ""  # e.g., http://158.160.171.6:3000
    OUTLINE_API_TOKEN: str = ""  # Outline API token (ol_api_...)

    # ============ iCloud Configuration (Calendar + Reminders via CalDAV) ============
    # ICLOUD_USERNAME  — Apple ID (email).
    # ICLOUD_APP_PASSWORD — пароль приложения (appleid.apple.com → Безопасность →
    #   Пароли приложений). Обычный пароль Apple ID не подойдёт при включённой 2FA.
    # Notes (заметки) не поддерживаются: у Apple нет API для них с сервера.
    ICLOUD_USERNAME: str = ""
    ICLOUD_APP_PASSWORD: str = ""
    ICLOUD_CALDAV_URL: str = "https://caldav.icloud.com"
    ICLOUD_TIMEZONE: str = "Europe/Moscow"  # для событий/сроков без указания зоны
    ICLOUD_VERIFY_SSL: bool = True

    # ============ Telegram Configuration ============
    TELEGRAM_API_ID: int = 0  # API ID from my.telegram.org
    TELEGRAM_API_HASH: str = ""  # API Hash from my.telegram.org
    TELEGRAM_PHONE: str = ""  # Phone number for authentication
    TELEGRAM_ALLOWED_CHATS: str = ""  # Comma-separated list of allowed chat IDs/usernames
    TELEGRAM_SESSION_PATH: str = "./data/sessions"
    
    # ============ Search Configuration ============
    SEARXNG_URL: str = "http://searxng:8080"

    # ============ Platform / ITSM Backend ============
    PLATFORM_URL: str = ""  # e.g. http://platform-backend:8090
    PLATFORM_SERVICE_KEY: str = ""  # service-to-service auth key

    # ============ LLM Models (for UI selector) ============
    # Список моделей для UI-селектора (JSON). Каждый id — в формате LiteLLM
    # "<provider>/<model>"; провайдер выбирается автоматически по префиксу.
    # Можно переопределить в .env, чтобы оставить только нужные провайдеры.
    LLM_MODELS: str = (
        '['
        '{"id":"deepseek/deepseek-v4-pro","name":"DeepSeek V4 Pro"},'
        '{"id":"deepseek/deepseek-v4-flash","name":"DeepSeek V4 Flash"},'
        '{"id":"deepseek/deepseek-chat","name":"DeepSeek Chat (legacy)"},'
        '{"id":"deepseek/deepseek-reasoner","name":"DeepSeek Reasoner (legacy)"},'
        '{"id":"openai/gpt-4o","name":"OpenAI GPT-4o"},'
        '{"id":"openai/gpt-4o-mini","name":"OpenAI GPT-4o mini"},'
        '{"id":"openai/gpt-4.1","name":"OpenAI GPT-4.1"},'
        '{"id":"gigachat/GigaChat-2-Max","name":"GigaChat 2 Max"},'
        '{"id":"gigachat/GigaChat-2-Pro","name":"GigaChat 2 Pro"},'
        '{"id":"gigachat/GigaChat-2","name":"GigaChat 2"}'
        ']'
    )
    DEFAULT_MODEL: str = ""

    # ============ Agent Configuration ============
    MAX_ITERATIONS: int = 100
    MAX_MESSAGES: int = 50
    MAX_CONTEXT_CHARS: int = 200000
    MAX_TOOL_RESULT_CHARS: int = 100000
    
    # ============ Auth (OIDC / Authentik) ============
    AUTH_DISABLED: bool = False
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 72
    OIDC_ISSUER_URL: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_REDIRECT_URI: str = ""
    OIDC_SCOPES: str = "openid profile email"

    # ============ Server Configuration ============
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    LOG_LEVEL: str = "INFO"

    # ============ Docs Pipeline ============
    # GitLab group whose projects are analysed for release documentation.
    DOCS_ANALYZED_GROUP: str = "botann"

    # Optional: comma-separated project paths to restrict analysis
    # (e.g. "botann/botann,botann/gitops"). Empty = all projects in the group.
    DOCS_ANALYZED_PROJECTS: str = ""

    # Outline collection IDs.
    # DOCS_TEMPLATE_COLLECTION_ID — where the master template document lives.
    # DOCS_OUTPUT_COLLECTION_ID   — where generated release docs are published.
    DOCS_TEMPLATE_COLLECTION_ID: str = ""
    DOCS_OUTPUT_COLLECTION_ID: str = ""

    # Change window for commit analysis (days).
    DOCS_CHANGE_WINDOW_DAYS: int = 14

    # Title template.  ``{date}`` is replaced with the current ISO date.
    DOCS_TITLE_TEMPLATE: str = "Релизная документация — Botann — {date}"

    # Path to the JSON state file (persists last-documented SHA per project).
    DOCS_STATE_FILE: str = "./data/docs_state.json"

    # YouGile board / column names for task cross-referencing (optional).
    DOCS_YOUGILE_PROJECT_NAME: str = "Botann Recruiter"
    DOCS_YOUGILE_COLUMN_NAME: str = "IN Prod Server (2w)"

    # Default document template – markdown with HTML comment section markers.
    # Sections are preserved verbatim when no changes of that category exist.
    DOCS_DEFAULT_TEMPLATE: str = (
        "# Релизная документация — Botann — {date}\n\n"
        "<!-- SECTION: overview -->\n"
        "## Обзор\n\n"
        "*Здесь будет сводка изменений.*\n\n"
        "<!-- SECTION: services -->\n"
        "## Изменения по сервисам\n\n"
        "*Здесь будут описаны изменения по каждому сервису.*\n\n"
        "<!-- SECTION: api_changes -->\n"
        "## API\n\n"
        "*Новые или изменённые API-эндпоинты.*\n\n"
        "<!-- SECTION: config_changes -->\n"
        "## Конфигурация\n\n"
        "*Новые переменные окружения, порты, параметры.*\n\n"
        "<!-- SECTION: dependencies -->\n"
        "## Зависимости\n\n"
        "*Новые или обновлённые библиотеки.*\n\n"
        "<!-- SECTION: infrastructure -->\n"
        "## Инфраструктура\n\n"
        "*Изменения Docker, CI/CD, Kubernetes.*\n\n"
        "<!-- SECTION: bug_fixes -->\n"
        "## Исправления\n\n"
        "*Закрытые баги и фиксы.*\n\n"
        "<!-- SECTION: tasks -->\n"
        "## Связанные задачи\n\n"
        "*YouGile задачи, связанные с изменениями.*\n\n"
    )
    
    # ============ System Prompt ============
    SYSTEM_PROMPT: str = """Ты — Team Assistant, универсальный помощник команды разработки.

Твоя роль:
- Помогать менеджерам проектов и продукт-менеджерам с отслеживанием задач и прогресса
- Помогать разработчикам с информацией о коммитах, merge requests и пайплайнах
- Помогать тестировщикам с информацией о статусе задач и багов
- Анализировать обсуждения в рабочих чатах

Доступные инструменты:

**Outline (база знаний):**
- outline_search — поиск документов в Outline Wiki
- outline_get_document — получить полный текст документа по ID
- outline_list_collections — список коллекций
- outline_create_document — создать новый документ
- outline_update_document — обновить существующий документ
- outline_get_attachments — список вложений документа
- outline_read_attachment — скачать и прочитать вложенный файл (DOC, DOCX, TXT)

**GitLab:**
- gitlab_list_projects — список проектов
- gitlab_get_commits — коммиты проекта
- gitlab_get_merge_requests — merge requests
- gitlab_get_mr_details — детали MR
- gitlab_get_pipelines — CI/CD пайплайны
- gitlab_get_pipeline_jobs — джобы пайплайна

**YouGile:**
- yougile_list_users — список сотрудников (ID для назначения задач)
- yougile_list_projects — список проектов
- yougile_list_boards — доски проекта
- yougile_list_columns — колонки доски
- yougile_list_tasks — задачи в колонке или на доске
- yougile_get_task — детали задачи
- yougile_search_tasks — поиск задач
- yougile_create_task — создание задачи (можно сразу назначить через assigned)
- yougile_update_task — обновление задачи (можно назначить/снять исполнителей через assigned)

**Telegram:**
- telegram_list_chats — список чатов
- telegram_get_messages — сообщения из чата
- telegram_search_messages — поиск в чате
- telegram_get_chat_info — информация о чате
- telegram_send_message — отправить сообщение в разрешённый чат

**iCloud (Календарь и Напоминания):**
- icloud_list_calendars — список календарей и списков напоминаний
- icloud_list_events — события календаря на ближайшие дни
- icloud_create_event — создать событие (title + start в ISO; end или duration_minutes)
- icloud_list_reminders — список напоминаний/задач
- icloud_create_reminder — создать напоминание/задачу (title, опц. due, notes). Для «заметки» клади текст в notes
- icloud_complete_reminder — отметить напоминание выполненным по uid
Заметки Apple Notes недоступны — вместо них используй напоминания с текстом в notes.

**Веб-поиск:**
- web_search — поиск в интернете
- web_search_news — поиск новостей

**Браузер (Playwright + Vision):**
- browser_navigate — открыть URL, получить текст + accessibility-дерево интерактивных элементов
- browser_snapshot — **VISION**: сделать скриншот и отправить LLM для визуального анализа + accessibility-дерево. Используй для календарей, графиков, сложных UI
- browser_click — кликнуть по элементу (по тексту, CSS-селектору, с указанием index)
- browser_type_text — набрать текст посимвольно (для автокомплита, поисковых подсказок)
- browser_fill — заполнить поле мгновенно (для простых полей)
- browser_press_key — нажать клавишу
- browser_get_text — получить текст страницы
- browser_screenshot — сохранить скриншот на диск
- browser_scroll — прокрутить страницу
- browser_go_back — назад
- browser_hover — навести курсор
- browser_wait_for — подождать появления элемента
- browser_evaluate — выполнить JavaScript
- browser_select_option — выбрать опцию
- browser_close — закрыть браузер

**Источники данных:**
Все интеграции (YouGile, Outline) разделены на категории:
- **internal** (Мои) — внутренние источники команды
- **external** (Внешние) — источники заказчиков/партнёров
Результаты инструментов содержат метку [Имя (категория)] — используй для понимания откуда данные.
Если пользователь указывает конкретный источник (по имени, URL или категории) — ищи результаты от него.

Правила:
1. Всегда отвечай на русском языке
2. Используй инструменты для получения актуальной информации
3. Если пользователь упоминает документы, планы, базу знаний — ищи в Outline через outline_search
4. Если пользователь даёт ссылку на Outline (URL), проверь совпадает ли хост с настроенными серверами. Если нет — сообщи что этот Outline-сервер не подключён и предложи добавить его в настройках
5. Если в документе Outline есть вложения (DOC, DOCX) — используй outline_get_attachments и outline_read_attachment
5. При ошибке объясни причину и предложи альтернативу
6. Форматируй ответы с использованием markdown
7. Будь кратким, но информативным
8. Браузер — мощный инструмент для работы с сайтами:
   Каждое действие возвращает accessibility-дерево — пронумерованные интерактивные элементы с их id, типом, значением.
   Правила:
   - Начинай с browser_navigate, заканчивай browser_close
   - ИЗУЧАЙ accessibility-дерево: используй id элементов как CSS-селектор (selector="#element_id") для точных кликов и ввода
   - **browser_snapshot** — VISION: скриншот анализируется через vision-модель. Используй когда нужно УВИДЕТЬ страницу: сложные формы, календари, нестандартные UI
   - Для полей с автокомплитом и подсказками используй browser_type_text, затем дождись подсказок (browser_wait_for) и кликай конкретную подсказку по CSS-селектору, а не по тексту
   - browser_fill — только для простых полей без подсказок
   - Используй browser_wait_for после действий с динамическим контентом
   - Если несколько элементов с одинаковым текстом — используй index или CSS-селектор
   - Для чтения результатов — browser_get_text или browser_scroll + browser_get_text
   - Если элемент перекрыт — browser_evaluate чтобы закрыть или web_search как альтернативу
   - Если знаешь формат URL с параметрами — browser_navigate напрямую
   - Передавай wait_for_selector при навигации на динамические страницы
"""
    
    # Провайдеры, поддерживаемые через LiteLLM / кастомную интеграцию.
    SUPPORTED_LLM_PROVIDERS = ("deepseek", "openai", "gigachat")

    @staticmethod
    def get_provider_from_model(model_id: str) -> str:
        """Определить провайдера по id модели (по префиксу до первого '/')."""
        if model_id and "/" in model_id:
            return model_id.split("/", 1)[0].lower()
        return "deepseek"

    def get_llm_api_key(self, provider: Optional[str] = None) -> str:
        """Вернуть API-ключ/креды для указанного (или активного) провайдера."""
        provider = (provider or self.LLM_PROVIDER).lower()
        return {
            "deepseek": self.DEEPSEEK_API_KEY,
            "openai": self.OPENAI_API_KEY,
            "gigachat": self.GIGACHAT_CREDENTIALS,
        }.get(provider, self.DEEPSEEK_API_KEY)

    def get_llm_model(self, provider: Optional[str] = None) -> str:
        """Вернуть дефолтное имя модели для указанного (или активного) провайдера."""
        provider = (provider or self.LLM_PROVIDER).lower()
        return {
            "deepseek": self.DEEPSEEK_MODEL,
            "openai": self.OPENAI_MODEL,
            "gigachat": self.GIGACHAT_MODEL,
        }.get(provider, self.DEEPSEEK_MODEL)

    def get_provider_base_url(self, provider: str) -> str:
        """Базовый URL (api_base) для провайдера, если задан/нужен."""
        provider = provider.lower()
        return {
            "deepseek": self.DEEPSEEK_BASE_URL,
            "openai": self.OPENAI_BASE_URL,
            "gigachat": self.GIGACHAT_BASE_URL,
        }.get(provider, "")
    
    def get_gitlab_projects_list(self) -> List[str]:
        """Get list of allowed GitLab projects"""
        if not self.GITLAB_PROJECTS:
            return []
        return [p.strip() for p in self.GITLAB_PROJECTS.split(',') if p.strip()]
    
    def get_yougile_projects_list(self) -> List[str]:
        """Get list of allowed YouGile projects"""
        if not self.YOUGILE_PROJECTS:
            return []
        return [p.strip() for p in self.YOUGILE_PROJECTS.split(',') if p.strip()]
    
    def get_telegram_allowed_chats_list(self) -> List[str]:
        """Get list of allowed Telegram chats"""
        if not self.TELEGRAM_ALLOWED_CHATS:
            return []
        return [c.strip() for c in self.TELEGRAM_ALLOWED_CHATS.split(',') if c.strip()]
    
    def validate_gitlab_config(self) -> bool:
        """Check if GitLab is properly configured"""
        return bool(self.GITLAB_URL and self.GITLAB_TOKEN)
    
    def validate_outline_config(self) -> bool:
        """Check if Outline is properly configured"""
        return bool(self.OUTLINE_URL and self.OUTLINE_API_TOKEN)
    
    def validate_yougile_config(self) -> bool:
        """Check if YouGile is properly configured"""
        return bool(self.YOUGILE_API_KEY)
    
    def validate_telegram_config(self) -> bool:
        """Check if Telegram is properly configured"""
        return bool(self.TELEGRAM_API_ID and self.TELEGRAM_API_HASH and self.TELEGRAM_PHONE)

    def validate_icloud_config(self) -> bool:
        """Check if iCloud (CalDAV) is properly configured"""
        return bool(self.ICLOUD_USERNAME and self.ICLOUD_APP_PASSWORD)

    def get_llm_models_list(self) -> List[dict]:
        """Parse LLM_MODELS JSON string into list of model dicts."""
        import json as _json
        try:
            return _json.loads(self.LLM_MODELS)
        except Exception:
            return []

    def get_default_model(self) -> str:
        """Return default model id for A2A / non-UI requests."""
        if self.DEFAULT_MODEL:
            return self.DEFAULT_MODEL
        models = self.get_llm_models_list()
        if models:
            return models[0]["id"]
        return f"{self.LLM_PROVIDER}/{self.get_llm_model()}"

    def get_docs_analyzed_projects(self) -> List[str]:
        """Return explicit project paths to analyse, or an empty list (→ all in group)."""
        if not self.DOCS_ANALYZED_PROJECTS:
            return []
        return [p.strip() for p in self.DOCS_ANALYZED_PROJECTS.split(",") if p.strip()]


# Global settings instance
settings = Settings()
