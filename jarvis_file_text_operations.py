import os
import shutil
import asyncio
import logging
import urllib.parse
import webbrowser
import time
import re
import zipfile
import ctypes
import subprocess
from typing import List, Tuple
from livekit.agents import function_tool

try:
    import win32clipboard
    WIN32CLIP_AVAILABLE = True
except ImportError:
    WIN32CLIP_AVAILABLE = False

try:
    import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False

import pyperclip
import pyautogui
from pynput.keyboard import Key, Controller as KeyboardController
from jarvis_whatsapp import send_whatsapp_message

logger = logging.getLogger(__name__)
pyautogui.FAILSAFE = False
_keyboard = KeyboardController()


BN_EN_PHONETIC_MAP = {
    "ব্লিংকি": "blinky", "ব্লিনকি": "blinky", "ব্লিংকির": "blinky", "ব্লিনকির": "blinky", "ব্লিংক": "blink",
    "ডাটা": "data", "ডেটা": "data", "ক্লিন": "clean", "ক্লিনের": "clean", "কিল": "",
    "জাভা": "java", "জাভার": "java", "ডাবা": "java",
    "পাওয়ার": "power", "পাওয়ার": "power", "বিআই": "bi",
    "কোড": "code", "কোডের": "code", "পাইথন": "python", "পাইথনের": "python",
    "নোট": "note", "নোটস": "notes", "নোটপ্যাড": "notepad",
    "ফাইল": "file", "ফাইলটা": "file", "ফোল্ডার": "folder", "ফোল্ডারটা": "folder",
    "জিপ": "zip", "প্যাক": "pack", "ডেস্কটপ": "desktop", "ডাউনলোড": "download",
    "ডকুমেন্ট": "document", "পিকচার": "picture", "ইমেজ": "image", "ভিডিও": "video",
    "অডিও": "audio", "সোং": "song", "মিউজিক": "music", "সিভি": "cv", "রিপোর্ট": "report",
    "সার্টিফিকেট": "certificate", "কোর্স": "course", "প্রজেক্ট": "project", "অ্যাপ": "app"
}


def _translate_bn_to_en(text: str) -> str:
    """Translates Bengali phonetic words in a string into English words."""
    words = text.split()
    translated = []
    for w in words:
        w_clean = re.sub(r'[^\u0980-\u09FFa-zA-Z0-9]', '', w)
        if w_clean in BN_EN_PHONETIC_MAP:
            tr = BN_EN_PHONETIC_MAP[w_clean]
            if tr:
                translated.append(tr)
        else:
            translated.append(w_clean)
    return " ".join(translated)


def _find_file_in_dir(directory: str, target_name: str) -> Optional[str]:
    """Helper to locate a target file/folder inside directory using exact, extensionless, phonetic Bengali-English, and fuzzy token matching."""
    if not os.path.exists(directory):
        return None

    def normalize(s: str) -> str:
        return re.sub(r'[^a-zA-Z0-9]', '', s).lower()

    target_clean = target_name.strip().lower()
    target_norm = normalize(target_clean)
    target_stem = os.path.splitext(target_clean)[0]

    # Translate any Bengali phonetic words to English (e.g. 'ব্লিনকির ডাটা ক্লিন' -> 'blinky data clean')
    translated_target = _translate_bn_to_en(target_clean).lower()
    translated_stem = os.path.splitext(translated_target)[0]
    translated_norm = normalize(translated_target)

    try:
        entries = os.listdir(directory)
    except Exception:
        return None

    # Pass 1: Direct Exact / Stem match (English or Bengali)
    for entry in entries:
        e_lower = entry.lower()
        e_stem = os.path.splitext(e_lower)[0]
        if e_lower in (target_clean, translated_target) or e_stem in (target_clean, target_stem, translated_stem):
            return os.path.join(directory, entry)

    # Pass 2: Normalized alphanumeric match
    for entry in entries:
        e_norm = normalize(entry)
        e_stem_norm = normalize(os.path.splitext(entry)[0])
        if (target_norm and (e_norm == target_norm or e_stem_norm == target_norm)) or \
           (translated_norm and (e_norm == translated_norm or e_stem_norm == translated_norm)):
            return os.path.join(directory, entry)

    # Pass 3: Token-based multi-word fuzzy match (e.g. ['blinky', 'data', 'clean'] matching 'Blinky Data Clean.zip')
    tokens = [t for t in re.split(r'[\s_\-\.\,]+', translated_target) if len(t) >= 2 and t not in ('zip', 'file', 'folder', 'the', 'a', 'in', 'on', 'my', 'of')]
    if tokens:
        best_entry = None
        max_matches = 0
        for entry in entries:
            e_lower = entry.lower()
            e_tokens = set(re.split(r'[\s_\-\.\,]+', os.path.splitext(e_lower)[0]))
            matched_count = sum(1 for tok in tokens if any(tok in e_tok or e_tok in tok for e_tok in e_tokens))
            if matched_count > max_matches:
                max_matches = matched_count
                best_entry = entry

        if best_entry and max_matches >= 1:
            return os.path.join(directory, best_entry)

    # Pass 4: Substring match (e.g. searching 'java' finds 'java.zip' or 'java_course')
    search_stems = [target_stem, translated_stem]
    for stem in search_stems:
        if stem and len(stem) >= 2:
            for entry in entries:
                e_lower = entry.lower()
                e_stem = os.path.splitext(e_lower)[0]
                if stem in e_lower or stem in e_stem:
                    return os.path.join(directory, entry)

    # Pass 5: 1-level subfolder recursive search
    for entry in entries:
        full_sub = os.path.join(directory, entry)
        if os.path.isdir(full_sub) and not entry.startswith(".") and entry.lower() not in ("node_modules", "__pycache__", "venv"):
            try:
                sub_entries = os.listdir(full_sub)
                for sub_e in sub_entries:
                    sub_e_lower = sub_e.lower()
                    sub_e_stem = os.path.splitext(sub_e_lower)[0]
                    if sub_e_lower in (target_clean, translated_target) or sub_e_stem in (target_clean, target_stem, translated_stem):
                        return os.path.join(full_sub, sub_e)
            except Exception:
                pass

    return None


