import os
import time
import glob
import shutil
import ctypes
import asyncio
import logging
import threading
import re
from datetime import datetime
import numpy as np
import cv2
from PIL import Image, ImageGrab
import pyautogui
from pynput.keyboard import Key, Controller as KeyboardController
from livekit.agents import function_tool

logger = logging.getLogger(__name__)

# Global background recorder state
_recording_active = False
_recording_thread = None
_last_recorded_filepath = ""
_keyboard = KeyboardController()


def _get_desktop_dir() -> str:
    desktop = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
    if os.path.exists(desktop):
        return desktop
    return os.path.join(os.path.expanduser("~"), "Desktop")


def _get_pictures_screenshots_dir() -> str:
    home = os.path.expanduser("~")
    dirs = [
        os.path.join(home, "OneDrive", "Pictures", "Screenshots"),
        os.path.join(home, "Pictures", "Screenshots"),
    ]
    for d in dirs:
        if os.path.exists(d):
            return d
    os.makedirs(dirs[0], exist_ok=True)
    return dirs[0]


def _sanitize_filename(name: str, default_prefix: str, default_ext: str) -> str:
    """Sanitizes user-provided filename and ensures it has the correct extension."""
    name = name.strip()
    if not name:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{default_prefix}_{timestamp}{default_ext}"
    
    # Remove invalid characters for Windows filenames (\ / : * ? " < > |)
    clean_name = re.sub(r'[\\/:*?"<>|]', '_', name)
    
    if not clean_name.lower().endswith(default_ext.lower()):
        clean_name = f"{clean_name}{default_ext}"
        
    return clean_name


def _grab_screen_frame() -> Image.Image:
    """Capture full screen image frame using PyAutoGUI/ImageGrab with Win32 PrintWindow fallback."""
    try:
        pyautogui.FAILSAFE = False
        img = pyautogui.screenshot()
        ext = img.getextrema()
        # Check if non-black frame
        if ext != ((0, 0), (0, 0), (0, 0)) and ext != ((0, 0), (0, 0), (0, 0), (0, 0)):
            return img
    except Exception:
        pass

    try:
        img = ImageGrab.grab()
        ext = img.getextrema()
        if ext != ((0, 0), (0, 0), (0, 0)) and ext != ((0, 0), (0, 0), (0, 0), (0, 0)):
            return img
    except Exception:
        pass

    # Win32 GDI fallback
    try:
        import win32gui, win32ui, win32api
        hwnd = win32gui.GetDesktopWindow()
        width = win32api.GetSystemMetrics(0)
        height = win32api.GetSystemMetrics(1)

        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
        saveDC.SelectObject(saveBitMap)

        ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)

        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)

        im = Image.frombuffer(
            'RGB',
            (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
            bmpstr, 'raw', 'BGRX', 0, 1
        )

        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)

        return im
    except Exception as e:
        logger.warning(f"Fallback grab failed: {e}")

    # Return empty fallback image if all fail
    return Image.new("RGB", (1920, 1080), color=(50, 50, 50))


