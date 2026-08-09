import os
import asyncio
import logging
import time
from dotenv import load_dotenv
from livekit.agents import function_tool
from datetime import datetime

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    import requests
    _HAS_HTTPX = False

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- Deduplication cache ----
# Stores {normalized_query: (result_str, timestamp)}
_search_cache: dict[str, tuple[str, float]] = {}
_search_locks: dict[str, asyncio.Lock] = {}
_CACHE_TTL = 8.0   # seconds — same query within 8s returns cached result


def _get_search_lock(key: str) -> asyncio.Lock:
    """Return (or create) a per-query asyncio.Lock to prevent duplicate concurrent fetches."""
    if key not in _search_locks:
        _search_locks[key] = asyncio.Lock()
    return _search_locks[key]


import urllib.parse
import webbrowser

@function_tool
async def get_latest_news_and_knowledge(topic_or_query: str) -> str:
    """
    Fetches real-time live news headlines, breaking updates, and latest knowledge on any topic, event, person, or query.
    ALWAYS call this tool whenever the user asks about latest news, current affairs, recent events, sports updates,
    tech releases, world news, stock market updates, or asks 'what is happening with X' or any real-time knowledge question.

    Args:
        topic_or_query: The specific topic, keyword, person, or news query to search strictly in English.
    """
    query_clean = topic_or_query.strip()
    logger.info(f"[Real-Time News Tool] Searching latest news for: '{query_clean}'")

    # Simultaneously launch search results in browser
    try:
        webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query_clean)}")
    except Exception as e:
        logger.warning(f"Could not open browser for news search: {e}")

    cache_key = f"news_{query_clean.lower()}"
    cached = _search_cache.get(cache_key)
    if cached:
        result, ts = cached
        if time.monotonic() - ts < _CACHE_TTL:
            return result

    lock = _get_search_lock(cache_key)
    async with lock:
        cached = _search_cache.get(cache_key)
        if cached:
            result, ts = cached
            if time.monotonic() - ts < _CACHE_TTL:
                return result

        # 1. Try DuckDuckGo News search first for real-time news articles
        try:
            def _ddgs_news():
                from ddgs import DDGS
                return list(DDGS().news(query_clean, max_results=4))

            news_items = await asyncio.to_thread(_ddgs_news)
            if news_items:
                formatted = f"Real-Time Live News & Updates for '{query_clean}':\n"
                for i, item in enumerate(news_items, start=1):
                    title = item.get("title", "No Title")
                    source = item.get("source", "News")
                    body = item.get("body", "")
                    formatted += f"{i}. [{source}] {title}: {body}\n"

                result = formatted.strip()
                _search_cache[cache_key] = (result, time.monotonic())
                return result
        except Exception as ddg_err:
            logger.warning(f"[News Tool] DDG News error: {ddg_err}. Falling back to standard search...")

        # 2. Fallback to standard web search
        return await google_search(query_clean)


@function_tool
async def google_search(query: str) -> str:
    """Search Google and web for real-time information, queries, or user web searches formatted in English.
    Call this whenever the user asks to search or look up anything on Google or Chrome.

    Args:
        query: The search query strictly written/translated in English.
    """
    query_clean = query.strip()
    encoded_query = urllib.parse.quote(query_clean)
    google_url = f"https://www.google.com/search?q={encoded_query}"
    
    # Launch Chrome / Google browser with search results
    logger.info(f"Opening Google Chrome search: {google_url}")
    try:
        webbrowser.open(google_url)
    except Exception as e:
        logger.warning(f"Could not open browser for search: {e}")

    cache_key = query_clean.lower()

    # ---- Cache hit: return instantly without any network call ----
    cached = _search_cache.get(cache_key)
    if cached:
        result, ts = cached
        if time.monotonic() - ts < _CACHE_TTL:
            logger.info(f"[Cache HIT] Returning cached result for: {query!r}")
            return result

    # ---- Per-query lock: prevent duplicate concurrent fetches ----
    lock = _get_search_lock(cache_key)
    async with lock:
        # Re-check cache after acquiring lock (another coroutine may have filled it)
        cached = _search_cache.get(cache_key)
        if cached:
            result, ts = cached
            if time.monotonic() - ts < _CACHE_TTL:
                logger.info(f"[Cache HIT after lock] Returning cached result for: {query!r}")
                return result

        logger.info(f"Search Query received: {query}")

        api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        search_engine_id = os.getenv("SEARCH_ENGINE_ID")


        # Try Google Custom Search API if credentials are present
        if api_key and search_engine_id:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": api_key,
                "cx": search_engine_id,
                "q": query,
                "num": 3,          # ⚡ Reduced 4→3: faster parse, enough context for voice
            }

            try:
                if _HAS_HTTPX:
                    async with httpx.AsyncClient(timeout=2.5) as client:  # ⚡ 4s→2.5s
                        response = await client.get(url, params=params)
                else:
                    import requests as _requests
                    response = await asyncio.to_thread(_requests.get, url, params=params,
                                                       timeout=2.5)

                if response.status_code == 200:
                    data = response.json()
                    results = data.get("items", [])
                    if results:
                        formatted = ""
                        for i, item in enumerate(results, start=1):
                            title = item.get("title", "No title")
                            snippet = item.get("snippet", "")
                            formatted += f"{i}. {title}: {snippet}\n"
                        result = formatted.strip()
                        _search_cache[cache_key] = (result, time.monotonic())
                        return result
                else:
                    logger.warning(f"Google API status {response.status_code}. Falling back...")
            except Exception as e:
                logger.warning(f"Google API exception: {e}. Falling back to DuckDuckGo...")

        # Fallback: DuckDuckGo
        logger.info("Falling back to DuckDuckGo...")
        try:
            def _ddgs_search():
                from ddgs import DDGS
                return list(DDGS().text(query, max_results=3))  # ⚡ 4→3

            ddgs_results = await asyncio.to_thread(_ddgs_search)
            if not ddgs_results:
                return "No real-time search results found for this query."

            formatted = ""
            for i, item in enumerate(ddgs_results, start=1):
                title = item.get("title", "No title")
                body = item.get("body", "")
                formatted += f"{i}. {title}: {body}\n"

            result = formatted.strip()
            _search_cache[cache_key] = (result, time.monotonic())
            return result
        except Exception as e:
            logger.error(f"DuckDuckGo search exception: {e}")
            return f"Search error: {e}"


@function_tool
async def get_current_datetime() -> str:
    """Get the current live local date, time, day of the week, and timestamp."""
    now = datetime.now()
    return f"Current Local Date & Time: {now.strftime('%A, %B %d, %Y %I:%M:%S %p')} (ISO: {now.isoformat()})"