def _find_latest_archive(search_dirs=None) -> Optional[str]:
    """Locate the most recently modified archive file (.zip, .tar, .gz, .tgz, .rar, .7z) across search directories."""
    home = os.path.expanduser("~")
    if not search_dirs:
        search_dirs = [
            os.path.join(home, "OneDrive", "Desktop"),
            os.path.join(home, "Desktop"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "OneDrive", "Documents"),
            os.path.join(home, "Documents")
        ]

    latest_file = None
    latest_mtime = 0
    archive_exts = ('.zip', '.tar', '.gz', '.tgz', '.rar', '.7z')

    for sdir in search_dirs:
        if os.path.exists(sdir):
            try:
                for f in os.listdir(sdir):
                    if f.lower().endswith(archive_exts):
                        full_p = os.path.join(sdir, f)
                        if os.path.isfile(full_p):
                            mtime = os.path.getmtime(full_p)
                            if mtime > latest_mtime:
                                latest_mtime = mtime
                                latest_file = full_p
            except Exception:
                pass
    return latest_file


def _resolve_folder_path(path_str: str) -> str:
    """
    Intelligently resolves folder shortcuts, Bengali/English spoken names,
    subpath combinations (e.g. 'Desktop/app.zip', 'Downloads/notes', 'ডেস্কটপ/app'), extensionless names,
    generic phrases ('zip file', 'user define zip file'), and performs deep fuzzy resolution across Desktop, Downloads, Documents, drives, and workspace.
    """
    if not path_str or not path_str.strip():
        return ""

    p_clean = path_str.strip().replace('/', '\\')
    p_lower = p_clean.lower()
    home = os.path.expanduser("~")

    onedrive_desktop = os.path.join(home, "OneDrive", "Desktop")
    standard_desktop = os.path.join(home, "Desktop")
    public_desktop = "C:\\Users\\Public\\Desktop"

    onedrive_docs = os.path.join(home, "OneDrive", "Documents")
    standard_docs = os.path.join(home, "Documents")

    downloads_dir = os.path.join(home, "Downloads")

    # Collect all valid search directories across all Desktop locations
    search_directories = []
    for d in (onedrive_desktop, standard_desktop, public_desktop, downloads_dir, onedrive_docs, standard_docs, home, os.getcwd()):
        if os.path.exists(d) and d not in search_directories:
            search_directories.append(d)

    # Generic spoken phrases for archives -> resolve to latest archive file on system
    GENERIC_ZIP_PHRASES = (
        "zip file", "the zip file", "user define zip file", "user defined zip file",
        "zip", "jip file", "জিপ ফাইল", "জিপ", "latest zip file", "new zip file", "archive file",
        "এইটা", "এইটা জিপ", "ফাইলটা", "এই ফাইলটা", "this", "it", "this file", "the file"
    )
    if p_lower in GENERIC_ZIP_PHRASES:
        latest = _find_latest_archive(search_directories)
        if latest:
            return latest

    # Bengali & English location aliases mapping
    LOCATION_ALIASES = {
        "desktop": search_directories[0] if search_directories else standard_desktop,
        "the desktop": search_directories[0] if search_directories else standard_desktop,
        "ডেস্কটপ": search_directories[0] if search_directories else standard_desktop,
        "ডেক স্টপ": search_directories[0] if search_directories else standard_desktop,
        "ডেক্সটপ": search_directories[0] if search_directories else standard_desktop,
        "ডেস্কটপের": search_directories[0] if search_directories else standard_desktop,

        "downloads": downloads_dir,
        "download": downloads_dir,
        "ডাউনলোড": downloads_dir,
        "ডাউনলোডস": downloads_dir,
        "ডাউনলোডের": downloads_dir,

        "documents": onedrive_docs if os.path.exists(onedrive_docs) else standard_docs,
        "document": onedrive_docs if os.path.exists(onedrive_docs) else standard_docs,
        "ডকুমেন্ট": onedrive_docs if os.path.exists(onedrive_docs) else standard_docs,
        "ডকুমেন্টস": onedrive_docs if os.path.exists(onedrive_docs) else standard_docs,

        "pictures": os.path.join(home, "Pictures"),
        "photos": os.path.join(home, "Pictures"),
        "ছবি": os.path.join(home, "Pictures"),

        "music": os.path.join(home, "Music"),
        "songs": os.path.join(home, "Music"),
        "গান": os.path.join(home, "Music"),
    }

    # Match drive letters like "D drive", "D:", "d drive", "ডি ড্রাইভ", "E drive"
    drive_match = re.match(r'^([a-zA-Z])(?:\s+drive|\:?[\/\\]?)$', p_lower)
    if drive_match:
        drive_letter = drive_match.group(1).upper()
        return f"{drive_letter}:\\"

    # Check Bengali/English location aliases directly
    if p_lower in LOCATION_ALIASES:
        return LOCATION_ALIASES[p_lower]

    # Handle subpath like "Desktop\app.zip" or "Downloads\project" or "ডেস্কটপ\app.zip" or "ডেস্কটপের\app"
    if "\\" in p_clean:
        parts = p_clean.split("\\", 1)
        parent_part = parts[0].strip().lower()
        sub_part = parts[1].strip()

        if parent_part in LOCATION_ALIASES:
            resolved_parent = LOCATION_ALIASES[parent_part]
            cand = os.path.join(resolved_parent, sub_part)
            if os.path.exists(cand):
                return cand
            # Search sub_part inside resolved_parent
            found = _find_file_in_dir(resolved_parent, sub_part)
            if found:
                return found
            # Target path does not exist yet (e.g. creating a new folder 'Desktop\java_extracted')
            return cand

    # Direct absolute path check
    if os.path.isabs(p_clean) and os.path.exists(p_clean):
        return p_clean

    # Direct relative check in search directories
    for sdir in search_directories:
        cand = os.path.join(sdir, p_clean)
        if os.path.exists(cand):
            return cand

    # Deep search across all search directories
    for sdir in search_directories:
        found = _find_file_in_dir(sdir, p_clean)
        if found:
            return found

    return os.path.abspath(os.path.expanduser(p_clean))


