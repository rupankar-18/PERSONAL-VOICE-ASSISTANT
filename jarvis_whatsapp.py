import os
import sys
import time
import asyncio
import urllib.parse
import webbrowser
import logging

try:
    import pyautogui
    pyautogui.PAUSE = 0.5
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None

try:
    from livekit.agents import function_tool
except ImportError:
    def function_tool(func):
        return func

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard using pyperclip, win32clipboard, or tkinter to ensure Unicode script support."""
    if pyperclip:
        try:
            pyperclip.copy(text)
            return True
        except Exception as e:
            logger.warning(f"pyperclip copy failed: {e}")
    try:
        import win32clipboard
        import win32con
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        logger.warning(f"win32clipboard failed: {e}")
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True
    except Exception as e:
        logger.warning(f"tkinter clipboard failed: {e}")
    return False


def _is_phone_number(text: str) -> bool:
    """Check if recipient string is a numeric phone number."""
    cleaned = text.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    return cleaned.isdigit() and len(cleaned) >= 7


def _format_phone(phone: str) -> str:
    """Format phone number into international standard (defaulting 10 digits to India +91)."""
    cleaned = phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    if len(cleaned) == 10:
        cleaned = "91" + cleaned
    return cleaned


def _focus_whatsapp_window() -> bool:
    """Attempt to bring WhatsApp Desktop or WhatsApp Web browser window to the foreground."""
    if not gw:
        return False
    try:
        all_wins = gw.getAllWindows()
        for win in all_wins:
            if win.title and "whatsapp" in win.title.lower():
                if win.isMinimized:
                    win.restore()
                win.activate()
                time.sleep(0.6)
                return True
    except Exception as e:
        logger.warning(f"Could not focus WhatsApp window directly: {e}")
    return False


@function_tool
async def open_whatsapp() -> str:
    """Open WhatsApp application or WhatsApp Web in the browser."""
    async def _async_open():
        try:
            webbrowser.open("whatsapp://")
            await asyncio.sleep(2.0)
            if not _focus_whatsapp_window():
                webbrowser.open("https://web.whatsapp.com")
        except Exception as e:
            logger.error(f"Error opening WhatsApp: {e}")

    asyncio.create_task(_async_open())
    return "WhatsApp window is opening."


@function_tool
async def send_whatsapp_message(recipient: str, message: str) -> str:
    """Open WhatsApp, search a contact name strictly in English, open their chat, write the message strictly in English, and send it.
    
    Args:
        recipient: The contact person's name strictly in English alphabet/script (e.g., 'Bapi', 'Maa', 'Amit', 'Rahul', 'Rupankar') or phone number (e.g. '+918240656131').
        message: The text message content strictly written in English (e.g., 'Hello, where are you?', 'Please call me when free').
    """
    if not recipient or not message:
        return "Error: Both recipient and message content are required."

    recipient_clean = recipient.strip()
    msg_clean = message.strip()

    logger.info(f"Initiating WhatsApp message to '{recipient_clean}': {msg_clean}")

    async def _async_send():
        try:
            if _is_phone_number(recipient_clean):
                phone = _format_phone(recipient_clean)
                encoded_msg = urllib.parse.quote(msg_clean)
                
                app_url = f"whatsapp://send?phone={phone}&text={encoded_msg}"
                web_url = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_msg}"

                logger.info(f"Opening WhatsApp URL for phone {phone}...")
                webbrowser.open(app_url)
                await asyncio.sleep(2.5)

                if not _focus_whatsapp_window():
                    webbrowser.open(web_url)
                    await asyncio.sleep(4.0)
                else:
                    await asyncio.sleep(1.0)

                if pyautogui:
                    pyautogui.press("enter")
            else:
                # Recipient is a contact name (e.g. "বাবা", "অমিত", "Rupankar", "Mom", "Rahul")
                logger.info(f"Opening WhatsApp to search contact '{recipient_clean}'...")
                webbrowser.open("whatsapp://")
                await asyncio.sleep(1.5)

                focused = _focus_whatsapp_window()
                if not focused:
                    webbrowser.open("https://web.whatsapp.com")
                    await asyncio.sleep(3.5)
                    _focus_whatsapp_window()

                if not pyautogui:
                    return

                # Step 1: Dismiss any popups
                pyautogui.press("escape")
                await asyncio.sleep(0.2)
                pyautogui.press("escape")
                await asyncio.sleep(0.2)

                # Step 2: Focus Search bar
                pyautogui.hotkey("ctrl", "f")
                await asyncio.sleep(0.3)

                # Clear search field
                pyautogui.hotkey("ctrl", "a")
                pyautogui.press("backspace")
                await asyncio.sleep(0.2)

                # Step 3: Paste contact name
                copied = _copy_to_clipboard(recipient_clean)
                if copied:
                    pyautogui.hotkey("ctrl", "v")
                else:
                    pyautogui.typewrite(recipient_clean, interval=0.03)
                
                logger.info(f"Searched for '{recipient_clean}' in WhatsApp.")
                await asyncio.sleep(1.2)

                # Step 4: Navigate down and press Enter
                pyautogui.press("down")
                await asyncio.sleep(0.3)
                pyautogui.press("enter")
                await asyncio.sleep(0.8)

                # Step 5: Paste message into chat text field
                copied_msg = _copy_to_clipboard(msg_clean)
                if copied_msg:
                    pyautogui.hotkey("ctrl", "v")
                else:
                    pyautogui.typewrite(msg_clean, interval=0.02)
                
                logger.info(f"Pasted message into chat for '{recipient_clean}'.")
                await asyncio.sleep(0.4)

                # Step 6: Send message
                pyautogui.press("enter")
                logger.info(f"Successfully sent WhatsApp message to '{recipient_clean}'.")

        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}", exc_info=True)

    asyncio.create_task(_async_send())
    return f"Sending WhatsApp message to '{recipient_clean}' now."


@function_tool
async def close_whatsapp() -> str:
    """Close WhatsApp application window, WhatsApp Desktop app, or WhatsApp Web browser tab."""
    logger.info("Initiating close WhatsApp...")
    try:
        from Jarvis_window_CTRL import close as close_window
        await close_window("whatsapp")
    except Exception as e:
        logger.warning(f"Window close error for WhatsApp: {e}")

    try:
        await asyncio.create_subprocess_shell("taskkill /IM WhatsApp.exe /F >nul 2>&1", shell=True)
        await asyncio.create_subprocess_shell("taskkill /IM WhatsApp.Desktop.exe /F >nul 2>&1", shell=True)
    except Exception as e:
        logger.warning(f"Taskkill WhatsApp fallback error: {e}")

    return "WhatsApp application and window have been successfully closed."

