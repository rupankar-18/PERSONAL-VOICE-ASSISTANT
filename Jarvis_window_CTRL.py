import os
import subprocess
import logging
import sys
import asyncio
import time
from fuzzywuzzy import process

try:
    from livekit.agents import function_tool
except ImportError:
    def function_tool(func):
        return func

try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None
    win32con = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None

# Setup encoding and logger
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# App command map
APP_MAPPINGS = {
    "notepad": "notepad",
    "calculator": "calc",
    "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "whatsapp": "start whatsapp:",
    "vlc": "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe",
    "command prompt": "cmd",
    "control panel": "control",
    "settings": "start ms-settings:",
    "paint": "mspaint",
    "vs code": "code",
    "vscode": "code",
    "postman": os.path.expandvars(r"%LOCALAPPDATA%\Postman\Postman.exe")
}

# -----------------------------------------------
# Item Index Cache — avoids re-walking D:/ every call
# -----------------------------------------------
_item_cache: list = []
_item_cache_time: float = 0.0
_ITEM_CACHE_TTL: float = 300.0  # 5 minutes


async def _get_item_index(base_dirs) -> list:
    """Return cached file+folder index, refreshing only if older than TTL."""
    global _item_cache, _item_cache_time
    now = time.monotonic()
    if _item_cache and (now - _item_cache_time) < _ITEM_CACHE_TTL:
        logger.info(f"✅ Cache hit — {len(_item_cache)} items (no re-scan needed)")
        return _item_cache

    logger.info(f"🔍 Scanning directories: {base_dirs} ...")
    # Run os.walk in a thread so it doesn't block the async event loop
    def _walk():
        item_index = []
        for base_dir in base_dirs:
            for root, dirs, files in os.walk(base_dir):
                for d in dirs:
                    item_index.append({"name": d, "path": os.path.join(root, d), "type": "folder"})
                for f in files:
                    item_index.append({"name": f, "path": os.path.join(root, f), "type": "file"})
        return item_index

    _item_cache = await asyncio.to_thread(_walk)
    _item_cache_time = now
    logger.info(f"✅ Indexed {len(_item_cache)} items.")
    return _item_cache


# -------------------------
# Global focus utility
# -------------------------
async def focus_window(title_keyword: str) -> bool:
    if not gw:
        logger.warning("⚠ pygetwindow not available")
        return False

    await asyncio.sleep(0.1)  # fast window focus
    title_keyword = title_keyword.lower().strip()

    for window in gw.getAllWindows():
        if title_keyword in window.title.lower():
            if window.isMinimized:
                window.restore()
            window.activate()
            return True
    return False


from jarvis_file_text_operations import _translate_bn_to_en


async def search_item(query, index, item_type):
    filtered = [item for item in index if item["type"] == item_type]
    choices = [item["name"] for item in filtered]
    if not choices:
        return None

    # Translate Bengali speech to English phonetic text for fuzzy matching against Windows file names
    translated_query = _translate_bn_to_en(query)
    
    match1, score1 = process.extractOne(query, choices) if choices else (None, 0)
    match2, score2 = process.extractOne(translated_query, choices) if (choices and translated_query) else (None, 0)

    best_match = match2 if score2 >= score1 else match1
    best_score = max(score1, score2)

    logger.info(f"🔍 Matched '{query}' (translated: '{translated_query}') to '{best_match}' with score {best_score}")
    if best_score > 60:
        for item in filtered:
            if item["name"] == best_match:
                return item
    return None


# File/folder actions
async def open_folder(path):
    try:
        os.startfile(path) if os.name == 'nt' else subprocess.call(['xdg-open', path])
        await focus_window(os.path.basename(path))
    except Exception as e:
        logger.error(f"❌ फ़ाइल open करने में error आया। {e}")

async def play_file(path):
    try:
        os.startfile(path) if os.name == 'nt' else subprocess.call(['xdg-open', path])
        await focus_window(os.path.basename(path))
    except Exception as e:
        logger.error(f"❌ फ़ाइल open करने में error आया।: {e}")