def _get_selected_items_from_clipboard() -> Tuple[List[str], str]:
    """
    Captures currently selected files/folders (CF_HDROP) or text (CF_UNICODETEXT) from screen.
    """
    files: List[str] = []
    text: str = ""

    # Press Ctrl+C to copy current selection
    with _keyboard.pressed(Key.ctrl):
        _keyboard.press('c')
        _keyboard.release('c')

    time.sleep(0.03)

    if WIN32CLIP_AVAILABLE:
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_HDROP):
                raw_files = win32clipboard.GetClipboardData(win32clipboard.CF_HDROP)
                if raw_files:
                    files = list(raw_files)
            elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                raw_text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                if raw_text:
                    text = raw_text.strip()
            win32clipboard.CloseClipboard()
        except Exception as e:
            logger.debug(f"win32clipboard error: {e}")

    if not files and not text:
        try:
            clip_text = pyperclip.paste()
            if clip_text and clip_text.strip():
                text = clip_text.strip()
        except Exception:
            pass

    return files, text


@function_tool
async def manage_file_or_folder_tool(
    action: str,
    target: str = "selected",
    destination_path: str = "",
    new_name: str = ""
) -> str:
    """
    Performs cut, copy, paste, delete, move, or rename operations on any specified or currently selected file (e.g. .zip, .exe, .pdf, .txt, .mp4, etc.), folder, or text across any directory or drive (C:, D:, E:, Desktop, Downloads).

    Args:
        action: The operation to perform: 'copy', 'cut', 'paste', 'move', 'delete' (or 'remove'), or 'rename'.
        target: 'selected' (to operate on whatever file, folder, or text is highlighted/selected on screen), OR a specific file/folder path (e.g., 'C:\\Users\\...\\file.zip', 'setup.exe', 'D:\\MyFolder').
        destination_path: The target folder or drive path for copy/cut/paste/move (e.g., 'D:', 'E:\\Backup', 'Desktop', 'Downloads', 'C:\\Projects').
        new_name: New name of the file or folder when performing a 'rename' action (e.g., 'final_report.pdf', 'New_Folder_Name').
    """
    try:
        act = action.strip().lower()

        # 1. DELETE / REMOVE ACTION
        if act in ("delete", "remove", "del"):
            if target.lower() == "selected":
                files, text = _get_selected_items_from_clipboard()
                if files:
                    deleted_names = []
                    for f in files:
                        fname = os.path.basename(f)
                        if SEND2TRASH_AVAILABLE:
                            send2trash.send2trash(f)
                        else:
                            if os.path.isdir(f):
                                shutil.rmtree(f)
                            else:
                                os.remove(f)
                        deleted_names.append(fname)
                    return f"🗑️ Successfully deleted {len(deleted_names)} selected items ({', '.join(deleted_names)})."
                else:
                    # Press Delete key on active selection in Explorer
                    _keyboard.press(Key.delete)
                    _keyboard.release(Key.delete)
                    return "🗑️ Executed delete operation (Delete key) on selected screen item."
            else:
                src_path = _resolve_folder_path(target)
                if not os.path.exists(src_path):
                    return f"❌ Target file/folder to delete does not exist: '{src_path}'"
                
                fname = os.path.basename(src_path)
                if SEND2TRASH_AVAILABLE:
                    send2trash.send2trash(src_path)
                else:
                    if os.path.isdir(src_path):
                        shutil.rmtree(src_path)
                    else:
                        os.remove(src_path)
                return f"🗑️ Successfully deleted '{fname}'."

        # 2. RENAME ACTION
        elif act in ("rename", "ren"):
            rename_to = new_name.strip() if new_name else destination_path.strip()
            if not rename_to:
                return "❌ Please specify the new name for the file or folder."

            if target.lower() == "selected":
                files, text = _get_selected_items_from_clipboard()
                if files:
                    src_f = files[0]
                    parent_dir = os.path.dirname(src_f)
                    dest_f = os.path.join(parent_dir, rename_to)
                    os.rename(src_f, dest_f)
                    return f"✏️ Successfully renamed selected item '{os.path.basename(src_f)}' to '{rename_to}'."
                else:
                    # Press F2, type new name, and press Enter
                    _keyboard.press(Key.f2)
                    _keyboard.release(Key.f2)
                    time.sleep(0.02)
                    pyautogui.typewrite(rename_to, interval=0.005)
                    _keyboard.press(Key.enter)
                    _keyboard.release(Key.enter)
                    return f"✏️ Renamed selected item on screen to '{rename_to}'."
            else:
                src_path = _resolve_folder_path(target)
                if not os.path.exists(src_path):
                    return f"❌ File or folder to rename does not exist: '{src_path}'"
                parent_dir = os.path.dirname(src_path)
                dest_path = os.path.join(parent_dir, rename_to)
                os.rename(src_path, dest_path)
                return f"✏️ Successfully renamed '{os.path.basename(src_path)}' to '{rename_to}'."
        
        # 1. PASTE ACTION
        if act == "paste":
            if destination_path:
                dest_dir = _resolve_folder_path(destination_path)
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                
                # Check if clipboard has files
                files, text = _get_selected_items_from_clipboard()
                if files:
                    moved_files = []
                    for f in files:
                        fname = os.path.basename(f)
                        dest_f = os.path.join(dest_dir, fname)
                        if os.path.isdir(f):
                            shutil.copytree(f, dest_f, dirs_exist_ok=True)
                        else:
                            shutil.copy2(f, dest_f)
                        moved_files.append(fname)
                    return f"📋 Successfully pasted {len(moved_files)} items ({', '.join(moved_files)}) into '{dest_dir}'."
                elif text:
                    txt_file = os.path.join(dest_dir, f"Pasted_Text_{int(time.time())}.txt")
                    with open(txt_file, "w", encoding="utf-8") as out:
                        out.write(text)
                    return f"📋 Successfully pasted text into new file '{txt_file}' inside '{dest_dir}'."

            # Default paste into active window via Ctrl+V
            with _keyboard.pressed(Key.ctrl):
                _keyboard.press('v')
                _keyboard.release('v')
            return "📋 Executed paste operation (Ctrl+V) into active target window."

        # 2. CUT ACTION
        elif act in ("cut", "move"):
            if target.lower() == "selected":
                files, text = _get_selected_items_from_clipboard()
                if files and destination_path:
                    dest_dir = _resolve_folder_path(destination_path)
                    os.makedirs(dest_dir, exist_ok=True)
                    moved = []
                    for f in files:
                        fname = os.path.basename(f)
                        dest_f = os.path.join(dest_dir, fname)
                        shutil.move(f, dest_f)
                        moved.append(fname)
                    return f"✂️ Successfully cut and moved {len(moved)} selected items ({', '.join(moved)}) to '{dest_dir}'."
                
                # Default selected cut via Ctrl+X
                with _keyboard.pressed(Key.ctrl):
                    _keyboard.press('x')
                    _keyboard.release('x')
                return "✂️ Cut selected item/text to clipboard (Ctrl+X)."
            else:
                src_path = _resolve_folder_path(target)
                dest_dir = _resolve_folder_path(destination_path) if destination_path else _resolve_folder_path("Desktop")
                if not os.path.exists(src_path):
                    return f"❌ Source file/folder does not exist: '{src_path}'"
                os.makedirs(dest_dir, exist_ok=True)
                dest_f = os.path.join(dest_dir, os.path.basename(src_path))
                shutil.move(src_path, dest_f)
                return f"✂️ Successfully cut and moved '{os.path.basename(src_path)}' to '{dest_dir}'."

        # 3. COPY ACTION
        elif act == "copy":
            if target.lower() == "selected":
                files, text = _get_selected_items_from_clipboard()
                if files and destination_path:
                    dest_dir = _resolve_folder_path(destination_path)
                    os.makedirs(dest_dir, exist_ok=True)
                    copied = []
                    for f in files:
                        fname = os.path.basename(f)
                        dest_f = os.path.join(dest_dir, fname)
                        if os.path.isdir(f):
                            shutil.copytree(f, dest_f, dirs_exist_ok=True)
                        else:
                            shutil.copy2(f, dest_f)
                        copied.append(fname)
                    return f"📂 Successfully copied {len(copied)} selected items ({', '.join(copied)}) to '{dest_dir}'."
                
                return f"📂 Copied selected item/text ({len(files)} files / {len(text)} chars) to clipboard (Ctrl+C)."
            else:
                src_path = _resolve_folder_path(target)
                if not os.path.exists(src_path):
                    return f"❌ Source file/folder does not exist: '{src_path}'"
                if destination_path:
                    dest_dir = _resolve_folder_path(destination_path)
                    os.makedirs(dest_dir, exist_ok=True)
                    dest_f = os.path.join(dest_dir, os.path.basename(src_path))
                    if os.path.isdir(src_path):
                        shutil.copytree(src_path, dest_f, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src_path, dest_f)
                    return f"📂 Successfully copied '{os.path.basename(src_path)}' to '{dest_dir}'."
                else:
                    pyperclip.copy(src_path)
                    return f"📂 Copied file path '{src_path}' to clipboard."

        return f"Invalid action '{action}'. Supported actions: 'copy', 'cut', 'paste', 'move'."

    except Exception as e:
        logger.error(f"[Manage File/Folder Tool Error]: {e}")
        return f"❌ Error performing {action}: {e}"


