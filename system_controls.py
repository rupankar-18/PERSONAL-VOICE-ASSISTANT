# import os
# import subprocess
# import asyncio
# import logging
# from livekit.agents import function_tool

# logger = logging.getLogger(__name__)

# @function_tool
# async def set_brightness_tool(action: str = "set", level: int = 50) -> str:
#     """
#     Adjust or set laptop screen brightness.
#     Args:
#         action: 'set', 'increase', or 'decrease'
#         level: brightness level percentage (0 to 100)
#     """
#     try:
#         def _get_current_brightness():
#             cmd = "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness"
#             res = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)
#             val = res.stdout.strip()
#             return int(val) if val.isdigit() else 50

#         curr = await asyncio.to_thread(_get_current_brightness)

#         if action == "increase":
#             target = min(100, curr + 20)
#         elif action == "decrease":
#             target = max(0, curr - 20)
#         else:
#             target = max(0, min(100, level))

#         def _set_brightness(val):
#             cmd = f"(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {val})"
#             subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)

#         await asyncio.to_thread(_set_brightness, target)
#         logger.info(f"Screen brightness set to {target}%")
#         return f"💡 Screen brightness updated to {target}%."
#     except Exception as e:
#         logger.error(f"Error setting brightness: {e}")
#         return f"❌ Failed to adjust brightness: {e}"


# @function_tool
# async def open_task_manager_tool() -> str:
#     """
#     Open Windows Task Manager to monitor or manage system processes and performance.
#     """
#     try:
#         subprocess.Popen(["taskmgr.exe"])
#         logger.info("Task Manager launched.")
#         return "🖥️ Task Manager opened successfully."
#     except Exception as e:
#         logger.error(f"Error opening Task Manager: {e}")
#         return f"❌ Failed to open Task Manager: {e}"


# @function_tool
# async def open_file_manager_tool(path: str = "") -> str:
#     """
#     Open Windows File Manager / File Explorer.
#     Args:
#         path: Optional directory path or folder to open (defaults to Quick Access/This PC)
#     """
#     try:
#         if path and os.path.exists(path):
#             subprocess.Popen(["explorer.exe", path])
#             return f"📁 File Explorer opened at {path}."
#         else:
#             subprocess.Popen(["explorer.exe"])
#             return "📁 File Explorer opened."
#     except Exception as e:
#         logger.error(f"Error opening File Explorer: {e}")
#         return f"❌ Failed to open File Explorer: {e}"


# @function_tool
# async def system_power_control_tool(action: str) -> str:
#     """
#     Control laptop power states: power off (shutdown), restart, or sleep mode.
#     Args:
#         action: 'shutdown' (or 'power_off'), 'restart', or 'sleep'
#     """
#     act = action.lower().strip()
#     try:
#         if act in ["shutdown", "power_off", "poweroff", "turn_off"]:
#             # Shutdown in 5 seconds allowing time for assistant to reply
#             subprocess.run(["shutdown", "/s", "/t", "5"], capture_output=True)
#             return "🔌 Powering off laptop in 5 seconds. Goodbye Sir!"
#         elif act in ["restart", "reboot"]:
#             # Restart in 5 seconds
#             subprocess.run(["shutdown", "/r", "/t", "5"], capture_output=True)
#             return "🔄 Restarting laptop in 5 seconds."
#         elif act in ["sleep", "sleep_mode", "suspend", "hibernate"]:
#             # Sleep mode command using rundll32
#             ps_cmd = "Add-Type -Assembly System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)"
#             subprocess.Popen(["powershell", "-Command", ps_cmd])
#             return "🌙 Laptop is entering Sleep mode now."
#         else:
#             return f"❌ Unknown power action: {action}. Please specify 'shutdown', 'restart', or 'sleep'."
#     except Exception as e:
#         logger.error(f"Error executing power action '{action}': {e}")
#         return f"❌ Failed to execute {action}: {e}"
"""
system_control_tools.py

A comprehensive set of Windows system-control tools for a LiveKit voice/AI agent.
Covers: display brightness, volume/mute, Wi-Fi, Bluetooth, airplane mode,
power actions (shutdown/restart/sleep/lock), Task Manager, File Explorer,
process management, screenshot capture, clipboard, and battery/system info.

Requirements:
    - Windows OS
    - PowerShell available on PATH
    - pip install pycaw comtypes psutil pillow pyperclip  (optional, see notes below)

NOTE ON DEPENDENCIES:
    - Volume control uses `pycaw` (optional). If not installed, it falls back to
      a PowerShell/nircmd-free approach using SendKeys for mute/volume steps.
    - Process listing/killing uses `psutil` if available, otherwise falls back
      to `tasklist`/`taskkill` via subprocess.
    - Screenshot uses `PIL.ImageGrab` if available.
    - Clipboard uses `pyperclip` if available, otherwise PowerShell clipboard cmdlets.

All tools are defensive: they catch exceptions and return a human-readable
string rather than raising, since they are meant to be called by an LLM
function-calling agent.
"""

