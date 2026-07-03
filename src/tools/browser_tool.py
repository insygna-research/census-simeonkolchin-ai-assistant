"""
Browser Tool - Web browser automation via Playwright.
Allows the agent to navigate websites, interact with elements,
fill forms, extract text, take screenshots and send them to LLM for vision analysis.
"""

import base64
import logging
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

_SCREENSHOTS_DIR = Path("data/screenshots")
_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

_PAGE_TEXT_LIMIT = 6000
_A11Y_LIMIT = 100

_STEALTH_SCRIPT = """
// --- webdriver ---
Object.defineProperty(navigator, 'webdriver', {get: () => false});
try { delete navigator.__proto__.webdriver; } catch(e) {}

// --- platform & hardware ---
Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU','ru','en-US','en']});
Object.defineProperty(navigator, 'platform', {get: () => 'Linux x86_64'});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

// --- chrome object ---
window.chrome = {
  runtime: {
    onMessage: {addListener(){},removeListener(){}},
    sendMessage(){},
    connect(){return {onMessage:{addListener(){}},postMessage(){}}},
  },
  loadTimes(){return {}},
  csi(){return {}},
};

// --- plugins ---
Object.defineProperty(navigator, 'plugins', {get: () => {
  const p = [
    {name:'Chrome PDF Plugin',filename:'internal-pdf-viewer',description:'Portable Document Format'},
    {name:'Chrome PDF Viewer',filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai',description:''},
    {name:'Native Client',filename:'internal-nacl-plugin',description:''},
  ];
  p.length = 3;
  return p;
}});

// --- permissions ---
const _origQuery = window.navigator.permissions?.query?.bind(window.navigator.permissions);
if (_origQuery) {
  window.navigator.permissions.query = (p) =>
    p.name === 'notifications'
      ? Promise.resolve({state: Notification.permission})
      : _origQuery(p);
}

// --- WebGL vendor/renderer ---
const _getP = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
  if (p === 37445) return 'Intel Inc.';
  if (p === 37446) return 'Intel Iris OpenGL Engine';
  return _getP.call(this, p);
};
const _getP2 = WebGL2RenderingContext?.prototype?.getParameter;
if (_getP2) {
  WebGL2RenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel Iris OpenGL Engine';
    return _getP2.call(this, p);
  };
}
"""

_A11Y_TREE_JS = """(() => {
    const items = [];
    let idx = 0;
    const iTags = new Set(['a','button','input','textarea','select','summary','details']);
    const iRoles = new Set([
        'button','link','textbox','checkbox','radio','tab','menuitem',
        'option','switch','slider','combobox','searchbox','spinbutton',
        'treeitem','gridcell'
    ]);

    function vis(el) {
        const s = getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 || r.height > 0;
    }

    function label(el) {
        return (
            el.getAttribute('aria-label') ||
            el.getAttribute('title') ||
            el.getAttribute('placeholder') ||
            el.textContent?.trim().substring(0, 80) ||
            ''
        ).replace(/\\s+/g, ' ');
    }

    function walk(node, depth) {
        if (items.length >= LIMIT || depth > 15) return;
        for (const c of node.children || []) {
            if (!vis(c)) continue;
            const tag = c.tagName.toLowerCase();
            const role = c.getAttribute('role') || '';
            const interactive = iTags.has(tag) || iRoles.has(role)
                || c.hasAttribute('tabindex') || c.hasAttribute('contenteditable')
                || c.hasAttribute('onclick');

            if (interactive) {
                idx++;
                const it = {ref: idx, tag, role: role || tag, label: label(c)};
                if (c.id) it.id = c.id;
                if (tag === 'input' || tag === 'textarea') {
                    it.type = c.type || 'text';
                    it.name = c.name || '';
                    it.value = (c.value || '').substring(0, 60);
                }
                if (tag === 'a' && c.href) it.href = c.href.substring(0, 120);
                if (tag === 'select') {
                    it.options = Array.from(c.options).slice(0, 6).map(o => o.text.trim());
                }
                if (c.getAttribute('aria-expanded') !== null) it.expanded = c.getAttribute('aria-expanded') === 'true';
                items.push(it);
            }
            walk(c, depth + 1);
        }
    }

    walk(document.body, 0);
    return items;
})()""".replace("LIMIT", str(_A11Y_LIMIT))