@function_tool
async def send_file_or_text_tool(
    destination_type: str,
    recipient: str,
    target: str = "selected",
    file_or_text_content: str = ""
) -> str:
    """
    Sends any selected text, selected file, or specified file/text via WhatsApp or Email.

    Args:
        destination_type: 'whatsapp' or 'email'.
        recipient: Contact name or phone number for WhatsApp, or Email address (e.g. 'john@example.com') for Email.
        target: 'selected' (to send whatever file, folder, or text is highlighted/selected on screen), OR 'specified'.
        file_or_text_content: Optional path to file or text message if target is 'specified'.
    """
    try:
        dest = destination_type.strip().lower()
        recip = recipient.strip()

        content_text = ""
        content_files = []

        if target.lower() == "selected":
            content_files, content_text = _get_selected_items_from_clipboard()
        elif file_or_text_content:
            resolved = _resolve_folder_path(file_or_text_content)
            if os.path.exists(resolved):
                content_files = [resolved]
            else:
                content_text = file_or_text_content

        # 1. SEND VIA WHATSAPP
        if "whatsapp" in dest:
            if content_files:
                file_names = [os.path.basename(f) for f in content_files]
                msg_body = f"Sending selected file: {', '.join(file_names)}\nPath: {content_files[0]}"
                res = await send_whatsapp_message(recip, msg_body)
                return f"📱 Sent WhatsApp notification to '{recip}' with file details ({', '.join(file_names)}).\nResult: {res}"
            elif content_text:
                res = await send_whatsapp_message(recip, content_text)
                return f"📱 Successfully sent WhatsApp message to '{recip}': '{content_text[:50]}...'\nResult: {res}"
            else:
                return "❌ No selected text or file found to send via WhatsApp."

        # 2. SEND VIA EMAIL
        elif "email" in dest or "mail" in dest:
            subject = "Shared item from Assistant"
            body = content_text if content_text else f"Attached file: {content_files}"
            
            enc_subj = urllib.parse.quote(subject)
            enc_body = urllib.parse.quote(body)
            mailto_url = f"mailto:{recip}?subject={enc_subj}&body={enc_body}"
            
            webbrowser.open(mailto_url)
            return f"📧 Opened Windows Default Mail client with pre-filled email draft to '{recip}'."

        return f"Invalid destination '{destination_type}'. Supported destinations: 'whatsapp', 'email'."

    except Exception as e:
        logger.error(f"[Send File/Text Tool Error]: {e}")
        return f"❌ Error sending item: {e}"


