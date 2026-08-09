import os
import subprocess
import sys
import logging
import asyncio
import time
from fuzzywuzzy import process
from livekit.agents import function_tool

try:
    import pygetwindow as gw
except ImportError:
    gw = None

sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------------------------
# File Index Cache — avoids re-walking D:/ every call
# -----------------------------------------------
_file_cache: list = []
_file_cache_time: float = 0.0
_FILE_CACHE_TTL: float = 300.0  # 5 minutes


async def _get_file_index(base_dirs) -> list:
    """Return cached file index, refreshing only if older than TTL."""
    global _file_cache, _file_cache_time
    now = time.monotonic()
    if _file_cache and (now - _file_cache_time) < _FILE_CACHE_TTL:
        logger.info(f"✅ Cache hit — {len(_file_cache)} files (no re-scan needed)")
        return _file_cache

    logger.info(f"🔍 Scanning directories: {base_dirs} ...")
    # Run os.walk in a thread so it doesn't block the async event loop
    def _walk():
        index = []
        for base_dir in base_dirs:
            for root, _, files in os.walk(base_dir):
                for f in files:
                    index.append({
                        "name": f,
                        "path": os.path.join(root, f),
                        "type": "file"
                    })
        return index

    _file_cache = await asyncio.to_thread(_walk)
    _file_cache_time = now
    logger.info(f"✅ Indexed {len(_file_cache)} files from {base_dirs}")
    return _file_cache


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
            logger.info(f"🪟 window focus में है: {window.title}")
            return True
    logger.warning("⚠ Focus करने के लिए window नहीं मिली।")
    return False


async def search_file(query, index):
    choices = [item["name"] for item in index]
    if not choices:
        logger.warning("⚠ Match करने के लिए कोई files नहीं हैं।")
        return None

    best_match, score = process.extractOne(query, choices)
    logger.info(f"🔍 Matched '{query}' to '{best_match}' (Score: {score})")
    if score > 70:
        for item in index:
            if item["name"] == best_match:
                return item
    return None


async def open_file(item):
    try:
        logger.info(f"📂 File खोल रहे हैं: {item['path']}")
        if os.name == 'nt':
            os.startfile(item["path"])
        else:
            subprocess.call(['open' if sys.platform == 'darwin' else 'xdg-open', item["path"]])
        await focus_window(item["name"])
        return f"✅ File open हो गई।: {item['name']}"
    except Exception as e:
        logger.error(f"❌ File open करने में error आया।: {e}")
        return f"❌ File open करने में विफल रहा। {e}"


async def handle_command(command, index):
    item = await search_file(command, index)
    if item:
        return await open_file(item)
    else:
        logger.warning("❌ File नहीं मिली।")
        return "❌ File नहीं मिली।"


from jarvis_file_text_operations import _resolve_folder_path


@function_tool
async def Play_file(name: str) -> str:
    """Open and play any media, document, archive, or executable file (MP4, MP3, PDF, PPT, Word, Excel, images, EXE, ZIP)."""
    # 1. Fast direct resolution via _resolve_folder_path
    resolved = _resolve_folder_path(name)
    if os.path.exists(resolved) and os.path.isfile(resolved):
        try:
            os.startfile(resolved)
            await focus_window(os.path.basename(resolved))
            return f"✅ Successfully opened '{os.path.basename(resolved)}'."
        except Exception as e:
            return f"❌ Failed to open '{os.path.basename(resolved)}': {e}"

    # 2. Fallback index search across Desktop, Downloads, Documents, D:\, E:\
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
    index = await _get_file_index(valid_folders)
    command = name.strip()
    return await handle_command(command, index)