async def create_folder(path):
    try:
        os.makedirs(path, exist_ok=True)
        return f"✅ Folder create हो गया।: {path}"
    except Exception as e:
        return f"❌ फ़ाइल create करने में error आया।: {e}"

async def rename_item(old_path, new_path):
    try:
        os.rename(old_path, new_path)
        return f"✅ नाम बदलकर {new_path} कर दिया गया।"
    except Exception as e:
        return f"❌ नाम बदलना fail हो गया: {e}"

async def delete_item(path):
    try:
        if os.path.isdir(path):
            os.rmdir(path)
        else:
            os.remove(path)
        return f"🗑️ Deleted: {path}"
    except Exception as e:
        return f"❌ Delete नहीं हुआ।: {e}"


import win32api

def _get_hwnd_for_app(app_name: str):
    if not win32gui:
        return None
    app_lower = app_name.lower().strip()
    
    title_keywords = {
        "vs code": ["visual studio code", "code", "vsc"],
        "vscode": ["visual studio code", "code", "vsc"],
        "whatsapp": ["whatsapp"],
        "notepad": ["notepad", "untitled - notepad"],
        "calculator": ["calculator", "calc"],
        "chrome": ["chrome", "google chrome"],
        "google": ["chrome", "google chrome"],
        "edge": ["edge", "microsoft edge"],
        "microsoft edge": ["edge", "microsoft edge"],
        "cmd": ["command prompt", "cmd"],
        "paint": ["paint"],
    }
    
    search_terms = title_keywords.get(app_lower, [app_lower])
    found_hwnds = []

    def enum_windows_callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            txt = win32gui.GetWindowText(hwnd).lower()
            if txt:
                for term in search_terms:
                    if term in txt:
                        try:
                            rect = win32gui.GetWindowRect(hwnd)
                            w = rect[2] - rect[0]
                            h = rect[3] - rect[1]
                            if w > 150 and h > 150:
                                found_hwnds.append(hwnd)
                                break
                        except Exception:
                            pass

    win32gui.EnumWindows(enum_windows_callback, None)
    return found_hwnds[0] if found_hwnds else None


def _set_hwnd_position(hwnd, corner: str) -> bool:
    if not win32gui:
        return False

    try:
        screen_w = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        screen_h = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
    except Exception:
        screen_w, screen_h = 1920, 1080

    taskbar_h = 40
    usable_h = max(100, screen_h - taskbar_h)
    half_w = screen_w // 2
    half_h = usable_h // 2

    c = corner.lower().strip().replace(" ", "_").replace("-", "_")

    if c in ("upper_left", "top_left", "left_upper", "top_left_corner", "upper_left_corner"):
        x, y, w, h = 0, 0, half_w, half_h
    elif c in ("upper_right", "top_right", "right_upper", "top_right_corner", "upper_right_corner"):
        x, y, w, h = half_w, 0, half_w, half_h
    elif c in ("lower_left", "bottom_left", "left_lower", "bottom_left_corner", "lower_left_corner"):
        x, y, w, h = 0, half_h, half_w, half_h
    elif c in ("lower_right", "bottom_right", "right_lower", "bottom_right_corner", "lower_right_corner"):
        x, y, w, h = half_w, half_h, half_w, half_h
    elif c in ("left_half", "left", "left_portion", "left_side", "shift_left"):
        x, y, w, h = 0, 0, half_w, usable_h
    elif c in ("right_half", "right", "right_portion", "right_side", "shift_right"):
        x, y, w, h = half_w, 0, half_w, usable_h
    elif c in ("top_half", "upper_half", "top_portion", "upper_portion"):
        x, y, w, h = 0, 0, screen_w, half_h
    elif c in ("bottom_half", "lower_half", "bottom_portion", "lower_portion"):
        x, y, w, h = 0, half_h, screen_w, half_h
    elif c in ("maximize", "full", "fullscreen"):
        x, y, w, h = 0, 0, screen_w, usable_h
    else:
        x, y, w, h = 0, 0, half_w, half_h

    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.MoveWindow(hwnd, x, y, w, h, True)
        
        # Safely attempt focus bringing without failing the positioning call
        try:
            win32api.keybd_event(0x12, 0, 0, 0)
            win32gui.SetForegroundWindow(hwnd)
            win32api.keybd_event(0x12, 0, win32con.KEYEVENTF_KEYUP, 0)
        except Exception:
            pass

        return True
    except Exception as e:
        logger.warning(f"Error moving hwnd {hwnd}: {e}")
        return False


