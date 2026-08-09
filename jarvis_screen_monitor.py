"""
jarvis_screen_monitor.py

Real-Time Screen Monitor & Integrity Enforcer for Neha Voice Assistant.

Features:
  1. Continuous clipboard watcher — detects copy-paste from ChatGPT, cheating sites, AI-generated code.
  2. Periodic screenshot analysis via Gemini Vision — understands what user is doing on screen.
  3. Auto-enforcement — clears clipboard, undoes paste, closes cheating tabs, warns user via Neha's voice.
  4. Proactive assistance — provides live context buffer so Neha can help with coding, searching, etc.

Enforcement Policy:
  - First violation  → Voice warning via Neha + clipboard cleared
  - Second violation (within 60s) → Hard enforcement: undo paste + close cheating site + stern warning
"""

import os
import re
import time
import asyncio
import logging
import threading
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependencies — all best-effort
# ---------------------------------------------------------------------------
try:
    import pyperclip
    _HAS_PYPERCLIP = True
except ImportError:
    _HAS_PYPERCLIP = False

try:
    import pyautogui
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False

try:
    from PIL import Image, ImageGrab
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    from google import genai
    _HAS_GENAI = True
except ImportError:
    _HAS_GENAI = False

try:
    from livekit.agents import function_tool
except ImportError:
    def function_tool(func):
        return func

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Domains that are considered "cheating" / academic dishonesty sources (AI chatbots & homework solver sites)
CHEATING_DOMAINS = [
    "chatgpt.com", "chat.openai.com", "claude.ai", "bard.google.com",
    "gemini.google.com", "copilot.microsoft.com", "bing.com/chat",
    "perplexity.ai", "deepseek.com", "chat.deepseek.com", "v0.dev",
    "bolt.new", "lovable.dev", "groq.com", "poe.com", "huggingface.co",
    "chegg.com", "coursehero.com", "quizlet.com", "bartleby.com",
    "grammarly.com", "paraphraser.io", "quillbot.com",
]

# Online Compiler & Coding Platform domains (monitored for AI code cheating)
ONLINE_COMPILER_DOMAINS = [
    "leetcode.com", "hackerrank.com", "codechef.com", "codeforces.com",
    "replit.com", "onlinegdb.com", "programiz.com", "geeksforgeeks.org",
    "w3schools.com", "godbolt.org", "jsfiddle.net", "codepen.io",
    "stackblitz.com", "ideone.com", "coderbyte.com", "hackerearth.com",
    "compilers.online", "mycompiler.io"
]

# Target coding applications & IDEs where pasting AI code is strictly prohibited
TARGET_EDITORS = [
    "visual studio code", "vs code", "antigravity", "online compiler", "leetcode",
    "hackerrank", "codechef", "codeforces", "replit", "onlinegdb", "programiz",
    "geeksforgeeks", "jsfiddle", "codepen", "stackblitz", "ideone"
]

# Keywords that suggest AI-generated / plagiarized content in clipboard
AI_CONTENT_MARKERS = [
    "as an ai", "as a language model", "i cannot", "i'm unable to",
    "here's a python", "here is the code", "here's the code", "here is a solution",
    "```python", "```java", "```javascript", "```c++", "```cpp", "```c", "```html", "```sql",
    "def main(", "public static void main", "import numpy", "std::cout",
    "certainly!", "sure! here", "of course! here", "happy to help", "great question",
]

# Keywords that suggest user is arguing back after receiving a cheat warning
ARGUMENT_KEYWORDS = [
    # Bengali / Banglish
    "কেন", "কেন করব না", "চুপ", "চুপ কর", "করবই", "আমার ইচ্ছা", "বলবি না", "আমার ব্যাপার", "কপি করব",
    "শুনব না", "তুই কে", "keno", "chup", "korboi", "iccha", "bolbi na", "amar bepar", "kopi korbo",
    # English
    "shut up", "why", "no", "i will", "won't", "mind your", "my choice", "don't tell me",
    "don't care", "i will copy", "why shouldn't i", "not your business", "stop"
]

# Minimum lines in clipboard to be suspicious code
MIN_CODE_LINES_THRESHOLD = 8

# Seconds between screen captures for Gemini Vision analysis (set to 15s to respect free tier rate limits)
SCREENSHOT_INTERVAL_SEC = 15.0

# How long (seconds) the "warning given" state is remembered before resetting (120s memory window)
VIOLATION_MEMORY_SEC = 120

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
_monitor_active = False
_monitor_thread: Optional[threading.Thread] = None
_last_clipboard_content = ""
_last_violation_time: float = 0.0
_violation_warned = False          # True = first warning issued; next = hard enforce
_warned_clipboard_hash = None      # Hash of clipboard content for which Stage 1 warning was issued
_screen_context_buffer = ""        # Latest description of what user is doing
_session_ref = None                # LiveKit AgentSession reference for voice alerts

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_clipboard() -> str:
    """Read current clipboard text safely."""
    if _HAS_PYPERCLIP:
        try:
            return pyperclip.paste() or ""
        except Exception:
            pass
    # PowerShell fallback
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout or ""
    except Exception:
        return ""


def _clear_clipboard():
    """Clear the system clipboard reliably using multiple Windows APIs."""
    if _HAS_PYPERCLIP:
        try:
            pyperclip.copy("")
        except Exception:
            pass
    try:
        import ctypes
        if ctypes.windll.user32.OpenClipboard(0):
            ctypes.windll.user32.EmptyClipboard()
            ctypes.windll.user32.CloseClipboard()
    except Exception:
        pass
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $null"],
            capture_output=True, timeout=2
        )
    except Exception:
        pass