def _format_a11y_tree(items: list) -> str:
    """Format accessibility tree items into a readable numbered list."""
    lines = []
    for it in items:
        ref = it["ref"]
        role = it.get("role", it["tag"])
        lbl = it.get("label", "")
        extra_parts = []

        if "type" in it and it["tag"] in ("input", "textarea"):
            role = f'input[{it["type"]}]'
        if it.get("id"):
            extra_parts.append(f'id="{it["id"]}"')
        if it.get("name"):
            extra_parts.append(f'name="{it["name"]}"')
        if it.get("value"):
            extra_parts.append(f'value="{it["value"]}"')
        if it.get("href"):
            extra_parts.append(f'→ {it["href"][:60]}')
        if it.get("options"):
            extra_parts.append(f'options={it["options"]}')
        if "expanded" in it:
            extra_parts.append(f'expanded={it["expanded"]}')

        extra = " " + " ".join(extra_parts) if extra_parts else ""
        lines.append(f'[{ref}] {role} "{lbl}"{extra}')
    return "\n".join(lines)


class BrowserTool:
    """Headless Chromium browser controlled by the agent."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._last_used: float = 0
        self._last_screenshot_b64: Optional[str] = None

    async def _ensure_browser(self):
        """Launch browser on first use, reuse afterwards."""
        if self._page and not self._page.is_closed():
            self._last_used = time.time()
            return

        from playwright.async_api import async_playwright

        if self._playwright is None:
            self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        await self._page.add_init_script(_STEALTH_SCRIPT)
        self._last_used = time.time()
        logger.info("Browser launched (stealth mode)")

    # ── page state helpers ──────────────────────────────────────

    async def _get_a11y_tree(self) -> str:
        """Extract and format accessibility tree of interactive elements."""
        try:
            items = await self._page.evaluate(_A11Y_TREE_JS)
            return _format_a11y_tree(items)
        except Exception as e:
            logger.warning(f"A11y tree extraction failed: {e}")
            return "(could not extract elements)"

    async def _page_state(self, *, full_text: bool = False) -> Dict[str, Any]:
        """Return a structured snapshot of the current page for the LLM."""
        title = await self._page.title()
        url = self._page.url

        body_text = ""
        try:
            body_text = await self._page.inner_text("body", timeout=8000)
        except Exception:
            pass
        if not full_text:
            body_text = body_text[:_PAGE_TEXT_LIMIT]

        a11y = await self._get_a11y_tree()

        return {
            "success": True,
            "title": title,
            "url": url,
            "text": body_text,
            "interactive_elements": a11y,
        }

    async def _safe_page_state(self) -> Dict[str, Any]:
        """Get page state, recovering from destroyed contexts (after navigation)."""
        for attempt in range(3):
            try:
                return await self._page_state()
            except Exception:
                await self._page.wait_for_timeout(1500)
        return {"success": True, "title": "", "url": self._page.url,
                "text": "[Page is loading...]", "interactive_elements": ""}

    # ── vision ──────────────────────────────────────────────────

    def pop_screenshot_b64(self) -> Optional[str]:
        """Get and clear the last screenshot base64."""
        b64 = self._last_screenshot_b64
        self._last_screenshot_b64 = None
        return b64

    # ── public tool methods ─────────────────────────────────────

    async def navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        wait_for_selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Navigate to a URL and return page state with accessibility tree."""
        await self._ensure_browser()
        try:
            await self._page.goto(url, wait_until=wait_until, timeout=30000)
            if wait_for_selector:
                try:
                    await self._page.wait_for_selector(
                        wait_for_selector, state="visible", timeout=15000
                    )
                except Exception:
                    logger.warning(f"wait_for_selector '{wait_for_selector}' timed out")
            else:
                await self._page.wait_for_timeout(2000)
            return await self._page_state()
        except Exception as e:
            logger.error(f"browser_navigate error: {e}")
            return {"error": f"Failed to navigate to {url}: {str(e)}"}

    async def snapshot(self) -> Dict[str, Any]:
        """
        Take a visual snapshot: screenshot (sent to LLM as image) + accessibility tree.
        Use when you need to SEE the page visually (calendars, charts, complex layouts).
        """
        await self._ensure_browser()
        try:
            screenshot_bytes = await self._page.screenshot(
                type="jpeg", quality=55, full_page=False,
            )
            self._last_screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

            title = await self._page.title()
            url = self._page.url
            a11y = await self._get_a11y_tree()

            saved_path = _SCREENSHOTS_DIR / f"vision_{int(time.time())}.jpg"
            saved_path.write_bytes(screenshot_bytes)

            return {
                "success": True,
                "title": title,
                "url": url,
                "interactive_elements": a11y,
                "_has_vision": True,
            }
        except Exception as e:
            logger.error(f"browser_snapshot error: {e}")
            return {"error": f"Snapshot failed: {str(e)}"}

    async def click(
        self,
        text: Optional[str] = None,
        selector: Optional[str] = None,
        index: int = 0,
    ) -> Dict[str, Any]:
        """Click an element on the page."""
        await self._ensure_browser()
        try:
            if text:
                loc = self._page.get_by_text(text, exact=False).nth(index)
                await loc.click(timeout=10000)
            elif selector:
                loc = self._page.locator(selector)
                if index > 0:
                    loc = loc.nth(index)
                await loc.click(timeout=10000)
            else:
                return {"error": "Specify either text or selector"}

            await self._page.wait_for_timeout(2000)
            return await self._safe_page_state()
        except Exception as e:
            logger.error(f"browser_click error: {e}")
            return {"error": f"Click failed: {str(e)}"}

    async def fill(
        self,
        value: str,
        selector: Optional[str] = None,
        label: Optional[str] = None,
        placeholder: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Clear and fill a text input (instant, no key events). For autocomplete use type_text."""
        await self._ensure_browser()
        try:
            if label:
                loc = self._page.get_by_label(label)
            elif placeholder:
                loc = self._page.get_by_placeholder(placeholder)
            elif selector:
                loc = self._page.locator(selector)
            else:
                return {"error": "Specify selector, label, or placeholder"}
            await loc.fill(value, timeout=10000)
            return {"success": True, "message": f"Filled with: {value[:80]}"}
        except Exception as e:
            logger.error(f"browser_fill error: {e}")
            return {"error": f"Fill failed: {str(e)}"}

    async def type_text(
        self,
        text: str,
        selector: Optional[str] = None,
        clear: bool = False,
        delay: int = 50,
    ) -> Dict[str, Any]:
        """Type text char-by-char (fires real key events). Triggers autocomplete."""
        await self._ensure_browser()
        try:
            if selector:
                await self._page.click(selector, timeout=5000)
                await self._page.wait_for_timeout(300)
            if clear:
                await self._page.keyboard.press("Control+a")
                await self._page.keyboard.press("Delete")
                await self._page.wait_for_timeout(200)
            await self._page.keyboard.type(text, delay=delay)
            await self._page.wait_for_timeout(1500)
            return await self._page_state()
        except Exception as e:
            logger.error(f"browser_type_text error: {e}")
            return {"error": f"Type text failed: {str(e)}"}

    async def press_key(self, key: str) -> Dict[str, Any]:
        """Press a keyboard key (Enter, Tab, Escape, etc.)."""
        await self._ensure_browser()
        try:
            await self._page.keyboard.press(key)
            await self._page.wait_for_timeout(2000)
            return await self._safe_page_state()
        except Exception as e:
            logger.error(f"browser_press_key error: {e}")
            return {"error": f"Key press failed: {str(e)}"}

    async def get_text(self, selector: Optional[str] = None) -> Dict[str, Any]:
        """Get visible text content of the page or a specific element."""
        await self._ensure_browser()
        try:
            if selector:
                text = await self._page.inner_text(selector, timeout=8000)
            else:
                text = await self._page.inner_text("body", timeout=8000)
            return {
                "success": True,
                "url": self._page.url,
                "text": text[:12000],
                "length": len(text),
            }
        except Exception as e:
            logger.error(f"browser_get_text error: {e}")
            return {"error": f"Get text failed: {str(e)}"}

    async def screenshot(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Take a screenshot and save to disk (not sent to LLM — use snapshot for vision)."""
        await self._ensure_browser()
        try:
            fname = (name or f"screenshot_{int(time.time())}") + ".png"
            path = _SCREENSHOTS_DIR / fname
            await self._page.screenshot(path=str(path), full_page=False)
            logger.info(f"Screenshot saved: {path}")
            return {
                "success": True,
                "filename": fname,
                "path": str(path),
                "message": f"Screenshot saved as {fname}",
            }
        except Exception as e:
            logger.error(f"browser_screenshot error: {e}")
            return {"error": f"Screenshot failed: {str(e)}"}

    async def scroll(self, direction: str = "down", amount: int = 3) -> Dict[str, Any]:
        """Scroll the page up or down."""
        await self._ensure_browser()
        try:
            pixels = min(amount, 10) * 600
            delta = pixels if direction == "down" else -pixels
            await self._page.mouse.wheel(0, delta)
            await self._page.wait_for_timeout(1500)
            return await self._page_state()
        except Exception as e:
            logger.error(f"browser_scroll error: {e}")
            return {"error": f"Scroll failed: {str(e)}"}

    async def go_back(self) -> Dict[str, Any]:
        """Go back to the previous page."""
        await self._ensure_browser()
        try:
            await self._page.go_back(wait_until="domcontentloaded", timeout=15000)
            await self._page.wait_for_timeout(2000)
            return await self._safe_page_state()
        except Exception as e:
            logger.error(f"browser_go_back error: {e}")
            return {"error": f"Go back failed: {str(e)}"}

    async def evaluate(self, script: str) -> Dict[str, Any]:
        """Execute JavaScript on the page and return the result."""
        await self._ensure_browser()
        try:
            code = script.strip()
            if "return " in code and not code.startswith("("):
                code = f"(() => {{ {code} }})()"
            result = await self._page.evaluate(code)
            result_str = str(result)
            if len(result_str) > 8000:
                result_str = result_str[:8000] + "..."
            return {"success": True, "result": result_str}
        except Exception as e:
            logger.error(f"browser_evaluate error: {e}")
            return {"error": f"JS execution failed: {str(e)}"}

    async def hover(
        self, text: Optional[str] = None, selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Hover over an element (useful for dropdown menus)."""
        await self._ensure_browser()
        try:
            if text:
                await self._page.get_by_text(text, exact=False).first.hover(timeout=5000)
            elif selector:
                await self._page.hover(selector, timeout=5000)
            else:
                return {"error": "Specify text or selector"}
            await self._page.wait_for_timeout(500)
            return await self._page_state()
        except Exception as e:
            logger.error(f"browser_hover error: {e}")
            return {"error": f"Hover failed: {str(e)}"}

    async def wait_for(
        self,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        timeout: int = 15000,
    ) -> Dict[str, Any]:
        """Wait for an element or text to appear on the page."""
        await self._ensure_browser()
        try:
            if text:
                await self._page.get_by_text(text, exact=False).first.wait_for(
                    state="visible", timeout=timeout
                )
            elif selector:
                await self._page.wait_for_selector(selector, state="visible", timeout=timeout)
            else:
                return {"error": "Specify selector or text"}
            return await self._page_state()
        except Exception as e:
            logger.error(f"browser_wait_for error: {e}")
            return {"error": f"Wait failed ({timeout}ms): {str(e)}"}

    async def select_option(
        self, selector: str, value: Optional[str] = None, label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Select an option in a <select> dropdown."""
        await self._ensure_browser()
        try:
            if label:
                await self._page.select_option(selector, label=label, timeout=5000)
            elif value:
                await self._page.select_option(selector, value=value, timeout=5000)
            else:
                return {"error": "Specify value or label"}
            return {"success": True, "message": f"Selected option in {selector}"}
        except Exception as e:
            logger.error(f"browser_select_option error: {e}")
            return {"error": f"Select option failed: {str(e)}"}

    async def close(self) -> Dict[str, Any]:
        """Close the browser and free resources."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
        finally:
            self._browser = None
            self._context = None
            self._page = None
            self._playwright = None
        logger.info("Browser closed")
        return {"success": True, "message": "Browser closed"}


# ──────────────────────────────────────────────────────────────
# Tool definitions
# ──────────────────────────────────────────────────────────────

BROWSER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Открыть URL. Возвращает текст, accessibility-дерево интерактивных элементов (пронумерованные кнопки, ссылки, поля). Для ожидания динамического контента передай wait_for_selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL (https://...)"},
                    "wait_until": {
                        "type": "string",
                        "enum": ["domcontentloaded", "load", "networkidle"],
                        "default": "domcontentloaded"
                    },
                    "wait_for_selector": {
                        "type": "string",
                        "description": "CSS-селектор для ожидания после загрузки (например '.search-results')"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": "Сделать визуальный снимок страницы: скриншот отправляется в LLM для анализа + accessibility-дерево элементов. Используй когда нужно УВИДЕТЬ страницу (календари, графики, сложные UI, карты).",
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
            "name": "browser_click",
            "description": "Кликнуть элемент по тексту или CSS-селектору. Используй index при нескольких одинаковых элементах.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Видимый текст элемента"},
                    "selector": {"type": "string", "description": "CSS-селектор"},
                    "index": {"type": "integer", "description": "Какой по счёту (0=первый)", "default": 0}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Мгновенно заполнить поле (без событий клавиш). Для автокомплита — browser_type_text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "string", "description": "Текст"},
                    "selector": {"type": "string", "description": "CSS-селектор"},
                    "label": {"type": "string", "description": "Текст label"},
                    "placeholder": {"type": "string", "description": "Placeholder"}
                },
                "required": ["value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type_text",
            "description": "Набрать текст посимвольно — активирует автокомплит и выпадающие подсказки. После набора кликни нужную подсказку.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Текст для набора"},
                    "selector": {"type": "string", "description": "CSS-селектор поля (кликнет для фокуса)"},
                    "clear": {"type": "boolean", "description": "Очистить поле перед набором", "default": False},
                    "delay": {"type": "integer", "description": "Задержка между символами (мс)", "default": 50}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press_key",
            "description": "Нажать клавишу (Enter, Tab, Escape, ArrowDown и т.д.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Клавиша (Enter, Tab, Escape, ArrowDown)"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_text",
            "description": "Получить видимый текст (до 12000 символов). Для чтения результатов поиска после загрузки.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS-селектор (без него — вся страница)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Сохранить скриншот на диск (не отправляет LLM). Для vision-анализа используй browser_snapshot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Имя файла без расширения"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Прокрутить страницу.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["down","up"], "default": "down"},
                    "amount": {"type": "integer", "description": "Экранов (1-10)", "default": 3}
                },
                "required": []
            }
        }
    },
    {"type": "function", "function": {"name": "browser_go_back", "description": "Назад.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {
        "type": "function",
        "function": {
            "name": "browser_evaluate",
            "description": "Выполнить JavaScript. Код с return автоматически оборачивается в функцию.",
            "parameters": {
                "type": "object",
                "properties": {"script": {"type": "string", "description": "JS код"}},
                "required": ["script"]
            }
        }
    },
    {"type": "function", "function": {"name": "browser_hover", "description": "Навести курсор (для dropdown-меню).", "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "selector": {"type": "string"}}, "required": []}}},
    {
        "type": "function",
        "function": {
            "name": "browser_wait_for",
            "description": "Подождать появления элемента/текста. Используй после навигации для ожидания динамического контента.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS-селектор"},
                    "text": {"type": "string", "description": "Текст"},
                    "timeout": {"type": "integer", "default": 15000}
                },
                "required": []
            }
        }
    },
    {"type": "function", "function": {"name": "browser_select_option", "description": "Выбрать опцию в <select>.", "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "value": {"type": "string"}, "label": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "browser_close", "description": "Закрыть браузер.", "parameters": {"type": "object", "properties": {}, "required": []}}},
]