@function_tool
async def position_app_window(app_name: str, corner: str) -> str:
    """Move or snap an open application window to a specific corner or quadrant of the screen.
    
    Args:
        app_name: Name of the application (e.g. 'whatsapp', 'vs code', 'notepad', 'calculator', 'chrome')
        corner: Screen position ('upper_left', 'upper_right', 'lower_left', 'lower_right', 'left_half', 'right_half', 'maximize')
    """
    app_clean = app_name.lower().strip()
    hwnd = _get_hwnd_for_app(app_clean)
    
    if not hwnd:
        await open(app_clean)
        await asyncio.sleep(0.2)
        hwnd = _get_hwnd_for_app(app_clean)

    if hwnd and _set_hwnd_position(hwnd, corner):
        return f"Successfully moved '{app_clean}' window to {corner} corner of the screen."
    else:
        return f"Could not find or position window for '{app_clean}'."


@function_tool
async def arrange_quadrant_windows(
    upper_left_app: str = "",
    upper_right_app: str = "",
    lower_left_app: str = "",
    lower_right_app: str = ""
) -> str:
    """Open multiple applications and tile/arrange them into the 4 corners (quadrants) of the desktop screen simultaneously.
    
    Args:
        upper_left_app: App for upper left corner (e.g. 'notepad', 'chrome', 'calculator')
        upper_right_app: App for upper right corner (e.g. 'whatsapp', 'vs code')
        lower_left_app: App for lower left corner (e.g. 'calculator', 'notepad')
        lower_right_app: App for lower right corner (e.g. 'vs code', 'chrome')
    """
    results = []
    assignments = [
        (upper_left_app, "upper_left"),
        (upper_right_app, "upper_right"),
        (lower_left_app, "lower_left"),
        (lower_right_app, "lower_right"),
    ]

    for app_name, corner in assignments:
        if app_name:
            app_clean = app_name.lower().strip()
            hwnd = _get_hwnd_for_app(app_clean)
            if not hwnd:
                await open(app_clean)

    await asyncio.sleep(0.3)

    for app_name, corner in assignments:
        if app_name:
            app_clean = app_name.lower().strip()
            hwnd = _get_hwnd_for_app(app_clean)
            if hwnd and _set_hwnd_position(hwnd, corner):
                results.append(f"{app_clean} -> {corner}")
            else:
                results.append(f"{app_clean} (opened)")

    return f"Screen layout arranged: {', '.join(results)}"


# App control
@function_tool
async def open(app_title: str) -> str:
    """Launch or open a desktop application by its name (e.g. notepad, chrome, calculator, paint, vs code, vlc, control panel). Call ONLY when user explicitly asks to open an application."""
    app_title = app_title.lower().strip()
    app_command = APP_MAPPINGS.get(app_title, app_title)
    try:
        await asyncio.create_subprocess_shell(f'start "" "{app_command}"', shell=True)
        focused = await focus_window(app_title)
        if focused:
            return f"🚀 App launch हुआ और focus में है: {app_title}."
        else:
            return f"🚀 {app_title} Launch किया गया, लेकिन window पर focus नहीं हो पाया।"
    except Exception as e:
        return f"❌ {app_title} Launch नहीं हो पाया।: {e}"