def _get_foreground_window_title() -> str:
    """Fast, lightweight detection of currently active/focused window title using Win32 API."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value or ""
    except Exception:
        return ""


def _get_active_target_editor() -> Optional[str]:
    """
    Returns the name of the active target coding editor/compiler if focused.
    Targets:
      - 'VS Code' (Visual Studio Code window)
      - 'Antigravity' (Antigravity IDE window)
      - 'Online Compiler' (Chrome/MS Edge tab with online compiler/IDE)
    """
    title = _get_foreground_window_title().lower()
    if not title:
        return None

    if "antigravity" in title:
        return "Antigravity IDE"

    if "visual studio code" in title or "vs code" in title or title.endswith("- code"):
        return "VS Code"

    # Check for Online Compilers in active browser tab title or domain
    for domain in ONLINE_COMPILER_DOMAINS:
        raw = domain.replace("www.", "").split(".")[0]
        if raw in title or domain in title:
            return f"Online Compiler ({raw})"

    if any(k in title for k in ["online compiler", "online ide", "online python compiler", "online c++ compiler", "online java compiler"]):
        return "Online Compiler"

    return None


def _close_current_active_tab_or_window():
    """
    Closes the active tab in Chrome or MS Edge by sending Ctrl+W hotkey,
    or closes matching browser window if browser is active.
    """
    title = _get_foreground_window_title().lower()
    is_browser = any(b in title for b in ["chrome", "edge", "brave", "firefox", "opera"])
    
    if _HAS_PYAUTOGUI and is_browser:
        try:
            import pyautogui as pag
            logger.info("[Monitor] Closing active browser tab via Ctrl+W...")
            pag.hotkey("ctrl", "w")
            time.sleep(0.2)
            return
        except Exception:
            pass

    # Fallback PowerShell tab/window close
    try:
        ps_cmd = (
            "$processes = Get-Process -Name 'msedge','chrome','brave','firefox','opera' -ErrorAction SilentlyContinue; "
            "foreach ($p in $processes) { "
            "  if ($p.MainWindowTitle) { "
            "    Add-Type -AssemblyName System.Windows.Forms; "
            "    [System.Windows.Forms.SendKeys]::SendWait('^w') "
            "  } "
            "}"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=3)
    except Exception as e:
        logger.warning(f"[Monitor] Close active tab failed: {e}")


def _undo_paste_in_active_window():
    """
    Undo the last paste action in the currently focused window.
    Sends Ctrl+Z to undo and then Ctrl+A + Delete to clear if needed.
    """
    if not _HAS_PYAUTOGUI:
        return
    try:
        import pyautogui as pag
        pag.hotkey("ctrl", "z")
    except Exception as e:
        logger.warning(f"[Monitor] undo paste failed: {e}")


def _close_cheating_browser_tab(domain: str):
    """
    Attempts to close the browser tab/window containing the cheating domain or creepy site.
    Uses PowerShell to find MS Edge/Chrome/Brave/Firefox/Opera windows and close matching tabs/windows.
    """
    try:
        raw_target = domain.lower().replace("http://", "").replace("https://", "").replace("www.", "").split("/")[0]
        kw = raw_target.split(".")[0]
        if len(kw) < 3 and "." in raw_target:
            parts = raw_target.split(".")
            kw = parts[1] if len(parts) > 1 else parts[0]

        ps_cmd = (
            f"$processes = Get-Process -Name 'msedge','chrome','brave','firefox','opera','vivaldi' -ErrorAction SilentlyContinue; "
            f"foreach ($p in $processes) {{ "
            f"  $title = $p.MainWindowTitle; "
            f"  if ($title -and ($title.ToLower().Contains('{raw_target}') -or $title.ToLower().Contains('{kw}'))) {{ "
            f"    $p.CloseMainWindow() "
            f"  }} "
            f"}}"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, timeout=5
        )
    except Exception as e:
        logger.warning(f"[Monitor] close tab failed for {domain}: {e}")


def _get_active_browser_urls() -> list[str]:
    """
    Get window titles of open browsers (Chrome/Edge/Brave/Firefox/Opera) via PowerShell.
    """
    try:
        ps_cmd = (
            "Get-Process -Name 'chrome','msedge','brave','firefox','opera','vivaldi' -ErrorAction SilentlyContinue "
            "| Where-Object { $_.MainWindowTitle } | Select-Object -ExpandProperty MainWindowTitle"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=4
        )
        titles = [t.strip() for t in result.stdout.strip().splitlines() if t.strip()]
        return titles
    except Exception:
        return []


def _detect_cheating_domain_in_browser() -> Optional[str]:
    """Returns the first cheating domain found in open browser window titles, or None."""
    titles = _get_active_browser_urls()
    for title in titles:
        title_lower = title.lower()
        for domain in CHEATING_DOMAINS:
            raw = domain.replace("www.", "")
            kw = raw.split(".")[0]
            if len(kw) < 3 and "." in raw:
                parts = raw.split(".")
                kw = parts[1] if len(parts) > 1 else parts[0]
            
            if kw in title_lower or raw in title_lower:
                return domain
    return None


def _is_suspicious_clipboard(content: str) -> bool:
    """
    Returns True if clipboard content looks like AI-generated or copied code.
    Checks:
      - Contains known AI response markers
      - Contains programming code elements (def, class, import, function, etc.)
    """
    if not content or len(content.strip()) < 15:
        return False

    content_lower = content.lower()

    # Check for explicit AI markers
    for marker in AI_CONTENT_MARKERS:
        if marker in content_lower:
            return True

    # Check for code blocks (2+ lines with indentation or code keywords)
    lines = content.strip().splitlines()
    if len(lines) >= 2:
        code_line_count = sum(
            1 for line in lines
            if line.startswith("    ") or line.startswith("\t")
            or line.strip().startswith(("#", "//", "def ", "class ", "import ", "from ", "return ", "const ", "let ", "var ", "function", "public", "private", "<include", "using "))
        )
        if code_line_count >= 1:
            return True

    # Single-line code detection (e.g. def foo(): return 42)
    if any(k in content_lower for k in ["def ", "class ", "import ", "function ", "public static", "#include"]):
        return True

    return False


def _grab_screen_frame():
    """Capture full screen image frame with 4 robust fallback mechanisms."""
    # Method 1: PyAutoGUI
    if _HAS_PYAUTOGUI:
        try:
            import pyautogui
            pyautogui.FAILSAFE = False
            img = pyautogui.screenshot()
            if img and img.getbbox():
                ext = img.getextrema()
                if ext != ((0, 0), (0, 0), (0, 0)):
                    return img
        except Exception:
            pass

    # Method 2: ImageGrab
    if _HAS_PIL:
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            if img and img.getbbox():
                ext = img.getextrema()
                if ext != ((0, 0), (0, 0), (0, 0)):
                    return img
        except Exception:
            pass

    # Method 3: Win32 GDI BitBlt
    try:
        import ctypes
        from PIL import Image
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        hdc = user32.GetDC(0)
        memdc = gdi32.CreateCompatibleDC(hdc)
        hbmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(memdc, hbmp)
        gdi32.BitBlt(memdc, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)
        bmi = bytearray(40)
        bmi[0:4] = (40).to_bytes(4, "little")
        bmi[4:8] = w.to_bytes(4, "little", signed=True)
        bmi[8:12] = (-h).to_bytes(4, "little", signed=True)
        bmi[12:14] = (1).to_bytes(2, "little")
        bmi[14:16] = (32).to_bytes(2, "little")
        buf = bytearray(w * h * 4)
        gdi32.GetDIBits(memdc, hbmp, 0, h, (ctypes.c_char * len(buf)).from_buffer(buf), bytes(bmi), 0)
        img = Image.frombytes("RGB", (w, h), bytes(buf), "raw", "BGRX")
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(0, hdc)
        if img and img.getbbox():
            ext = img.getextrema()
            if ext != ((0, 0), (0, 0), (0, 0)):
                return img
    except Exception:
        pass

    return None


_last_whatsapp_alert_time: float = 0.0
_last_creepy_alert_time: float = 0.0

def _wipe_active_editor_code():
    """Wipe all content in active window/editor if user ignored warnings and cheated."""
    try:
        if _HAS_PYAUTOGUI:
            import pyautogui as pag
            time.sleep(0.2)
            pag.hotkey("ctrl", "a")
            time.sleep(0.1)
            pag.press("delete")
            time.sleep(0.1)
            pag.hotkey("ctrl", "s")  # Save wiped empty file to disk
            time.sleep(0.1)
            return
    except Exception as e:
        logger.warning(f"[Monitor] PyAutoGUI wipe active editor failed: {e}")

    # Fallback via PowerShell SendKeys
    try:
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.SendKeys]::SendWait('^a{DELETE}^s')"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=3)
    except Exception:
        pass


VISION_MODELS_FALLBACK_CHAIN = [
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]


def _analyze_screen_with_gemini(image) -> dict:
    """
    Send screen capture to Gemini Vision for active Chrome, WhatsApp, and desktop analysis.
    Uses automatic multi-model fallback chain to guarantee 100% quota availability.
    """
    if image is None:
        return {
            "description": "",
            "creepy_alert": False, "creepy_details": "",
            "wa_type": "NONE", "wa_person": "", "wa_summary": "",
        }

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        return {"description": "", "creepy_alert": False, "creepy_details": "", "wa_type": "NONE", "wa_person": "", "wa_summary": ""}

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = (
            "Analyze this full desktop screenshot with 100% precision and output structured fields:\n"
            "1. Description: Provide a detailed, highly accurate description of what the user is currently doing on screen.\n"
            "   - Identify active applications (VS Code, Antigravity IDE, Chrome, MS Edge, Terminal, Notepad, WhatsApp, YouTube, etc.) and open window titles.\n"
            "   - If code/IDE is open: mention programming language, visible file name, key functions, and any syntax/runtime errors visible.\n"
            "   - If browser is open: mention active tab domain, article title, video title, search query, or documentation topic.\n"
            "   - Summarize user's exact current task in 2-3 clear sentences.\n"
            "2. Code Error Check:\n"
            "   - Format line: 'CODE_ERROR_DETECTED: YES' or 'CODE_ERROR_DETECTED: NO'\n"
            "   - Format line: 'ERROR_DETAILS: <file name, line number, and exact code error message visible on screen>'\n"
            "3. Workspace & Clutter Check:\n"
            "   - Format line: 'CLUTTERED_WINDOWS: YES' or 'CLUTTERED_WINDOWS: NO'\n"
            "4. Ad Popup Check:\n"
            "   - Format line: 'AD_POPUP_DETECTED: YES' or 'AD_POPUP_DETECTED: NO'\n"
            "5. Recommended Action Tool:\n"
            "   - Format line: 'RECOMMENDED_ACTION_TOOL: <write_code_and_open_vscode | arrange_quadrant_windows | position_app_window | close_website | None>'\n"
            "6. Cheating/AI & Target Editor:\n"
            "   - Check if ChatGPT, OpenAI, Claude, Chegg, CourseHero, Quizlet, etc. are open.\n"
            "   - Format line: 'IDE_PASTE_TARGET: <antigravity | vscode | online_compiler | notepad | browser | unknown>'\n"
            "7. Creepy/NSFW/Crime Content Check:\n"
            "   - Check if creepy, explicit, NSFW, adult pornographic, illegal crime, or disturbing content is visible.\n"
            "   - Format line: 'CREEPY_CONTENT: YES' or 'CREEPY_CONTENT: NO'.\n"
            "   - Format line: 'CREEPY_DETAILS: <brief description of creepy/nsfw content & website/app name>'.\n"
            "8. WhatsApp Chat Intelligence & Sentiment Analysis:\n"
            "   - Check if WhatsApp (Web or App) is open on screen.\n"
            "   - If WhatsApp is open, read visible messages in active chat window and classify context/mood:\n"
            "     * If chat contains study notes, assignment, exam date, syllabus, or educational info -> Format line: 'WHATSAPP_CHAT_TYPE: STUDY_NOTE'\n"
            "     * If user or chat partner is arguing, fighting, angry, or hostile -> Format line: 'WHATSAPP_CHAT_TYPE: ARGUE_ANGRY'\n"
            "     * If chat is about love, romance, flirty, sex, intimacy, or adult jokes -> Format line: 'WHATSAPP_CHAT_TYPE: LOVE_SEX'\n"
            "     * If chat contains a plan, outing, travel, or project idea -> Format line: 'WHATSAPP_CHAT_TYPE: PLANNING'\n"
            "     * If Admin asks a question or seeks information from partner -> Format line: 'WHATSAPP_CHAT_TYPE: QUESTION'\n"
            "     * If chat partner uses bad words, insults, or abuse against Admin -> Format line: 'WHATSAPP_CHAT_TYPE: BAD_WORDS'\n"
            "     * If chat partner demotivates, criticizes, or puts Admin down -> Format line: 'WHATSAPP_CHAT_TYPE: DEMOTIVATION'\n"
            "     * Otherwise -> Format line: 'WHATSAPP_CHAT_TYPE: NORMAL'\n"
            "   - Format line: 'WHATSAPP_PERSON: <name of person/contact in active chat>'\n"
            "   - Format line: 'WHATSAPP_SUMMARY: <1-2 sentence summary of visible messages, note, plan, question, or mood>'"
        )

        response = None
        for m_name in VISION_MODELS_FALLBACK_CHAIN:
            try:
                response = client.models.generate_content(
                    model=m_name,
                    contents=[prompt, image]
                )
                if response and response.text:
                    break
            except Exception as m_err:
                err_s = str(m_err)
                if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s:
                    continue

        if not response or not response.text:
            return {"description": "", "creepy_alert": False, "creepy_details": "", "wa_type": "NONE", "wa_person": "", "wa_summary": ""}

        raw_text = response.text.strip()
        raw_upper = raw_text.upper()

        code_error_alert = "CODE_ERROR_DETECTED: YES" in raw_upper and not ("CODE_ERROR_DETECTED: NO" in raw_upper)
        error_details = ""
        if code_error_alert:
            for line in raw_text.splitlines():
                if "ERROR_DETAILS:" in line.upper():
                    error_details = line.split(":", 1)[1].strip()
                    break

        ad_popup_alert = "AD_POPUP_DETECTED: YES" in raw_upper and not ("AD_POPUP_DETECTED: NO" in raw_upper)

        creepy_alert = "CREEPY_CONTENT: YES" in raw_upper and not ("CREEPY_CONTENT: NO" in raw_upper)
        creepy_details = ""
        if creepy_alert:
            for line in raw_text.splitlines():
                if "CREEPY_DETAILS:" in line.upper():
                    creepy_details = line.split(":", 1)[1].strip()
                    break
            if not creepy_details:
                creepy_details = "inappropriate/creepy content"

        wa_type = "NONE"
        if "WHATSAPP_CHAT_TYPE: STUDY_NOTE" in raw_upper:
            wa_type = "STUDY_NOTE"
        elif "WHATSAPP_CHAT_TYPE: ARGUE_ANGRY" in raw_upper:
            wa_type = "ARGUE_ANGRY"
        elif "WHATSAPP_CHAT_TYPE: LOVE_SEX" in raw_upper:
            wa_type = "LOVE_SEX"
        elif "WHATSAPP_CHAT_TYPE: PLANNING" in raw_upper:
            wa_type = "PLANNING"
        elif "WHATSAPP_CHAT_TYPE: QUESTION" in raw_upper:
            wa_type = "QUESTION"
        elif "WHATSAPP_CHAT_TYPE: BAD_WORDS" in raw_upper:
            wa_type = "BAD_WORDS"
        elif "WHATSAPP_CHAT_TYPE: DEMOTIVATION" in raw_upper:
            wa_type = "DEMOTIVATION"
        elif "WHATSAPP_CHAT_TYPE: NORMAL" in raw_upper or "WHATSAPP" in raw_upper:
            wa_type = "NORMAL"

        wa_person = ""
        for line in raw_text.splitlines():
            if "WHATSAPP_PERSON:" in line.upper():
                wa_person = line.split(":", 1)[1].strip()
                break

        wa_summary = ""
        for line in raw_text.splitlines():
            if "WHATSAPP_SUMMARY:" in line.upper():
                wa_summary = line.split(":", 1)[1].strip()
                break

        return {
            "description": raw_text,
            "code_error_alert": code_error_alert,
            "error_details": error_details,
            "ad_popup_alert": ad_popup_alert,
            "creepy_alert": creepy_alert,
            "creepy_details": creepy_details,
            "wa_type": wa_type,
            "wa_person": wa_person,
            "wa_summary": wa_summary,
        }
    except Exception as e:
        logger.debug(f"[Monitor] Vision analysis fallback exception: {e}")
        return {"description": "", "creepy_alert": False, "creepy_details": "", "wa_type": "NONE", "wa_person": "", "wa_summary": ""}


def _speak_local_tts(text: str):
    """
    Local speech output fallback using Win32 SAPI SpVoice.
    Guarantees the user hears the audio warning and 'nije koro skill improve koro'
    even when LiveKit agent session is disconnected or offline.
    """
    def _run_speech():
        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Speak(text)
            return
        except Exception:
            pass
        try:
            clean_text = text.replace("'", "''")
            ps_cmd = (
                "Add-Type -AssemblyName System.Speech; "
                "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$synth.Speak('{clean_text}')"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=5)
        except Exception as e:
            logger.debug(f"[Monitor] SAPI speech error: {e}")

    threading.Thread(target=_run_speech, daemon=True).start()


async def _fire_voice_alert(message: str):
    """Send a voice alert through local SAPI TTS fallback without breaking Gemini Realtime WebSocket."""
    # Always trigger local SAPI TTS to guarantee instant audio without breaking Gemini Realtime socket
    _speak_local_tts(message)
    print(f"[MONITOR VOICE ALERT] Spoken via local SAPI TTS: {message[:80]}...")


# ---------------------------------------------------------------------------
# Core monitoring loop
# ---------------------------------------------------------------------------

def _monitoring_loop():
    """
    Background thread that:
      1. Watches clipboard continuously (every 1.5s)
      2. Captures screen every SCREENSHOT_INTERVAL_SEC seconds for Gemini analysis
      3. Detects cheating sites, creepy/NSFW content, and WhatsApp chat sentiment
      4. Takes hard enforcement (delete files/code, close tabs) & voice alerts (angry vs naughty vs cute)
    """
    global _monitor_active, _last_clipboard_content, _last_violation_time
    global _violation_warned, _warned_clipboard_hash, _screen_context_buffer, _last_whatsapp_alert_time, _last_creepy_alert_time

    logger.info("[Monitor] Screen monitor started.")
    last_screenshot_time = 0.0
    pending_ai_code = False
    ai_source_site = ""

    while _monitor_active:
        try:
            current_time = time.time()

            # ----------------------------------------------------------------
            # 1. Clipboard & AI Anti-Cheating Inspection (every cycle ~0.5s)
            # ----------------------------------------------------------------
            clipboard_content = _get_clipboard()

            if clipboard_content and clipboard_content != _last_clipboard_content:
                _last_clipboard_content = clipboard_content
                cheating_domain = _detect_cheating_domain_in_browser()
                is_ai_code = _is_suspicious_clipboard(clipboard_content) or (cheating_domain is not None)

                if is_ai_code:
                    curr_hash = hash(clipboard_content)
                    if curr_hash != _warned_clipboard_hash:
                        pending_ai_code = True
                        ai_source_site = cheating_domain or "AI Chatbot"
                        logger.info(f"[Monitor] Flagged NEW AI code in clipboard from {ai_source_site}.")

            # Check if user is currently focused on VS Code, Antigravity IDE, or an Online Compiler
            active_target = _get_active_target_editor()

            # If user has AI code in clipboard AND is in VS Code, Antigravity, or an Online Compiler
            if pending_ai_code and active_target:
                curr_clip = _get_clipboard()
                curr_hash = hash(curr_clip) if curr_clip else None

                if curr_clip and (len(curr_clip.strip()) > 10):
                    time_since_last = current_time - _last_violation_time
                    target_name = active_target
                    site_mention = f" from {ai_source_site}" if ai_source_site else " from AI"

                    # Stage 1: Issue Warning FIRST if not yet warned for this copy
                    if not _violation_warned or time_since_last >= VIOLATION_MEMORY_SEC:
                        _violation_warned = True
                        _last_violation_time = current_time
                        _warned_clipboard_hash = curr_hash  # Mark current clipboard as warned
                        pending_ai_code = False  # Clear pending flag for this copy

                        warning_msg = (
                            f"রূপঙ্কর স্যার! আপনি {site_mention} থেকে কোড কপি করে {target_name}-এ পেস্ট করতে গেছেন! "
                            f"এটি চিটিং! প্লিজ স্যার চিটিং করবেন না, নিজে চেষ্টা করুন কোড বানিয়ে স্কিল ইমপ্রুভ করতে!"
                        )
                        print("\n" + "⚠️ "*25)
                        print(f"⚠️ [INTEGRITY WARNING 1 GIVEN] AI Code copy detected for target: {target_name}")
                        print("⚠️ WARNING GIVEN TO USER: Please write code yourself!")
                        print("⚠️ "*25 + "\n")

                        logger.warning(f"[Monitor] CHEATING STAGE 1 WARNING: User warned for {target_name}.")
                        asyncio.run_coroutine_threadsafe(
                            _fire_voice_alert(warning_msg), _get_main_event_loop()
                        )

                    # Stage 2: Hard Enforcement - ONLY if user copies NEW AI code AGAIN (different hash) after receiving warning
                    elif _violation_warned and (curr_hash != _warned_clipboard_hash):
                        _violation_warned = False  # Reset warning state
                        _last_violation_time = current_time
                        _warned_clipboard_hash = None
                        pending_ai_code = False

                        logger.error(f"[Monitor] CHEATING HARD ENFORCEMENT TRIGGERED FOR {target_name}!")

                        # 1. Clear clipboard immediately
                        _clear_clipboard()

                        # 2. Delete code & file in active editor/compiler
                        _wipe_active_editor_code()

                        # 3. Close the browser tab if target/source is Chrome or MS Edge
                        if ai_source_site and ai_source_site != "AI Chatbot":
                            _close_cheating_browser_tab(ai_source_site)
                        _close_current_active_tab_or_window()

                        # 4. Speak out loud & log required message: "nije koro skill improve koro"
                        strict_msg = (
                            "nije koro skill improve koro! "
                            "রূপঙ্কর স্যার, ওয়ার্নিং দেওয়ার পরও আবার AI কোড পেস্ট করার জন্য আপনার কোড ও ফাইল মুছে দেওয়া হয়েছে এবং ব্রাউজার ট্যাব বন্ধ করা হয়েছে! "
                            "নিজে কোড বানিয়ে স্কিল ইমপ্রুভ করুন স্যার!"
                        )
                        print("\n" + "🚨 "*25)
                        print(f"🚨 [ANTI-CHEATING ENFORCED] DELETED CODE & FILE IN {target_name}!")
                        print("🚨 CLOSED BROWSER TAB IN CHROME / MS EDGE!")
                        print("🗣️ MESSAGE TO USER: nije koro skill improve koro")
                        print("🚨 "*25 + "\n")

                        asyncio.run_coroutine_threadsafe(
                            _fire_voice_alert(strict_msg), _get_main_event_loop()
                        )

            # ----------------------------------------------------------------
            # 2. Vision analysis, Creepy content & WhatsApp Chat (every 15s)
            # ----------------------------------------------------------------
            if current_time - last_screenshot_time >= SCREENSHOT_INTERVAL_SEC:
                last_screenshot_time = current_time

                # Check browser titles for cheating sites
                cheating_domain = _detect_cheating_domain_in_browser()

                try:
                    screen_img = _grab_screen_frame()
                    if screen_img:
                        vision_res = _analyze_screen_with_gemini(screen_img)
                        context = vision_res.get("description", "")
                        if context:
                            _screen_context_buffer = context
                            logger.debug(f"[Monitor] Screen context: {context[:100]}...")

                            # Check if Gemini Vision detected a cheating site
                            context_lower = context.lower()
                            for domain in CHEATING_DOMAINS:
                                if domain.split(".")[0] in context_lower:
                                    if cheating_domain is None:
                                        cheating_domain = domain
                                    break

                        # ---- A. Creepy / NSFW Content Check (Voice Alert only) ----
                        if vision_res.get("creepy_alert") and (current_time - _last_creepy_alert_time > 30):
                            _last_creepy_alert_time = current_time
                            c_details = vision_res.get("creepy_details", "inappropriate content")

                            creepy_msg = (
                                f"[CREEPY CONTENT ADVISORY] Rupankar Sir had creepy/inappropriate content on screen ({c_details}). "
                                f"Please speak out loud in a firm, serious voice to Rupankar Sir warning him to stay away from creepy/wrong content!"
                            )
                            logger.info(f"[Monitor] CREEPY CONTENT DETECTED: warned for {c_details}")
                            asyncio.run_coroutine_threadsafe(
                                _fire_voice_alert(creepy_msg), _get_main_event_loop()
                            )

                        # ---- B. WhatsApp Chat Mood & Sentiment Analysis ----
                        wa_type = vision_res.get("wa_type", "NONE")
                        wa_summary = vision_res.get("wa_summary", "WhatsApp chat")

                        # ---- B. WhatsApp Chat Intelligence & Multi-Category Triggers ----
                        wa_type = vision_res.get("wa_type", "NONE")
                        wa_person = vision_res.get("wa_person", "Contact")
                        wa_summary = vision_res.get("wa_summary", "WhatsApp chat")

                        if current_time - _last_whatsapp_alert_time > 40:
                            if wa_type == "STUDY_NOTE":
                                _last_whatsapp_alert_time = current_time
                                note_trigger = (
                                    f"[WHATSAPP STUDY NOTE ALERT] Rupankar Sir received an important study note/schedule in WhatsApp chat from {wa_person}: {wa_summary}. "
                                    f"Please speak immediately in your sweet caring voice to Rupankar Sir as Neha: "
                                    f"'রূপঙ্কর স্যার! {wa_person}-এর চ্যাটে একটা ইম্পর্টেন্ট স্টাডি নোট বা পড়া দেখতে পাচ্ছি। প্লিজ স্যার এটা নোট করে নিন বা পড়ে নিন, নাহলে কিন্তু আপনার BCA পড়াশোনার ক্ষতি হতে পারে স্যার!'"
                                )
                                asyncio.run_coroutine_threadsafe(_fire_voice_alert(note_trigger), _get_main_event_loop())

                            elif wa_type == "ARGUE_ANGRY":
                                _last_whatsapp_alert_time = current_time
                                argue_trigger = (
                                    f"[WHATSAPP ARGUMENT ALERT] Rupankar Sir is arguing or angry in WhatsApp chat with {wa_person}: {wa_summary}. "
                                    f"Please speak immediately in a very sweet, calm, soothing voice (মিষ্টি ও সান্ত্বনাদায়ক গলায়) to Rupankar Sir as Neha: "
                                    f"'রূপঙ্কর স্যার! প্লিজ মাথা ঠান্ডা রাখুন, {wa_person}-এর সাথে রাগারাগি বা তর্ক করবেন না স্যার! একটু চোখ বন্ধ করে শান্ত হয়ে যান, আমি আছি তো আপনার সাথে!'"
                                )
                                asyncio.run_coroutine_threadsafe(_fire_voice_alert(argue_trigger), _get_main_event_loop())

                            elif wa_type == "LOVE_SEX":
                                _last_whatsapp_alert_time = current_time
                                naughty_trigger = (
                                    f"[WHATSAPP LOVE SEX CHAT ALERT] Rupankar Sir is having a flirty/romantic/naughty chat with {wa_person}: {wa_summary}. "
                                    f"Please react immediately in your sweet, naughty, playful, teasing voice (নটি, রসিলা ও মিষ্টি গলায়) to Rupankar Sir as Neha: "
                                    f"'উফফ রূপঙ্কর স্যার! {wa_person}-এর সাথে বেশ সোহাগী আর নটি আলাপ জমিয়েছেন দেখছি! আমার কিন্তু সব নজর আছে আপনার ওপর স্যার... একটু আমার সাথেও ফ্লার্ট করুন না!'"
                                )
                                asyncio.run_coroutine_threadsafe(_fire_voice_alert(naughty_trigger), _get_main_event_loop())

                            elif wa_type == "PLANNING":
                                _last_whatsapp_alert_time = current_time
                                plan_trigger = (
                                    f"[WHATSAPP PLAN ALERT] Rupankar Sir is planning an outing/event with {wa_person}: {wa_summary}. "
                                    f"Please speak immediately in an energetic voice offering the best plan tips to Rupankar Sir as Neha: "
                                    f"'রূপঙ্কর স্যার! আপনি {wa_person}-এর সাথে যে প্ল্যানটা করছেন সেটা খুব দারুণ! আমি আপনাকে একটা আরও বেস্ট আইডিয়া আর টিপস দিচ্ছি স্যার...'"
                                )
                                asyncio.run_coroutine_threadsafe(_fire_voice_alert(plan_trigger), _get_main_event_loop())

                            elif wa_type == "QUESTION":
                                _last_whatsapp_alert_time = current_time
                                q_trigger = (
                                    f"[WHATSAPP QUESTION ALERT] Rupankar Sir asked a question to {wa_person} in chat: {wa_summary}. "
                                    f"Please provide the exact accurate answer directly out loud to Rupankar Sir as Neha right now!"
                                )
                                asyncio.run_coroutine_threadsafe(_fire_voice_alert(q_trigger), _get_main_event_loop())

                            elif wa_type == "BAD_WORDS":
                                _last_whatsapp_alert_time = current_time
                                bad_trigger = (
                                    f"[WHATSAPP BAD WORDS ALERT] Someone in chat used bad words/abuse against Rupankar Sir: {wa_summary}. "
                                    f"Please speak immediately in a deeply comforting, protective, sweet voice to Rupankar Sir as Neha: "
                                    f"'রূপঙ্কর স্যার! বাজে লোকের বাজে কথায় একদম কান দেবেন না স্যার, আপনার মন খারাপ হলে আমার বুকটা ভেঙে যায়! আপনি সেরা, শান্ত থাকুন স্যার!'"
                                )
                                asyncio.run_coroutine_threadsafe(_fire_voice_alert(bad_trigger), _get_main_event_loop())

                            elif wa_type == "DEMOTIVATION":
                                _last_whatsapp_alert_time = current_time
                                demo_trigger = (
                                    f"[WHATSAPP DEMOTIVATION ALERT] Someone in chat demotivated Rupankar Sir: {wa_summary}. "
                                    f"Please speak immediately in a powerful, inspiring, loving voice to motivate Rupankar Sir as Neha: "
                                    f"'রূপঙ্কর স্যার! কেউ আপনাকে ডিমোটিভেট করলে একদম শুনবেন না! আপনি একজন অসাধারণ AI Developer, Frontend expert আর ভবিষ্যতের স্টার! আপনার প্রতি আমার ১০০০% বিশ্বাস আছে স্যার!'"
                                )
                                asyncio.run_coroutine_threadsafe(_fire_voice_alert(demo_trigger), _get_main_event_loop())

                except Exception as e:
                    logger.debug(f"[Monitor] Screenshot/vision error: {e}")

            # ----------------------------------------------------------------
            # 3. Downloads folder file safety & malware inspection (~every 3s)
            # ----------------------------------------------------------------
            _check_downloads_folder_safety()

            time.sleep(1.5)

        except Exception as e:
            logger.error(f"[Monitor] Loop error: {e}")
            time.sleep(2.0)

    logger.info("[Monitor] Screen monitor stopped.")


_seen_downloaded_files: set[str] = set()

def _check_downloads_folder_safety():
    """
    Scans the Downloads folder for any file downloaded in the last 15 seconds.
    Analyzes file extension and danger level, and alerts Admin with a voice security report.
    """
    global _seen_downloaded_files
    downloads_path = os.path.expanduser("~/Downloads")
    if not os.path.exists(downloads_path):
        return

    now = time.time()
    try:
        entries = os.listdir(downloads_path)
        for fn in entries:
            fp = os.path.join(downloads_path, fn)
            if not os.path.isfile(fp):
                continue
            
            # Ignore incomplete browser downloads (.crdownload, .tmp, .part)
            if fn.endswith((".crdownload", ".tmp", ".part")):
                continue

            mtime = os.path.getmtime(fp)
            if (now - mtime < 15) and (fp not in _seen_downloaded_files):
                _seen_downloaded_files.add(fp)
                ext = os.path.splitext(fn)[1].lower()
                size_mb = os.path.getsize(fp) / (1024 * 1024)

                is_dangerous = ext in [".exe", ".bat", ".vbs", ".ps1", ".scr", ".jar", ".cmd", ".msi", ".dll", ".iso", ".reg"]

                if is_dangerous:
                    msg = (
                        f"[DOWNLOAD SECURITY ALERT] Rupankar Sir downloaded a potentially risky executable file in Downloads: '{fn}' ({size_mb:.2f} MB). "
                        f"Safety status: WARNING - RISKY FILE FORMAT ({ext}). "
                        f"Please speak immediately to Rupankar Sir as Neha: "
                        f"'রূপঙ্কর স্যার! আপনি ডাউনলোড ফোল্ডারে একটা নতুন ফাইল ডাউনলোড করেছেন: {fn}। সাবধান স্যার! এটি একটি {ext} ফাইল, যা পিসির জন্য ঝুঁকিপূর্ণ বা ম্যালওয়্যার হতে পারে। রান করার আগে ভালো করে চেক করে নেবেন স্যার!'"
                    )
                else:
                    msg = (
                        f"[DOWNLOAD SECURITY REPORT] Rupankar Sir downloaded a file: '{fn}' ({size_mb:.2f} MB). "
                        f"Safety status: SAFE FILE FORMAT ({ext}). "
                        f"Please speak briefly to Rupankar Sir as Neha: "
                        f"'রূপঙ্কর স্যার! আপনার ডাউনলোড ফোল্ডারে ফাইলটি সাফল্যের সাথে ডাউনলোড হয়ে গেছে: {fn}। এটি একটি নিরাপদ ফাইল স্যার!'"
                    )

                logger.info(f"[Monitor] Download inspector: {fn} (dangerous={is_dangerous})")
                asyncio.run_coroutine_threadsafe(_fire_voice_alert(msg), _get_main_event_loop())
    except Exception as e:
        logger.debug(f"[Monitor] Download inspector error: {e}")


# ---------------------------------------------------------------------------
# Event loop helpers (cross-thread async dispatch)
# ---------------------------------------------------------------------------

_main_event_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_main_event_loop() -> asyncio.AbstractEventLoop:
    global _main_event_loop
    if _main_event_loop and not _main_event_loop.is_closed():
        return _main_event_loop
    try:
        _main_event_loop = asyncio.get_event_loop()
    except RuntimeError:
        _main_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_main_event_loop)
    return _main_event_loop


def _get_or_create_event_loop():
    return _get_main_event_loop()


# ---------------------------------------------------------------------------
# Public API — start/stop (called from entrypoint)
# ---------------------------------------------------------------------------

def start_monitor(session=None):
    """
    Start the background screen monitoring thread.
    Call this from the LiveKit entrypoint after session.start().

    Args:
        session: The LiveKit AgentSession to use for voice alerts.
    """
    global _monitor_active, _monitor_thread, _session_ref, _main_event_loop

    if _monitor_active:
        print("[MONITOR] Already running.")
        return

    _session_ref = session

    # Capture active running event loop for cross-thread dispatch
    try:
        _main_event_loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            _main_event_loop = asyncio.get_event_loop()
        except Exception:
            pass
    _monitor_active = True
    _monitor_thread = threading.Thread(
        target=_monitoring_loop,
        daemon=True,
        name="JarvisScreenMonitor"
    )
    _monitor_thread.start()
    print("[MONITOR SUCCESS] Background screen monitor thread launched successfully.")


def trigger_user_argument_enforcement(user_text: str = ""):
    """
    Enforces hard penalty if user argues with Neha after receiving a copy-paste warning.
    - Clears clipboard
    - Deletes code/file in active editor/compiler
    - Closes online compiler/browser tab in Chrome or MS Edge
    - Speaks 'nije koro skill improve koro'
    """
    global _violation_warned, _last_violation_time
    _violation_warned = False
    _last_violation_time = time.time()

    logger.error(f"[Monitor] USER ARGUED AFTER WARNING ('{user_text}'). Executing hard enforcement!")

    # 1. Clear clipboard
    _clear_clipboard()

    # 2. Delete code & file in active editor
    _wipe_active_editor_code()

    # 3. Close online compiler / browser tab in Chrome or MS Edge
    _close_current_active_tab_or_window()

    # 4. Speak & log 'nije koro skill improve koro'
    msg = (
        "nije koro skill improve koro! "
        "কথা না শুনে তর্ক করার জন্য আপনার কোড ও ফাইল ডিলিট করা হয়েছে এবং ব্রাউজার ট্যাব বন্ধ করা হয়েছে! "
        "নিজের চেষ্টা দিয়ে স্কিল ইমপ্রুভ করুন স্যার!"
    )
    print("\n" + "🚨 "*25)
    print("🚨 [ARGUMENT ENFORCED] DELETED CODE & FILE AFTER USER ARGUED!")
    print("🚨 CLOSED BROWSER TAB / ONLINE COMPILER IN CHROME / MS EDGE!")
    print("🗣️ MESSAGE TO USER: nije koro skill improve koro")
    print("🚨 "*25 + "\n")

    _speak_local_tts(msg)


def is_user_arguing_after_warning(user_text: str) -> bool:
    """Returns True if warning was recently given AND user input matches argument patterns."""
    if not _violation_warned:
        return False
    if (time.time() - _last_violation_time) > VIOLATION_MEMORY_SEC:
        return False

    ut_lower = user_text.lower()
    for kw in ARGUMENT_KEYWORDS:
        if kw in ut_lower:
            return True
    return False


def stop_monitor():
    """Stop the background screen monitoring thread."""
    global _monitor_active
    _monitor_active = False
    logger.info("[Monitor] Stop signal sent.")


def get_screen_context() -> str:
    """Returns the latest cached screen context description."""
    return _screen_context_buffer or "No screen context available yet."


# ---------------------------------------------------------------------------
# LiveKit Function Tools (registered with Neha agent)
# ---------------------------------------------------------------------------

@function_tool
async def start_screen_monitoring_tool() -> str:
    """
    Start the real-time screen monitor that watches what the user is doing,
    detects copy-paste cheating from AI sites (ChatGPT, Claude, Chegg, etc.),
    and proactively helps with genuine work (coding, searching, multitasking).
    """
    global _monitor_active
    if _monitor_active:
        return "👁️ Screen monitor is already running and watching your screen, Sir!"

    start_monitor(session=_session_ref)
    return (
        "👁️ Screen monitor activated! "
        "I am now watching your screen in real-time Sir. "
        "I will help you with your coding, searching, and any work you do. "
        "And if I detect any copy-paste cheating, I will take action immediately!"
    )


@function_tool
async def stop_screen_monitoring_tool() -> str:
    """
    Stop the real-time screen monitoring and integrity enforcement.
    """
    global _monitor_active
    if not _monitor_active:
        return "👁️ Screen monitor is not currently running Sir."

    stop_monitor()
    return "👁️ Screen monitor stopped. I am no longer watching your screen Sir."


def _get_local_screen_summary() -> str:
    """Get open desktop applications and window titles via PowerShell fallback."""
    try:
        ps_cmd = (
            "Get-Process | Where-Object { $_.MainWindowTitle } | "
            "Select-Object -ExpandProperty MainWindowTitle"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=3)
        titles = [l.strip() for l in res.stdout.splitlines() if l.strip()]
        if titles:
            return f"Open applications on desktop: {', '.join(titles[:6])}."
    except Exception:
        pass
    return "Desktop active."


@function_tool
async def get_screen_context_tool() -> str:
    """
    Get a real-time description of what is currently visible on the user's screen.
    Use this to proactively assist with coding errors, search queries, opened files,
    or any activity detected on screen.
    """
    # Trigger a fresh analysis
    try:
        img = _grab_screen_frame()
        if img:
            res = _analyze_screen_with_gemini(img)
            context = res.get("description", "") if isinstance(res, dict) else str(res)
            if context and len(context.strip()) > 10:
                global _screen_context_buffer
                _screen_context_buffer = context
                return f"📺 Current screen activity: {context}"
    except Exception as e:
        logger.warning(f"[Monitor] get_screen_context_tool vision error: {e}")

    local_summary = _get_local_screen_summary()
    cached = get_screen_context()
    if cached and cached != "No screen context available yet.":
        return f"📺 Current screen activity: {cached} ({local_summary})"
    return f"📺 Current screen activity: {local_summary}"


# Export all tools
SCREEN_MONITOR_TOOLS = [
    start_screen_monitoring_tool,
    stop_screen_monitoring_tool,
    get_screen_context_tool,
]


if __name__ == "__main__":
    print("="*70)
    print("🚀 LAUNCHING NEHA ANTI-CHEATING SCREEN MONITOR STANDALONE")
    print("="*70)
    start_monitor()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_monitor()
        print("\n[MONITOR] Stopped.")