@function_tool
async def create_file_or_folder_tool(
    item_type: str,
    name: str,
    parent_directory: str = "Desktop",
    content: str = ""
) -> str:
    r"""
    Creates a new file or new folder at the specified directory (Desktop, Downloads, Documents, D:\, E:\, etc.).

    Args:
        item_type: 'folder' (or 'directory') to create a new folder, OR 'file' to create a new file.
        name: Name of the folder or file to create (e.g. 'Projects', 'notes.txt', 'script.py').
        parent_directory: Target directory (defaults to 'Desktop', can be 'Downloads', 'Documents', 'D:\', etc.).
        content: Text content to write if item_type is 'file'.
    """
    try:
        itype = item_type.strip().lower()
        target_dir = _resolve_folder_path(parent_directory)
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, name)

        if itype in ("folder", "dir", "directory"):
            os.makedirs(target_path, exist_ok=True)
            return f"📁 Successfully created folder '{name}' at '{target_dir}'."
        else:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"📄 Successfully created file '{name}' at '{target_dir}'."
    except Exception as e:
        logger.error(f"[Create File/Folder Error]: {e}")
        return f"❌ Failed to create {item_type} '{name}': {e}"


@function_tool
async def search_files_tool(
    query: str,
    search_directory: str = "all"
) -> str:
    """
    Searches for files or folders matching a query across Desktop, Downloads, Documents, or full drives (C:, D:, E:).

    Args:
        query: Search term or file/folder name pattern (e.g. 'resume', '.pdf', 'report').
        search_directory: Target folder to search in ('Desktop', 'Downloads', 'Documents', 'D:\', 'C:\', or 'all').
    """
    try:
        q_lower = query.lower().strip()
        found_items = []
        home = os.path.expanduser("~")

        if search_directory.lower() == "all":
            search_paths = [
                os.path.join(home, "OneDrive", "Desktop"),
                os.path.join(home, "Desktop"),
                os.path.join(home, "Downloads"),
                os.path.join(home, "OneDrive", "Documents"),
                os.path.join(home, "Documents"),
                "D:\\", "E:\\"
            ]
        else:
            search_paths = [_resolve_folder_path(search_directory)]

        valid_paths = [p for p in search_paths if os.path.exists(p)]

        def _do_search():
            matches = []
            for spath in valid_paths:
                for root, dirs, files in os.walk(spath):
                    # Exclude system / hidden folders
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ("$recycle.bin", "system volume information", "node_modules", "__pycache__", "venv")]
                    for item in dirs + files:
                        if q_lower in item.lower():
                            full_p = os.path.join(root, item)
                            try:
                                size_mb = os.path.getsize(full_p) / (1024 * 1024) if os.path.isfile(full_p) else 0
                                matches.append(f"{'📁' if os.path.isdir(full_p) else '📄'} {item} ({size_mb:.2f} MB) -> {full_p}")
                            except Exception:
                                matches.append(f"📄 {item} -> {full_p}")
                            if len(matches) >= 15:
                                return matches
            return matches

        matches = await asyncio.to_thread(_do_search)

        if matches:
            return f"🔍 Found {len(matches)} matching items for '{query}':\n" + "\n".join(matches)
        return f"🔍 No files or folders matching '{query}' were found."
    except Exception as e:
        logger.error(f"[Search Files Error]: {e}")
        return f"❌ Failed to search files for '{query}': {e}"


