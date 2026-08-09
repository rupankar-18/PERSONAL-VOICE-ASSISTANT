import asyncio
import logging
import pyperclip
import pyautogui
from pynput.keyboard import Key, Controller as KeyboardController
from livekit.agents import function_tool

logger = logging.getLogger(__name__)
pyautogui.FAILSAFE = False
_keyboard = KeyboardController()


@function_tool
async def get_selected_text_tool() -> str:
    """
    Captures and retrieves the text, paragraph, sentence, or line currently selected/highlighted by the user on screen.
    Use this tool whenever the user asks to 'read this', 'summarize this', 'explain this', 'understand this for me',
    'what does this say', or refers to any highlighted text on any web page or application.

    Returns:
        str: The exact selected/highlighted text from the active window.
    """
    try:
        prev_clipboard = ""
        try:
            prev_clipboard = pyperclip.paste()
        except Exception:
            pass

        # Clear clipboard temporarily to detect fresh copied selection
        pyperclip.copy("")
        await asyncio.sleep(0.02)

        # Trigger Ctrl+C using pynput keyboard controller
        with _keyboard.pressed(Key.ctrl):
            _keyboard.press('c')
            _keyboard.release('c')

        await asyncio.sleep(0.04)
        selected_text = pyperclip.paste()

        # If pynput missed, fallback to pyautogui hotkey
        if not selected_text or not selected_text.strip():
            pyautogui.hotkey("ctrl", "c")
            await asyncio.sleep(0.04)
            selected_text = pyperclip.paste()

        if not selected_text or not selected_text.strip():
            if prev_clipboard:
                pyperclip.copy(prev_clipboard)
            return "No text is currently selected or highlighted on the screen. Please select a line or paragraph with your mouse or keyboard first."

        logger.info(f"[Selected Text Tool] Successfully captured {len(selected_text.strip())} chars of selected text.")
        return selected_text.strip()

    except Exception as e:
        logger.error(f"[Selected Text Tool] Error fetching selected text: {e}")
        return f"Error capturing selected text: {e}"