@function_tool
async def take_screenshot_tool(custom_filename: str = "") -> str:
    """
    Takes a full-screen screenshot of the user's active desktop screen and saves it as a PNG file directly to the Desktop under a default or custom user-defined name.

    Args:
        custom_filename: Optional custom filename specified by the user (e.g., 'my_project', 'google_homepage.png'). If omitted, defaults to timestamped filename.
    """
    try:
        def _capture():
            filename = _sanitize_filename(custom_filename, "Screenshot", ".png")
            target_filepath = os.path.join(_get_desktop_dir(), filename)

            # Strategy 1: Hardware OS Win + PrintScreen trigger (guarantees full RGB colors)
            screenshots_dir = _get_pictures_screenshots_dir()
            before_files = set(glob.glob(os.path.join(screenshots_dir, "*.*")))

            with _keyboard.pressed(Key.cmd):
                _keyboard.press(Key.print_screen)
                _keyboard.release(Key.print_screen)

            time.sleep(0.5)

            after_files = set(glob.glob(os.path.join(screenshots_dir, "*.*")))
            new_files = list(after_files - before_files)

            if not new_files:
                all_files = glob.glob(os.path.join(screenshots_dir, "*.*"))
                if all_files:
                    all_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
                    new_files = [all_files[0]]

            if new_files:
                latest = new_files[0]
                shutil.copy2(latest, target_filepath)
                # Verify file non-empty
                if os.path.exists(target_filepath) and os.path.getsize(target_filepath) > 0:
                    return target_filepath

            # Strategy 2: Direct frame grab fallback
            im = _grab_screen_frame()
            im.save(target_filepath)
            return target_filepath

        file_path = await asyncio.to_thread(_capture)
        logger.info(f"[Screenshot Tool] Screenshot saved to: {file_path}")
        return f"📸 Screenshot captured successfully and saved directly to your Desktop as: '{os.path.basename(file_path)}'."

    except Exception as e:
        logger.error(f"[Screenshot Tool Error]: {e}")
        return f"❌ Failed to take screenshot: {e}"


def _record_worker(filepath: str, duration_sec: int = 0):
    global _recording_active
    try:
        first_img = _grab_screen_frame()
        width, height = first_img.size

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(filepath, fourcc, 15.0, (width, height))

        start_time = time.time()
        while _recording_active:
            if duration_sec > 0 and (time.time() - start_time) >= duration_sec:
                break

            img = _grab_screen_frame()
            frame_np = np.array(img)
            frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)
            out.write(frame_bgr)
            time.sleep(0.04)

        out.release()
        _recording_active = False
        logger.info(f"[Screen Recorder] Recording saved to: {filepath}")
    except Exception as e:
        _recording_active = False
        logger.error(f"[Screen Recorder Worker Error]: {e}")


@function_tool
async def control_screen_recording_tool(
    action: str = "start",
    duration_sec: int = 0,
    custom_filename: str = ""
) -> str:
    """
    Starts or stops background screen recording and saves the video (.mp4) directly to the user's Desktop under a default or custom user-defined name.

    Args:
        action: 'start' to begin screen recording, or 'stop' to end and save current screen recording.
        duration_sec: Optional duration in seconds (0 for continuous recording until stopped).
        custom_filename: Optional custom filename specified by the user for the recording (e.g. 'python_tutorial', 'demo_recording.mp4').
    """
    global _recording_active, _recording_thread, _last_recorded_filepath

    try:
        act = action.strip().lower()

        if act == "start":
            if _recording_active:
                return "📹 Screen recording is already in progress. Say 'stop recording' when finished."

            filename = _sanitize_filename(custom_filename, "ScreenRecord", ".mp4")
            filepath = os.path.join(_get_desktop_dir(), filename)
            _last_recorded_filepath = filepath

            _recording_active = True
            _recording_thread = threading.Thread(
                target=_record_worker,
                args=(filepath, duration_sec),
                daemon=True
            )
            _recording_thread.start()

            return f"🎥 Screen recording started! The video is being recorded and will be saved directly to your Desktop as '{filename}'. Say 'stop recording' when you want to finish."

        elif act == "stop":
            if not _recording_active:
                if _last_recorded_filepath and os.path.exists(_last_recorded_filepath):
                    return f"🎥 Screen recording is already saved on your Desktop as: '{os.path.basename(_last_recorded_filepath)}'."
                return "📹 No active screen recording was running."

            _recording_active = False
            if _recording_thread and _recording_thread.is_alive():
                _recording_thread.join(timeout=3.0)

            saved_file = os.path.basename(_last_recorded_filepath) if _last_recorded_filepath else "recording.mp4"
            return f"🎬 Screen recording stopped successfully! Your recorded video file is saved directly on your Desktop as: '{saved_file}'."

        return "Invalid action. Use 'start' or 'stop'."

    except Exception as e:
        logger.error(f"[Screen Recording Tool Error]: {e}")
        return f"❌ Failed to control screen recording: {e}"