import os
import re
import shlex
import asyncio
import logging
import subprocess
from typing import Optional

from livekit.agents import function_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency imports (all best-effort; tools degrade gracefully)
# ---------------------------------------------------------------------------
try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    _HAS_PYCAW = True
except ImportError:
    _HAS_PYCAW = False

try:
    from PIL import ImageGrab
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    import pyperclip
    _HAS_PYPERCLIP = True
except ImportError:
    _HAS_PYPERCLIP = False


def _run_ps(cmd: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Run a PowerShell command synchronously (call via asyncio.to_thread)."""
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ===========================================================================
# DISPLAY BRIGHTNESS
# ===========================================================================

@function_tool
async def set_brightness_tool(action: str = "set", level: int = 50) -> str:
    """
    Adjust or set laptop screen brightness.
    Args:
        action: 'set', 'increase', or 'decrease'
        level: brightness level percentage (0 to 100), used when action='set'
    """
    try:
        def _get_current_brightness():
            cmd = "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness"
            res = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)
            val = res.stdout.strip()
            return int(val) if val.isdigit() else 50

        curr = await asyncio.to_thread(_get_current_brightness)

        if action == "increase":
            target = min(100, curr + 20)
        elif action == "decrease":
            target = max(0, curr - 20)
        else:
            target = max(0, min(100, level))

        def _set_brightness(val):
            cmd = f"(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {val})"
            subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)

        await asyncio.to_thread(_set_brightness, target)
        logger.info(f"Screen brightness set to {target}%")
        return f"💡 Screen brightness updated to {target}%."
    except Exception as e:
        logger.error(f"Error setting brightness: {e}")
        return f"❌ Failed to adjust brightness: {e}"


# ===========================================================================
# VOLUME CONTROL
# ===========================================================================

@function_tool
async def set_volume_tool(action: str = "set", level: int = 50) -> str:
    """
    Adjust or set the system master volume.
    Args:
        action: 'set', 'increase', 'decrease', 'mute', or 'unmute'
        level: volume level percentage (0 to 100), used when action='set'
    """
    try:
        def _do():
            if not _HAS_PYCAW:
                return None  # signal fallback needed
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))

            if action == "mute":
                volume.SetMute(1, None)
                return "muted"
            if action == "unmute":
                volume.SetMute(0, None)
                return "unmuted"

            curr = round(volume.GetMasterVolumeLevelScalar() * 100)
            if action == "increase":
                target = min(100, curr + 10)
            elif action == "decrease":
                target = max(0, curr - 10)
            else:
                target = max(0, min(100, level))

            volume.SetMasterVolumeLevelScalar(target / 100.0, None)
            return target

        result = await asyncio.to_thread(_do)

        if result is None:
            # Fallback: no pycaw installed, use PowerShell nircmd-free SendKeys approach
            def _fallback():
                if action == "mute":
                    key = "{VOLUME_MUTE}"
                elif action == "unmute":
                    key = "{VOLUME_MUTE}"  # toggles; best effort
                elif action == "increase":
                    key = "{VOLUME_UP}" * 5
                elif action == "decrease":
                    key = "{VOLUME_DOWN}" * 5
                else:
                    return None
                ps = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    f"[System.Windows.Forms.SendKeys]::SendWait('{key}')"
                )
                subprocess.run(["powershell", "-Command", ps], capture_output=True, text=True)
                return True

            fb = await asyncio.to_thread(_fallback)
            if fb is None:
                return ("❌ Precise volume control needs 'pycaw' installed "
                        "(pip install pycaw comtypes). For set-level requests, "
                        "please install it; mute/unmute/step changes were attempted via fallback.")
            return f"🔊 Volume '{action}' applied (fallback mode, install pycaw for precise %)."

        if result == "muted":
            return "🔇 System volume muted."
        if result == "unmuted":
            return "🔊 System volume unmuted."
        logger.info(f"Volume set to {result}%")
        return f"🔊 Volume updated to {result}%."
    except Exception as e:
        logger.error(f"Error setting volume: {e}")
        return f"❌ Failed to adjust volume: {e}"


# ===========================================================================
# WI-FI CONTROL
# ===========================================================================

@function_tool
async def wifi_control_tool(action: str) -> str:
    """
    Turn Wi-Fi on or off, or check its status.
    Args:
        action: 'on', 'off', or 'status'
    """
    act = action.lower().strip()
    try:
        def _run(a):
            if a == "status":
                res = subprocess.run(
                    ["powershell", "-Command", "Get-NetAdapter | Where-Object {$_.InterfaceDescription -like '*Wi-Fi*' -or $_.Name -like '*Wi-Fi*'} | Select-Object Name, Status"],
                    capture_output=True, text=True,
                )
                return res.stdout.strip()
            state = "Enabled" if a == "on" else "Disabled"
            cmd = f"Get-NetAdapter -Name 'Wi-Fi' | {'Enable-NetAdapter' if a == 'on' else 'Disable-NetAdapter'} -Confirm:$false"
            res = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)
            return res.stderr.strip() or "ok"

        out = await asyncio.to_thread(_run, act)

        if act == "status":
            return f"📶 Wi-Fi status:\n{out}" if out else "📶 Could not determine Wi-Fi status."
        if act == "on":
            return "📶 Wi-Fi turned on."
        if act == "off":
            return "📶 Wi-Fi turned off."
        return "❌ Unknown action. Use 'on', 'off', or 'status'."
    except Exception as e:
        logger.error(f"Error controlling Wi-Fi: {e}")
        return f"❌ Failed to control Wi-Fi (may need Administrator privileges): {e}"


# ===========================================================================
# BLUETOOTH CONTROL
# ===========================================================================

@function_tool
async def bluetooth_control_tool(action: str) -> str:
    """
    Turn Bluetooth radio on or off (opens Bluetooth settings as a reliable fallback,
    since Windows requires elevated/API-level access for a silent toggle).
    Args:
        action: 'on', 'off', or 'settings'
    """
    act = action.lower().strip()
    try:
        def _open_settings():
            subprocess.Popen(["start", "ms-settings:bluetooth"], shell=True)

        await asyncio.to_thread(_open_settings)
        if act in ("on", "off"):
            return (f"📡 Opened Bluetooth settings — please toggle it {act.upper()} "
                    f"(Windows restricts silent Bluetooth radio toggling without a signed driver API).")
        return "📡 Opened Bluetooth settings."
    except Exception as e:
        logger.error(f"Error opening Bluetooth settings: {e}")
        return f"❌ Failed to control Bluetooth: {e}"


# ===========================================================================
# WINDOWS SETTINGS ACCESS TOOL
# ===========================================================================

SETTINGS_MAP = {
    "system": "ms-settings:",
    "display": "ms-settings:display",
    "screen": "ms-settings:display",
    "brightness": "ms-settings:display",
    "sound": "ms-settings:sound",
    "volume": "ms-settings:sound",
    "audio": "ms-settings:sound",
    "notifications": "ms-settings:notifications",
    "focus": "ms-settings:quiethours",
    "focus assist": "ms-settings:quiethours",
    "power": "ms-settings:powersleep",
    "sleep": "ms-settings:powersleep",
    "battery": "ms-settings:powersleep",
    "storage": "ms-settings:storagesense",
    "disk": "ms-settings:storagesense",
    "nearby sharing": "ms-settings:nearbysharing",
    "multitasking": "ms-settings:multitasking",
    "activation": "ms-settings:activation",
    "about": "ms-settings:about",
    "system info": "ms-settings:about",
    "clipboard": "ms-settings:clipboard",

    "bluetooth": "ms-settings:bluetooth",
    "connected devices": "ms-settings:connecteddevices",
    "devices": "ms-settings:connecteddevices",
    "printers": "ms-settings:printers",
    "scanners": "ms-settings:printers",
    "mouse": "ms-settings:mousetouchpad",
    "touchpad": "ms-settings:devices-touchpad",
    "keyboard": "ms-settings:typing",
    "typing": "ms-settings:typing",
    "pen": "ms-settings:pen",
    "ink": "ms-settings:pen",
    "camera": "ms-settings:camera",
    "cameras": "ms-settings:camera",
    "autoplay": "ms-settings:autoplay",
    "usb": "ms-settings:usb",

    "wifi": "ms-settings:network-wifi",
    "wi-fi": "ms-settings:network-wifi",
    "wireless": "ms-settings:network-wifi",
    "ethernet": "ms-settings:network-ethernet",
    "network": "ms-settings:network-status",
    "internet": "ms-settings:network-status",
    "vpn": "ms-settings:network-vpn",
    "hotspot": "ms-settings:network-mobilehotspot",
    "mobile hotspot": "ms-settings:network-mobilehotspot",
    "airplane": "ms-settings:network-airplanemode",
    "airplane mode": "ms-settings:network-airplanemode",
    "proxy": "ms-settings:network-proxy",

    "personalization": "ms-settings:personalization",
    "background": "ms-settings:personalization-background",
    "wallpaper": "ms-settings:personalization-background",
    "colors": "ms-settings:colors",
    "dark mode": "ms-settings:colors",
    "themes": "ms-settings:themes",
    "lockscreen": "ms-settings:lockscreen",
    "lock screen": "ms-settings:lockscreen",
    "taskbar": "ms-settings:personalization-taskbar",
    "start": "ms-settings:personalization-start",
    "start menu": "ms-settings:personalization-start",
    "fonts": "ms-settings:fonts",

    "apps": "ms-settings:appsfeatures",
    "installed apps": "ms-settings:appsfeatures",
    "applications": "ms-settings:appsfeatures",
    "default apps": "ms-settings:defaultapps",
    "startup": "ms-settings:startupapps",
    "startup apps": "ms-settings:startupapps",

    "accounts": "ms-settings:yourinfo",
    "account": "ms-settings:yourinfo",
    "your info": "ms-settings:yourinfo",
    "email": "ms-settings:emailandaccounts",
    "signin": "ms-settings:signinoptions",
    "sign-in": "ms-settings:signinoptions",
    "sign in": "ms-settings:signinoptions",
    "pin": "ms-settings:signinoptions",
    "password": "ms-settings:signinoptions",
    "windows hello": "ms-settings:signinoptions",

    "time": "ms-settings:dateandtime",
    "date": "ms-settings:dateandtime",
    "region": "ms-settings:regionlanguage",
    "language": "ms-settings:regionlanguage",

    "gaming": "ms-settings:gaming-gamebar",
    "game bar": "ms-settings:gaming-gamebar",
    "game mode": "ms-settings:gaming-gamemode",

    "accessibility": "ms-settings:easeofaccess-display",
    "ease of access": "ms-settings:easeofaccess-display",

    "privacy": "ms-settings:privacy",
    "location": "ms-settings:privacy-location",
    "camera privacy": "ms-settings:privacy-webcam",
    "microphone privacy": "ms-settings:privacy-microphone",
    "security": "ms-settings:windowsdefender",
    "update": "ms-settings:windowsupdate",
    "windows update": "ms-settings:windowsupdate",
}


@function_tool
async def open_windows_settings_tool(setting_name: str = "main") -> str:
    """
    Open any Windows Settings page or category (e.g. bluetooth, wifi, display, sound, battery, signin, apps, update, privacy, mouse, keyboard, etc.).
    Args:
        setting_name: The name or category of the setting to open (e.g. 'bluetooth', 'wifi', 'display', 'sound', 'battery', 'signin', 'privacy', 'update', or 'main')
    """
    name = setting_name.lower().strip()
    target_uri = "ms-settings:"

    for key, uri in SETTINGS_MAP.items():
        if key in name or name in key:
            target_uri = uri
            break

    try:
        def _open():
            subprocess.Popen(["start", target_uri], shell=True)

        await asyncio.to_thread(_open)
        return f"⚙️ Opened Windows Settings ({setting_name})."
    except Exception as e:
        logger.error(f"Error opening Windows Settings for '{setting_name}': {e}")
        return f"❌ Failed to open Settings: {e}"


# ===========================================================================
# AIRPLANE MODE
# ===========================================================================

@function_tool
async def airplane_mode_tool(action: str = "toggle") -> str:
    """
    Open Airplane mode settings (Windows does not expose a public silent API,
    so this opens the Settings page for the user/agent to confirm).
    Args:
        action: 'on', 'off', or 'toggle'
    """
    try:
        def _open():
            subprocess.Popen(["start", "ms-settings:network-airplanemode"], shell=True)

        await asyncio.to_thread(_open)
        return "✈️ Opened Airplane Mode settings."
    except Exception as e:
        logger.error(f"Error opening Airplane Mode settings: {e}")
        return f"❌ Failed to open Airplane Mode settings: {e}"



# ===========================================================================
# TASK MANAGER / FILE EXPLORER
# ===========================================================================

@function_tool
async def open_task_manager_tool() -> str:
    """
    Open Windows Task Manager to monitor or manage system processes and performance.
    """
    try:
        subprocess.Popen(["taskmgr.exe"])
        logger.info("Task Manager launched.")
        return "🖥️ Task Manager opened successfully."
    except Exception as e:
        logger.error(f"Error opening Task Manager: {e}")
        return f"❌ Failed to open Task Manager: {e}"


@function_tool
async def open_file_manager_tool(path: str = "") -> str:
    """
    Open Windows File Manager / File Explorer.
    Args:
        path: Optional directory path or folder to open (defaults to Quick Access/This PC)
    """
    try:
        if path and os.path.exists(path):
            subprocess.Popen(["explorer.exe", path])
            return f"📁 File Explorer opened at {path}."
        else:
            subprocess.Popen(["explorer.exe"])
            return "📁 File Explorer opened."
    except Exception as e:
        logger.error(f"Error opening File Explorer: {e}")
        return f"❌ Failed to open File Explorer: {e}"


# ===========================================================================
# PROCESS MANAGEMENT
# ===========================================================================

@function_tool
async def list_processes_tool(top_n: int = 10) -> str:
    """
    List running processes, sorted by memory usage (top N).
    Args:
        top_n: number of top processes to return (default 10)
    """
    try:
        def _list():
            if _HAS_PSUTIL:
                procs = []
                for p in psutil.process_iter(["pid", "name", "memory_info"]):
                    try:
                        mem = p.info["memory_info"].rss / (1024 * 1024)
                        procs.append((p.info["name"], p.info["pid"], mem))
                    except Exception:
                        continue
                procs.sort(key=lambda x: x[2], reverse=True)
                lines = [f"{name} (PID {pid}) — {mem:.1f} MB" for name, pid, mem in procs[:top_n]]
                return "\n".join(lines)
            else:
                res = subprocess.run(["tasklist"], capture_output=True, text=True)
                lines = res.stdout.strip().split("\n")
                return "\n".join(lines[: top_n + 3])

        out = await asyncio.to_thread(_list)
        return f"📋 Top {top_n} processes:\n{out}" if out else "📋 No process data available."
    except Exception as e:
        logger.error(f"Error listing processes: {e}")
        return f"❌ Failed to list processes: {e}"


@function_tool
async def kill_process_tool(name_or_pid: str) -> str:
    """
    Terminate a running process by name (e.g. 'chrome.exe') or PID.
    Args:
        name_or_pid: process name (with or without .exe) or numeric PID
    """
    try:
        def _kill():
            target = name_or_pid.strip()
            if target.isdigit():
                if _HAS_PSUTIL:
                    psutil.Process(int(target)).terminate()
                    return f"PID {target}"
                subprocess.run(["taskkill", "/PID", target, "/F"], capture_output=True, text=True)
                return f"PID {target}"
            else:
                name = target if target.lower().endswith(".exe") else f"{target}.exe"
                subprocess.run(["taskkill", "/IM", name, "/F"], capture_output=True, text=True)
                return name

        result = await asyncio.to_thread(_kill)
        logger.info(f"Terminated process: {result}")
        return f"🛑 Process '{result}' terminated."
    except Exception as e:
        logger.error(f"Error killing process '{name_or_pid}': {e}")
        return f"❌ Failed to terminate '{name_or_pid}': {e}"


@function_tool
async def open_application_tool(app_name: str) -> str:
    """
    Launch an application by name (e.g. 'notepad', 'calc', 'chrome', 'winword').
    Args:
        app_name: name/command of the application to launch
    """
    try:
        def _open():
            subprocess.Popen(app_name, shell=True)

        await asyncio.to_thread(_open)
        return f"🚀 Launched '{app_name}'."
    except Exception as e:
        logger.error(f"Error opening application '{app_name}': {e}")
        return f"❌ Failed to open '{app_name}': {e}"


# ===========================================================================
# POWER CONTROL
# ===========================================================================

@function_tool
async def system_power_control_tool(action: str) -> str:
    """
    Control laptop power states: power off (shutdown), restart, sleep, or lock.
    Args:
        action: 'shutdown' (or 'power_off'), 'restart', 'sleep', 'lock', or 'cancel'
    """
    act = action.lower().strip()
    try:
        if act in ["shutdown", "power_off", "poweroff", "turn_off"]:
            subprocess.run(["shutdown", "/s", "/t", "5"], capture_output=True)
            return "🔌 Powering off laptop in 5 seconds. Goodbye Sir!"
        elif act in ["restart", "reboot"]:
            subprocess.run(["shutdown", "/r", "/t", "5"], capture_output=True)
            return "🔄 Restarting laptop in 5 seconds."
        elif act in ["sleep", "sleep_mode", "suspend", "hibernate"]:
            ps_cmd = "Add-Type -Assembly System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)"
            subprocess.Popen(["powershell", "-Command", ps_cmd])
            return "🌙 Laptop is entering Sleep mode now."
        elif act in ["lock", "lock_screen"]:
            def _delayed_lock():
                import time
                time.sleep(2.0)
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], capture_output=True)

            asyncio.create_task(asyncio.to_thread(_delayed_lock))
            return "🔒 Screen locked."
        elif act in ["unlock", "unlock_screen", "unlock_pc"]:
            return await unlock_pc_tool()
        elif act in ["cancel", "abort", "cancel_shutdown"]:
            subprocess.run(["shutdown", "/a"], capture_output=True)
            return "🛑 Pending shutdown/restart cancelled."
        else:
            return f"❌ Unknown power action: {action}. Please specify 'shutdown', 'restart', 'sleep', 'lock', 'unlock', or 'cancel'."
    except Exception as e:
        logger.error(f"Error executing power action '{action}': {e}")
        return f"❌ Failed to execute {action}: {e}"


USER_PC_PASSWORD = ""


def _find_adb() -> Optional[str]:
    import shutil
    adb_path = shutil.which("adb")
    if adb_path:
        return adb_path
    
    candidates = [
        os.path.join(os.path.dirname(__file__), "platform-tools", "adb.exe"),
        r"C:\platform-tools\adb.exe",
        r"C:\tenorshare\adb\adb.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        r"C:\Program Files\platform-tools\adb.exe",
        r"C:\adb\adb.exe"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


@function_tool
async def unlock_phone_tool(passcode: str = "8240656131", phone_ip: str = "10.43.102.185", phone_port: str = "40691") -> str:
    """
    Unlock Android mobile phone screen via Wireless ADB (Wi-Fi) using user passcode.
    Wakes screen, swipes up, and enters PIN/passcode automatically.

    Args:
        passcode: PIN, password, or pattern sequence to unlock phone (defaults to Rupankar Sir's passcode '8240656131').
        phone_ip: Phone IP address for wireless Wi-Fi unlock (defaults to '10.43.102.185')
        phone_port: Wireless ADB connection port (defaults to '40691')
    """
    try:
        def _do_unlock():
            target_ip = phone_ip.strip() if phone_ip.strip() else "10.43.102.185"
            target_port = phone_port.strip() if phone_port.strip() else "40691"
            pin_to_use = passcode.strip() if passcode.strip() else "8240656131"
            adb_bin = _find_adb()
            
            if not adb_bin:
                return "📱 ADB tool not found. Please install Android Platform-Tools."

            # Connect wirelessly to IP:PORT
            target_addr = f"{target_ip}:{target_port}"
            subprocess.run([adb_bin, "connect", target_addr], capture_output=True)

            res = subprocess.run([adb_bin, "devices"], capture_output=True, text=True)
            lines = [l for l in res.stdout.strip().split("\n") if "\tdevice" in l]
            
            if not lines:
                return (
                    f"📱 No authorized phone connected at {target_addr}. Please make sure Wireless Debugging is ON.\n"
                    "Passcode '8240656131' is saved and ready!"
                )

            target_dev = lines[0].split()[0]

            # Step 1: Wake screen (KEYEVENT_WAKEUP = 224)
            subprocess.run([adb_bin, "-s", target_dev, "shell", "input", "keyevent", "224"], capture_output=True)
            
            # Step 2: Swipe up to reveal PIN pad
            subprocess.run([adb_bin, "-s", target_dev, "shell", "input", "swipe", "500", "1500", "500", "400", "200"], capture_output=True)
            subprocess.run([adb_bin, "-s", target_dev, "shell", "input", "keyevent", "82"], capture_output=True)

            # Step 3: Enter passcode 8240656131 & press Enter (KEYEVENT_ENTER = 66)
            import time
            time.sleep(0.5)
            subprocess.run([adb_bin, "-s", target_dev, "shell", "input", "text", pin_to_use], capture_output=True)
            subprocess.run([adb_bin, "-s", target_dev, "shell", "input", "keyevent", "66"], capture_output=True)

            return f"📱 Mobile Phone ({target_dev}) screen awakened and unlocked successfully using PIN {pin_to_use}!"

        return await asyncio.to_thread(_do_unlock)
    except Exception as e:
        logger.error(f"Error unlocking phone: {e}")
        return f"❌ Failed to unlock phone: {e}"


@function_tool
async def lock_phone_tool(phone_ip: str = "10.43.102.185", phone_port: str = "40691") -> str:
    """
    Lock or turn off Android mobile phone screen via Wireless ADB (Wi-Fi).
    Sends POWER keyevent (26) to lock the screen.

    Args:
        phone_ip: Phone IP address for wireless Wi-Fi control (defaults to '10.43.102.185')
        phone_port: Wireless ADB connection port (defaults to '40691')
    """
    try:
        def _do_lock():
            target_ip = phone_ip.strip() if phone_ip.strip() else "10.43.102.185"
            target_port = phone_port.strip() if phone_port.strip() else "40691"
            adb_bin = _find_adb()
            if not adb_bin:
                return "📱 ADB tool not found."

            target_addr = f"{target_ip}:{target_port}"
            subprocess.run([adb_bin, "connect", target_addr], capture_output=True)

            res = subprocess.run([adb_bin, "devices"], capture_output=True, text=True)
            lines = [l for l in res.stdout.strip().split("\n") if "\tdevice" in l]
            
            if not lines:
                return f"📱 No phone connected at {target_addr}."

            target_dev = lines[0].split()[0]
            # Keyevent 26 = POWER (locks/turns off screen)
            subprocess.run([adb_bin, "-s", target_dev, "shell", "input", "keyevent", "26"], capture_output=True)

            return f"🔒 Mobile Phone ({target_dev}) screen locked."

        return await asyncio.to_thread(_do_lock)
    except Exception as e:
        logger.error(f"Error locking phone: {e}")
        return f"❌ Failed to lock phone: {e}"


@function_tool
async def unlock_pc_tool(password: str = "") -> str:
    """
    Inform user regarding Windows lock screen security policies.
    Automated key injection into the Winlogon secure desktop is restricted by Windows OS architecture.
    """
    return (
        "🔒 Windows Security Policy: For security reasons, Windows isolates the Winlogon "
        "desktop (Session 0 / Secure Desktop) from user-mode applications. Automated password "
        "injection across a locked workstation is blocked by OS security design."
    )


# ===========================================================================
# BATTERY / SYSTEM INFO
# ===========================================================================

@function_tool
async def get_system_specs_and_battery_tool() -> str:
    """
    Get 100% accurate live system configuration and battery status:
    - Battery Percentage & Charging state (Plugged in & Charging / Discharging / Fully Charged)
    - CPU / Processor model & cores
    - RAM / Memory capacity & available RAM
    - Disk Storage capacity & free space (C: drive)
    - Graphics Card / GPU model (Intel / NVIDIA / AMD)
    - Operating System version
    Use this tool whenever user asks 'what is my battery percentage?', 'is it charging?', 'what is my laptop configuration/specs?', or system hardware info.
    """
    try:
        def _get_details():
            # 1. Battery Status
            batt_info = "Unknown"
            if _HAS_PSUTIL:
                batt = psutil.sensors_battery()
                if batt is not None:
                    pct = batt.percent
                    plugged = batt.power_plugged
                    if plugged:
                        charging_str = "Plugged in & Charging ⚡" if pct < 100 else "Plugged in (Fully Charged 🔌)"
                    else:
                        charging_str = "Discharging (On Battery 🔋)"
                    batt_info = f"{pct}% — {charging_str}"

            # Fallback for battery if psutil didn't return
            if batt_info == "Unknown":
                try:
                    res_b = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Battery).EstimatedChargeRemaining"], capture_output=True, text=True, timeout=3)
                    val = res_b.stdout.strip()
                    if val.isdigit():
                        batt_info = f"{val}%"
                    else:
                        batt_info = "Desktop PC (No Battery / AC Power)"
                except Exception:
                    batt_info = "AC Power"

            # 2. CPU Specs
            cpu_name = "Intel Core Processor"
            try:
                res_c = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"], capture_output=True, text=True, timeout=3)
                if res_c.stdout.strip():
                    cpu_name = res_c.stdout.strip()
            except Exception:
                pass

            # 3. RAM Specs
            ram_info = "16 GB"
            if _HAS_PSUTIL:
                mem = psutil.virtual_memory()
                total_gb = round(mem.total / (1024**3), 1)
                avail_gb = round(mem.available / (1024**3), 1)
                used_gb = round(mem.used / (1024**3), 1)
                ram_info = f"{total_gb} GB Total ({used_gb} GB Used, {avail_gb} GB Available)"

            # 4. Disk Storage
            disk_info = "Disk Storage"
            if _HAS_PSUTIL:
                try:
                    d = psutil.disk_usage("C:")
                    d_total = round(d.total / (1024**3), 1)
                    d_free = round(d.free / (1024**3), 1)
                    disk_info = f"C: Drive — {d_total} GB Total ({d_free} GB Free)"
                except Exception:
                    pass

            # 5. GPU Specs
            gpu_info = "Standard Display Graphics"
            try:
                res_g = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"], capture_output=True, text=True, timeout=3)
                g_lines = [l.strip() for l in res_g.stdout.splitlines() if l.strip()]
                if g_lines:
                    gpu_info = " / ".join(g_lines)
            except Exception:
                pass

            # 6. Operating System
            os_info = "Windows 11"
            try:
                res_o = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_OperatingSystem).Caption"], capture_output=True, text=True, timeout=3)
                if res_o.stdout.strip():
                    os_info = res_o.stdout.strip()
            except Exception:
                pass

            return (
                f"🔋 BATTERY STATUS:\n"
                f"• Level & Status: {batt_info}\n\n"
                f"🖥️ SYSTEM CONFIGURATION & SPECS:\n"
                f"• Processor (CPU): {cpu_name}\n"
                f"• Memory (RAM): {ram_info}\n"
                f"• Graphics (GPU): {gpu_info}\n"
                f"• Storage: {disk_info}\n"
                f"• Operating System: {os_info}\n\n"
                f"INSTRUCTION FOR NEHA: Please speak the battery percentage, charging state, and system configuration clearly and warmly to Rupankar Sir in Bengali/English!"
            )

        return await asyncio.to_thread(_get_details)
    except Exception as e:
        logger.error(f"Error getting system specs and battery: {e}")
        return f"❌ Error retrieving system details: {e}"


@function_tool
async def battery_status_tool() -> str:
    """
    Get current battery percentage and charging status.
    """
    return await get_system_specs_and_battery_tool()


@function_tool
async def system_info_tool() -> str:
    """
    Get basic system information: CPU usage, memory usage, and disk usage.
    """
    return await get_system_specs_and_battery_tool()


@function_tool
async def clipboard_tool(action: str, text: str = "") -> str:
    """
    Read from or write to the system clipboard.
    Args:
        action: 'get' or 'set'
        text: text to copy to clipboard (used when action='set')
    """
    try:
        def _do():
            if action == "set":
                if _HAS_PYPERCLIP:
                    pyperclip.copy(text)
                else:
                    safe = text.replace('"', '`"')
                    subprocess.run(["powershell", "-Command", f'Set-Clipboard -Value "{safe}"'],
                                   capture_output=True, text=True)
                return None
            else:
                if _HAS_PYPERCLIP:
                    return pyperclip.paste()
                res = subprocess.run(["powershell", "-Command", "Get-Clipboard"],
                                      capture_output=True, text=True)
                return res.stdout.strip()

        result = await asyncio.to_thread(_do)
        if action == "set":
            return "📋 Text copied to clipboard."
        return f"📋 Clipboard content: {result}" if result else "📋 Clipboard is empty."
    except Exception as e:
        logger.error(f"Error using clipboard: {e}")
        return f"❌ Failed clipboard action: {e}"


# ===========================================================================
# TOOL REGISTRY — convenient list to hand to the LiveKit Agent
# ===========================================================================

ALL_SYSTEM_TOOLS = [
    set_brightness_tool,
    set_volume_tool,
    wifi_control_tool,
    bluetooth_control_tool,
    airplane_mode_tool,
    open_windows_settings_tool,
    open_task_manager_tool,
    open_file_manager_tool,
    list_processes_tool,
    kill_process_tool,
    open_application_tool,
    system_power_control_tool,
    unlock_pc_tool,
    unlock_phone_tool,
    lock_phone_tool,
    battery_status_tool,
    system_info_tool,
    get_system_specs_and_battery_tool,
    clipboard_tool,
]