@function_tool
async def close(window_title: str) -> str:
    """Close an open application, browser window, or search tab by keyword (e.g. 'chrome', 'edge', 'microsoft edge', 'google', 'tab', 'vs code', 'notepad', 'calculator'). Call ONLY when user explicitly asks to close a window, browser, tab, or app."""
    if not win32gui:
        return "❌ win32gui not available"

    title_clean = window_title.lower().strip()

    # Special handling for closing current active browser tab
    if title_clean in ("tab", "search tab", "current tab", "browser tab", "close tab"):
        try:
            import pyautogui
            pyautogui.hotkey('ctrl', 'w')
            return "Successfully closed active browser tab."
        except Exception as e:
            logger.warning(f"Failed hotkey close tab: {e}")

    # Alias keywords for browsers and search tabs
    keywords = [title_clean]
    if title_clean in ("chrome", "google", "google chrome"):
        keywords = ["chrome", "google chrome", "new tab", "google"]
    elif title_clean in ("edge", "microsoft edge", "msedge"):
        keywords = ["edge", "microsoft edge", "msedge"]
    elif "tab" in title_clean or "search" in title_clean:
        keywords = ["chrome", "edge", "microsoft edge", "google", "bing", "tab"]

    closed_count = 0
    def enumHandler(hwnd, _):
        nonlocal closed_count
        try:
            if win32gui.IsWindowVisible(hwnd):
                w_text = win32gui.GetWindowText(hwnd).lower()
                for kw in keywords:
                    if kw in w_text:
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                        closed_count += 1
                        break
        except Exception:
            pass

    try:
        win32gui.EnumWindows(enumHandler, None)
    except Exception as e:
        logger.warning(f"EnumWindows warning: {e}")
    
    # Process killing fallbacks for full browser termination
    if title_clean in ("chrome", "google", "google chrome"):
        try:
            await asyncio.create_subprocess_shell("taskkill /IM chrome.exe /F >nul 2>&1", shell=True)
        except Exception:
            pass
    elif title_clean in ("edge", "microsoft edge", "msedge"):
        try:
            await asyncio.create_subprocess_shell("taskkill /IM msedge.exe /F >nul 2>&1", shell=True)
        except Exception:
            pass
    elif title_clean in ("whatsapp", "whatsapp desktop", "whatsapp web"):
        try:
            await asyncio.create_subprocess_shell("taskkill /IM WhatsApp.exe /F >nul 2>&1", shell=True)
            await asyncio.create_subprocess_shell("taskkill /IM WhatsApp.Desktop.exe /F >nul 2>&1", shell=True)
        except Exception:
            pass

    return f"Successfully closed window or search tabs matching '{window_title}'."


from jarvis_file_text_operations import _resolve_folder_path


# Jarvis command logic
@function_tool
async def folder_file(command: str) -> str:
    """Open, create, rename, or delete local folders and files across Desktop, Downloads, Documents, D:, E:, C:."""
    # 1. Fast direct resolution via _resolve_folder_path
    resolved = _resolve_folder_path(command)
    if os.path.exists(resolved):
        try:
            os.startfile(resolved)
            await focus_window(os.path.basename(resolved))
            return f"✅ Successfully opened: {os.path.basename(resolved)}"
        except Exception as e:
            return f"❌ Failed to open {os.path.basename(resolved)}: {e}"

    # 2. Search across all user system directories
    home = os.path.expanduser("~")
    folders_to_index = [
        os.path.join(home, "OneDrive", "Desktop"),
        os.path.join(home, "Desktop"),
        os.path.join(home, "Downloads"),
        os.path.join(home, "OneDrive", "Documents"),
        os.path.join(home, "Documents"),
        "D:\\",
        "E:\\"
    ]
    valid_folders = [f for f in folders_to_index if os.path.exists(f)]
    index = await _get_item_index(valid_folders)  # Uses cache — no re-scan!
    command_lower = command.lower()

    if "folder" in command_lower or "open folder" in command_lower or "directory" in command_lower:
        item = await search_item(command, index, "folder")
        if item:
            await open_folder(item["path"])
            return f"✅ Folder opened: {item['name']}"

    item = await search_item(command, index, "file") or await search_item(command, index, "folder")
    if item:
        await play_file(item["path"])
        return f"✅ Opened: {item['name']}"

    return f"⚠ Could not locate file or folder for '{command}'."