@function_tool
async def zip_unzip_tool(
    action: str,
    target_path: str,
    output_name_or_path: str = ""
) -> str:
    """
    Compresses files/folders into a .zip archive, or extracts any archive file (.zip, .tar, .gz, .tgz, .bz2, etc.) into a folder.

    Args:
        action: 'compress' (or 'zip') to archive, OR 'extract' (or 'unzip') to extract.
        target_path: Path or name of the file/folder to compress OR path to the archive file to extract.
        output_name_or_path: Name/path for destination zip file (when compressing) or extraction folder (when extracting).
    """
    try:
        act = action.strip().lower()
        resolved_target = _resolve_folder_path(target_path)

        if not os.path.exists(resolved_target):
            return f"❌ Target file or folder does not exist: '{resolved_target}'"

        if act in ("compress", "zip", "archive"):
            if output_name_or_path:
                clean_out = output_name_or_path.strip().replace('/', '\\')
                if '\\' in clean_out:
                    dir_part, file_part = clean_out.rsplit('\\', 1)
                    resolved_dir = _resolve_folder_path(dir_part)
                    zip_fname = file_part if file_part.lower().endswith(".zip") else f"{file_part}.zip"
                    zip_out = os.path.join(resolved_dir, zip_fname)
                else:
                    zip_fname = clean_out if clean_out.lower().endswith(".zip") else f"{clean_out}.zip"
                    if os.path.isabs(zip_fname):
                        zip_out = zip_fname
                    else:
                        zip_out = os.path.join(os.path.dirname(resolved_target), zip_fname)
            else:
                zip_out = f"{resolved_target}.zip"

            os.makedirs(os.path.dirname(zip_out), exist_ok=True)

            def _zip():
                with zipfile.ZipFile(zip_out, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    if os.path.isdir(resolved_target):
                        for root, _, files in os.walk(resolved_target):
                            for file in files:
                                fn = os.path.join(root, file)
                                arcname = os.path.relpath(fn, os.path.dirname(resolved_target))
                                zipf.write(fn, arcname)
                    else:
                        zipf.write(resolved_target, os.path.basename(resolved_target))

            await asyncio.to_thread(_zip)
            return f"📦 Successfully compressed '{os.path.basename(resolved_target)}' into '{zip_out}'."

        elif act in ("extract", "unzip", "decompress"):
            zip_stem = os.path.splitext(os.path.basename(resolved_target))[0]
            if zip_stem.lower().endswith(".tar"):
                zip_stem = os.path.splitext(zip_stem)[0]

            if output_name_or_path and output_name_or_path.strip().lower() not in ("desktop", "downloads", "documents", "the desktop"):
                dest_dir = _resolve_folder_path(output_name_or_path)
                if os.path.isfile(dest_dir) or dest_dir.lower() == resolved_target.lower():
                    dest_dir = os.path.join(os.path.dirname(resolved_target), zip_stem)
                elif os.path.isdir(dest_dir) and dest_dir.lower().endswith(("desktop", "downloads", "documents")):
                    dest_dir = os.path.join(dest_dir, zip_stem)
            else:
                parent_location = os.path.dirname(resolved_target)
                dest_dir = os.path.join(parent_location, zip_stem)

            os.makedirs(dest_dir, exist_ok=True)

            def _unzip():
                try:
                    shutil.unpack_archive(resolved_target, dest_dir)
                except Exception:
                    with zipfile.ZipFile(resolved_target, 'r') as zipf:
                        zipf.extractall(dest_dir)

            await asyncio.to_thread(_unzip)
            return f"📂 Successfully extracted '{os.path.basename(resolved_target)}' into '{dest_dir}'."

        return "❌ Invalid action. Use 'compress' (zip) or 'extract' (unzip)."
    except Exception as e:
        logger.error(f"[ZIP/Unzip Error]: {e}")
        return f"❌ Failed to {action} archive: {e}"


@function_tool
async def organize_downloads_folder_tool() -> str:
    """
    Automatically organizes loose files in the Downloads folder by categorizing them into subfolders (Images, Documents, Audio, Video, Archives, Programs, Code).
    """
    try:
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.exists(downloads_dir):
            return f"❌ Downloads directory not found at '{downloads_dir}'."

        categories = {
            "Images": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"],
            "Documents": [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".csv"],
            "Audio": [".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"],
            "Video": [".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv"],
            "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".iso"],
            "Programs": [".exe", ".msi", ".bat", ".cmd"],
            "Code": [".py", ".js", ".ts", ".html", ".css", ".json", ".cpp", ".java", ".c"]
        }

        def _organize():
            moved_counts = {}
            for item in os.listdir(downloads_dir):
                item_path = os.path.join(downloads_dir, item)
                if os.path.isfile(item_path):
                    ext = os.path.splitext(item)[1].lower()
                    target_cat = "Others"
                    for cat, ext_list in categories.items():
                        if ext in ext_list:
                            target_cat = cat
                            break

                    cat_dir = os.path.join(downloads_dir, target_cat)
                    os.makedirs(cat_dir, exist_ok=True)
                    dest_file = os.path.join(cat_dir, item)

                    # Handle duplicate filenames
                    if os.path.exists(dest_file):
                        base, extension = os.path.splitext(item)
                        dest_file = os.path.join(cat_dir, f"{base}_{int(time.time())}{extension}")

                    shutil.move(item_path, dest_file)
                    moved_counts[target_cat] = moved_counts.get(target_cat, 0) + 1
            return moved_counts

        counts = await asyncio.to_thread(_organize)
        if counts:
            summary = ", ".join([f"{cat}: {cnt}" for cat, cnt in counts.items()])
            return f"🧹 Successfully organized Downloads folder! Moved files into categories ({summary})."
        return "🧹 Downloads folder is already organized! No loose files found."
    except Exception as e:
        logger.error(f"[Organize Downloads Error]: {e}")
        return f"❌ Failed to organize Downloads folder: {e}"


@function_tool
async def empty_recycle_bin_tool() -> str:
    """
    Empties the Windows Recycle Bin to free up disk space.
    """
    try:
        def _empty():
            if WIN32CLIP_AVAILABLE:
                try:
                    # SHERB_NOCONFIRMATION (1) | SHERB_NOPROGRESSUI (2) | SHERB_NOSOUND (4)
                    res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
                    if res == 0:
                        return True
                except Exception:
                    pass
            # Fallback PowerShell command
            ps_cmd = "Clear-RecycleBin -Force -Confirm:$false"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
            return res.returncode == 0

        success = await asyncio.to_thread(_empty)
        return "🗑️ Successfully emptied the Windows Recycle Bin!"
    except Exception as e:
        logger.error(f"[Empty Recycle Bin Error]: {e}")
        return f"❌ Failed to empty Recycle Bin: {e}"


@function_tool
async def read_file_or_folder_info_tool(
    target_path: str,
    max_lines: int = 50
) -> str:
    """
    Reads the text contents of any user-defined text file (.txt, .md, .py, .json, .csv, .log, .xml, .html, etc.) OR lists all files and subfolders inside a directory.

    Args:
        target_path: Spoken name or path of the text file to read OR folder to inspect (e.g. 'notes.txt', 'Desktop/Java', 'Downloads', 'my_code.py').
        max_lines: Maximum lines of text to read from a file (default 50 lines).
    """
    try:
        if not target_path or not target_path.strip():
            return "❌ Please specify a file or folder name to read."

        resolved_target = _resolve_folder_path(target_path)
        if not os.path.exists(resolved_target):
            return f"❌ Specified file or folder '{target_path}' could not be located on your system."

        # If target is a directory/folder: List all items inside it
        if os.path.isdir(resolved_target):
            def _list_dir():
                items = os.listdir(resolved_target)
                if not items:
                    return f"📁 Folder '{os.path.basename(resolved_target)}' ({resolved_target}) is empty."

                dirs_list = []
                files_list = []
                for item in items[:40]:  # Cap at top 40 items
                    item_path = os.path.join(resolved_target, item)
                    if os.path.isdir(item_path):
                        dirs_list.append(f"📁 {item}/")
                    else:
                        size_kb = round(os.path.getsize(item_path) / 1024, 1)
                        files_list.append(f"📄 {item} ({size_kb} KB)")

                summary_parts = []
                if dirs_list:
                    summary_parts.append("Subfolders:\n  " + "\n  ".join(dirs_list))
                if files_list:
                    summary_parts.append("Files:\n  " + "\n  ".join(files_list))

                total_str = f"📁 Contents of folder '{os.path.basename(resolved_target)}' ({len(items)} items total):\n\n"
                return total_str + "\n\n".join(summary_parts)

            return await asyncio.to_thread(_list_dir)

        # If target is a file: Read text content
        if os.path.isfile(resolved_target):
            ext = os.path.splitext(resolved_target)[1].lower()
            binary_exts = ('.pdf', '.docx', '.png', '.jpg', '.jpeg', '.gif', '.zip', '.rar', '.7z', '.exe', '.dll', '.iso', '.mp4', '.mp3', '.wav', '.avi')

            if ext in binary_exts:
                size_kb = round(os.path.getsize(resolved_target) / 1024, 1)
                mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(resolved_target)))
                return f"📄 File '{os.path.basename(resolved_target)}' is a binary/media file ({ext.upper()} format, Size: {size_kb} KB, Last Modified: {mtime}). Direct text reading is not applicable."

            def _read_file():
                encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
                content = None
                for enc in encodings:
                    try:
                        with open(resolved_target, 'r', encoding=enc, errors='replace') as f:
                            lines = [f.readline() for _ in range(max_lines)]
                            content = "".join(lines).strip()
                            if content:
                                break
                    except Exception:
                        pass

                if not content:
                    return f"📄 File '{os.path.basename(resolved_target)}' is empty."

                return f"📄 Contents of '{os.path.basename(resolved_target)}':\n\n{content}"

            return await asyncio.to_thread(_read_file)

        return f"❌ Unable to read '{target_path}'."
    except Exception as e:
        logger.error(f"[Read File/Folder Error]: {e}")
        return f"❌ Failed to read '{target_path}': {e}"

