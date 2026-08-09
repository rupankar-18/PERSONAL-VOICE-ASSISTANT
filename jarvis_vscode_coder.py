import sys
import os
import subprocess
import logging
import asyncio

try:
    from livekit.agents import function_tool
except ImportError:
    def function_tool(func):
        return func

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys_logger = logging.getLogger(__name__)

# Default directory where generated code files will be saved
DEFAULT_CODE_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "Jarvis_Codes")

LANGUAGE_EXTENSIONS = {
    "python": ".py",
    "py": ".py",
    "javascript": ".js",
    "js": ".js",
    "typescript": ".ts",
    "ts": ".ts",
    "html": ".html",
    "css": ".css",
    "cpp": ".cpp",
    "c++": ".cpp",
    "c": ".c",
    "java": ".java",
    "csharp": ".cs",
    "c#": ".cs",
    "go": ".go",
    "rust": ".rs",
    "php": ".php",
    "ruby": ".rb",
    "sql": ".sql",
    "json": ".json",
    "bash": ".sh",
    "shell": ".sh",
}


@function_tool
async def write_code_and_open_vscode(
    language: str,
    filename: str,
    code_content: str
) -> str:
    """
    Write or code any program in any programming language, save it to a file, and open it in VS Code.
    Call this tool whenever the user asks to open VS Code and write/code a program or script in any language.

    Args:
        language: Programming language (e.g. 'python', 'cpp', 'javascript', 'html', 'java', 'c', etc.)
        filename: Name of the file (e.g. 'main.py', 'app.js', 'calculator.cpp')
        code_content: Complete, valid source code for the requested program
    """
    try:
        filename = filename.strip()
        
        # Ensure file has extension
        _, ext = os.path.splitext(filename)
        if not ext:
            default_ext = LANGUAGE_EXTENSIONS.get(language.lower().strip(), ".txt")
            filename += default_ext

        os.makedirs(DEFAULT_CODE_DIR, exist_ok=True)
        file_path = os.path.join(DEFAULT_CODE_DIR, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code_content)

        sys_logger.info(f"✅ Code file saved at: {file_path}")

        # Launch VS Code with the created file
        cmd = f'code "{file_path}"'
        await asyncio.create_subprocess_shell(cmd, shell=True)

        return f"✅ Program code in {language} has been saved to '{filename}' and opened in VS Code."

    except Exception as e:
        sys_logger.error(f"❌ Error writing code or opening VS Code: {e}")
        return f"❌ Failed to code in VS Code: {e}"
