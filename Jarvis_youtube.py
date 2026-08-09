import urllib.parse
import urllib.request
import re
import webbrowser
import asyncio
import logging
import pyautogui
from livekit.agents import function_tool

logger = logging.getLogger(__name__)
pyautogui.FAILSAFE = False


@function_tool
async def play_youtube(query: str) -> str:
    """Search YouTube for any song, music video, tutorial, or video requested by the user, open the top matching video directly in the browser, and play it out loud.
    
    Args:
        query: The title, artist name, song name, or topic of the video/song to search and play on YouTube (e.g., 'Arijit Singh Kesariya', 'Shape of You', 'Python tutorial').
    """
    try:
        query = query.strip()
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
        
        logger.info(f"Searching YouTube for song/video: {query}")
        
        def _get_top_video_url() -> str:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                }
                req = urllib.request.Request(search_url, headers=headers)
                html = urllib.request.urlopen(req, timeout=5.0).read().decode("utf-8")
                
                # Extract video IDs from YouTube search result HTML
                video_ids = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", html)
                if video_ids:
                    seen = set()
                    unique_ids = [v for v in video_ids if not (v in seen or seen.add(v))]
                    top_id = unique_ids[0]
                    return f"https://www.youtube.com/watch?v={top_id}"
            except Exception as inner_e:
                logger.warning(f"Direct video ID resolution failed: {inner_e}")
            return search_url

        target_url = await asyncio.to_thread(_get_top_video_url)
        
        logger.info(f"Launching YouTube URL in browser: {target_url}")
        await asyncio.to_thread(webbrowser.open, target_url)
        
        # Schedule 'k' keypress asynchronously in background so tool returns immediately
        async def _play_keypress():
            await asyncio.sleep(1.5)
            try:
                pyautogui.press('k')
            except Exception:
                pass
        asyncio.create_task(_play_keypress())

        if "watch?v=" in target_url:
            return f"Successfully found and opened the YouTube video '{query}' directly in your browser, and started playing it out loud."
        else:
            return f"Opened YouTube search for '{query}' in your browser."
            
    except Exception as e:
        logger.error(f"Error playing YouTube video/song: {e}")
        return f"Error playing YouTube video/song: {str(e)}"
