import os
import subprocess
import asyncio
import logging
from datetime import datetime
from livekit.agents import function_tool

logger = logging.getLogger(__name__)


@function_tool
async def write_letter_in_notepad_tool(
    letter_title: str,
    letter_content: str
) -> str:
    """
    Writes a formatted letter into a text file and opens it immediately in Windows Notepad on screen.
    Call this tool AFTER gathering necessary details from the user (recipient, topic, sender, date, etc.)
    and drafting the complete, professionally formatted letter text.

    Args:
        letter_title: A short descriptive title for the letter file (e.g., 'Leave_Application', 'Permission_Letter', 'Job_Application').
        letter_content: The full body and text of the complete letter ready to be written.
    """
    try:
        # Sanitize title for filename
        safe_title = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in letter_title.strip())
        if not safe_title:
            safe_title = "Letter"

        # Determine target directory (Desktop or workspace)
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        onedrive_desktop = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
        
        target_dir = desktop_dir
        if os.path.exists(onedrive_desktop):
            target_dir = onedrive_desktop
        elif not os.path.exists(target_dir):
            target_dir = os.getcwd()

        filename = f"{safe_title}.txt"
        file_path = os.path.join(target_dir, filename)

        # Write content to text file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(letter_content.strip() + "\n")

        logger.info(f"[Letter Writer Tool] Written letter to: {file_path}")

        # Launch Windows Notepad with the file
        def _open_notepad():
            subprocess.Popen(["notepad.exe", file_path])

        await asyncio.to_thread(_open_notepad)

        return f"✅ Letter '{safe_title}' written successfully and opened in Notepad at {file_path}."

    except Exception as e:
        logger.error(f"[Letter Writer Tool] Failed to write letter in Notepad: {e}")
        return f"❌ Error writing letter in Notepad: {e}"
