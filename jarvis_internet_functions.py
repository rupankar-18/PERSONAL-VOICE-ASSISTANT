import os
import asyncio
import logging
import time
import urllib.parse
import webbrowser
from datetime import datetime
from dotenv import load_dotenv

try:
    from livekit.agents import function_tool
except ImportError:
    def function_tool(func):
        return func

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    import requests
    _HAS_HTTPX = False

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Helper function to open search in browser asynchronously
def _open_in_browser(url: str):
    try:
        logger.info(f"[Browser Launcher] Opening URL in browser: {url}")
        webbrowser.open(url)
    except Exception as e:
        logger.warning(f"[Browser Launcher] Failed to open browser URL '{url}': {e}")


# ---------------------------------------------------------
# 1. Search Wikipedia
# ---------------------------------------------------------
@function_tool
async def search_wikipedia(query: str, open_in_browser: bool = True) -> str:
    """
    Searches Wikipedia for summary, facts, and information on any topic, person, place, or concept.
    Optionally opens the Wikipedia page directly in Google Chrome browser.

    Args:
        query: Topic, title, or person to search on Wikipedia.
        open_in_browser: Whether to open the full Wikipedia page in browser (default True).
    """
    query_clean = query.strip()
    logger.info(f"[Wikipedia Tool] Searching Wikipedia for: '{query_clean}'")

    wiki_summary = ""
    wiki_url = ""

    # Attempt 1: Fetch via Wikipedia REST API
    try:
        search_api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query_clean)}"
        headers = {"User-Agent": "JarvisVoiceAssistant/1.0 (admin@jarvis.local)"}

        if _HAS_HTTPX:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(search_api_url, headers=headers)
        else:
            import requests as _req
            resp = await asyncio.to_thread(_req.get, search_api_url, headers=headers, timeout=4.0)

        if resp.status_code == 200:
            data = resp.json()
            title = data.get("title", query_clean)
            extract = data.get("extract", "")
            content_urls = data.get("content_urls", {}).get("desktop", {})
            wiki_url = content_urls.get("page", f"https://en.wikipedia.org/wiki/{urllib.parse.quote(query_clean)}")

            if extract:
                wiki_summary = f"Wikipedia article on '{title}':\n{extract}"
    except Exception as api_err:
        logger.warning(f"[Wikipedia Tool] REST API failed: {api_err}. Falling back to web search...")

    # Fallback to DuckDuckGo if direct REST API did not return an extract
    if not wiki_summary:
        try:
            def _ddgs_wiki():
                from ddgs import DDGS
                return list(DDGS().text(f"site:wikipedia.org {query_clean}", max_results=3))

            results = await asyncio.to_thread(_ddgs_wiki)
            if results:
                formatted = f"Wikipedia Search results for '{query_clean}':\n"
                for i, item in enumerate(results, start=1):
                    formatted += f"{i}. {item.get('title', '')}: {item.get('body', '')}\n"
                wiki_summary = formatted.strip()
                wiki_url = results[0].get("href", f"https://en.wikipedia.org/w/index.php?search={urllib.parse.quote(query_clean)}")
        except Exception as ddg_err:
            logger.error(f"[Wikipedia Tool] DDG search error: {ddg_err}")

    if not wiki_url:
        wiki_url = f"https://en.wikipedia.org/w/index.php?search={urllib.parse.quote(query_clean)}"

    if open_in_browser:
        _open_in_browser(wiki_url)

    return wiki_summary if wiki_summary else f"Opened Wikipedia search for '{query_clean}' in browser."


# ---------------------------------------------------------
# 2. Open Websites
# ---------------------------------------------------------
@function_tool
async def open_website(url_or_domain: str) -> str:
    """
    Opens any website URL or domain directly in Google Chrome browser.
    Examples: 'google.com', 'wikipedia.org', 'youtube.com', 'cricbuzz.com', 'moneycontrol.com', 'github.com', 'chatgpt.com'.

    Args:
        url_or_domain: Domain name or full URL to open.
    """
    target = url_or_domain.strip().lower()
    if not target.startswith("http://") and not target.startswith("https://"):
        if "." not in target:
            target = f"https://www.google.com/search?q={urllib.parse.quote(target)}"
        else:
            target = f"https://{target}"

    logger.info(f"[Open Website Tool] Opening website: {target}")
    _open_in_browser(target)
    return f"Successfully opened website '{url_or_domain}' in your browser."


# ---------------------------------------------------------
# 3. Close Websites / Browser Tabs / Windows
# ---------------------------------------------------------
@function_tool
async def close_website(website_or_tab_name: str = "chrome") -> str:
    """
    Closes open website tabs, search tabs, Chrome browser windows, Microsoft Edge browser windows, Google search tabs, YouTube, Wikipedia, or web apps.

    Args:
        website_or_tab_name: Target window, browser, or tab to close (e.g. 'chrome', 'edge', 'microsoft edge', 'google', 'search tab', 'tab', 'youtube', 'wikipedia').
    """
    from Jarvis_window_CTRL import close
    return await close(website_or_tab_name)


# ---------------------------------------------------------
# 4. Live Stock Prices
# ---------------------------------------------------------
@function_tool
async def get_stock_price(company_or_symbol: str) -> str:
    """
    Fetches live real-time stock market prices, indices, and market trends for Indian & global stocks (e.g., Sensex, Nifty 50, Reliance, Tata Motors, TCS, HDFC, Apple, Tesla, Nvidia).
    Simultaneously opens the stock search & live chart in Google Chrome browser.

    Args:
        company_or_symbol: Stock symbol or company name (e.g. 'Nifty 50', 'Sensex', 'Reliance', 'Tata Motors', 'Apple', 'Tesla').
    """
    query_clean = company_or_symbol.strip()
    logger.info(f"[Stock Price Tool] Fetching live stock info for: '{query_clean}'")

    search_query = f"{query_clean} live stock price index share market update today"
    
    # Simultaneously open search in Chrome browser
    _open_in_browser(f"https://www.google.com/search?q={urllib.parse.quote(search_query)}")

    try:
        def _ddgs_stock():
            from ddgs import DDGS
            return list(DDGS().text(search_query, max_results=3))

        results = await asyncio.to_thread(_ddgs_stock)
        if results:
            formatted = f"Live Stock & Market Update for '{query_clean}':\n"
            for i, item in enumerate(results, start=1):
                formatted += f"{i}. {item.get('title', '')}: {item.get('body', '')}\n"
            return formatted.strip()
        return f"No live stock data found for '{query_clean}'."
    except Exception as e:
        logger.error(f"[Stock Price Tool] Exception: {e}")
        return f"Error fetching stock price for '{query_clean}': {e}"


# ---------------------------------------------------------
# 5. Live Cricket Scores
# ---------------------------------------------------------
@function_tool
async def get_cricket_scores(match_or_team: str = "") -> str:
    """
    Fetches real-time live cricket match scores, ongoing tournament updates, ball-by-ball summaries, and match results.
    Simultaneously opens the live cricket score in Google Chrome browser.

    Args:
        match_or_team: Optional team name or match (e.g. 'India vs England', 'Australia', or leave empty for general live scores).
    """
    query = f"live cricket score update {match_or_team}".strip()
    logger.info(f"[Cricket Score Tool] Fetching cricket scores for: '{query}'")

    # Simultaneously open search in Chrome browser
    _open_in_browser(f"https://www.google.com/search?q={urllib.parse.quote(query)}")

    try:
        def _ddgs_cricket():
            from ddgs import DDGS
            return list(DDGS().news(query, max_results=3)) or list(DDGS().text(query, max_results=3))

        results = await asyncio.to_thread(_ddgs_cricket)
        if results:
            formatted = f"Live Cricket Score & Match Updates:\n"
            for i, item in enumerate(results, start=1):
                formatted += f"{i}. [{item.get('source', 'CricInfo')}] {item.get('title', '')}: {item.get('body', '')}\n"
            return formatted.strip()
        return "No active live cricket matches found at the moment."
    except Exception as e:
        logger.error(f"[Cricket Score Tool] Exception: {e}")
        return f"Error fetching cricket scores: {e}"


# ---------------------------------------------------------
# 6. IPL Updates
# ---------------------------------------------------------
@function_tool
async def get_ipl_updates(query: str = "IPL latest match score standings updates") -> str:
    """
    Fetches real-time Indian Premier League (IPL) match scores, team points table standings, schedule fixtures, and IPL news updates.
    Simultaneously opens IPL updates in Google Chrome browser.

    Args:
        query: Specific IPL query (e.g. 'KKR vs CSK score', 'IPL points table', 'IPL match today').
    """
    query_clean = query.strip()
    if "ipl" not in query_clean.lower():
        query_clean = f"IPL {query_clean}"

    logger.info(f"[IPL Updates Tool] Searching IPL news & scores for: '{query_clean}'")

    # Simultaneously open search in Chrome browser
    _open_in_browser(f"https://www.google.com/search?q={urllib.parse.quote(query_clean)}")

    try:
        def _ddgs_ipl():
            from ddgs import DDGS
            return list(DDGS().news(query_clean, max_results=3)) or list(DDGS().text(query_clean, max_results=3))

        results = await asyncio.to_thread(_ddgs_ipl)
        if results:
            formatted = f"Live IPL Score & Tournament Updates:\n"
            for i, item in enumerate(results, start=1):
                formatted += f"{i}. {item.get('title', '')}: {item.get('body', '')}\n"
            return formatted.strip()
        return "No recent IPL updates found for this query."
    except Exception as e:
        logger.error(f"[IPL Updates Tool] Exception: {e}")
        return f"Error fetching IPL updates: {e}"


# ---------------------------------------------------------
# 7. Currency Conversion
# ---------------------------------------------------------
@function_tool
async def convert_currency(amount: float, from_currency: str = "USD", to_currency: str = "INR") -> str:
    """
    Converts amounts between global currencies (e.g. USD to INR, EUR to INR, GBP to USD, CAD to INR) using real-time live exchange rates.
    Simultaneously opens the currency converter in Google Chrome browser.

    Args:
        amount: Numerical amount to convert.
        from_currency: Source currency code or name (e.g. 'USD', 'EUR', 'GBP').
        to_currency: Target currency code or name (e.g. 'INR', 'USD', 'EUR').
    """
    from_curr = from_currency.strip().upper()
    to_curr = to_currency.strip().upper()
    logger.info(f"[Currency Tool] Converting {amount} {from_curr} to {to_curr}")

    # Simultaneously open currency conversion in Chrome browser
    _open_in_browser(f"https://www.google.com/search?q={urllib.parse.quote(f'{amount} {from_curr} to {to_curr}')}")

    # Attempt 1: Open Exchange Rates free API
    try:
        api_url = f"https://open.er-api.com/v6/latest/{from_curr}"
        if _HAS_HTTPX:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(api_url)
        else:
            import requests as _req
            resp = await asyncio.to_thread(_req.get, api_url, timeout=4.0)

        if resp.status_code == 200:
            data = resp.json()
            rates = data.get("rates", {})
            rate = rates.get(to_curr)
            if rate:
                converted = amount * rate
                return f"Live Currency Conversion:\n{amount:,.2f} {from_curr} = {converted:,.2f} {to_curr} (Rate: 1 {from_curr} = {rate:.4f} {to_curr})"
    except Exception as api_err:
        logger.warning(f"[Currency Tool] API conversion failed: {api_err}. Falling back to web search...")

    # Fallback to web search
    search_query = f"{amount} {from_curr} to {to_curr} currency exchange rate today"
    try:
        def _ddgs_curr():
            from ddgs import DDGS
            return list(DDGS().text(search_query, max_results=2))

        results = await asyncio.to_thread(_ddgs_curr)
        if results:
            formatted = f"Live Currency Exchange Search:\n"
            for item in results:
                formatted += f"- {item.get('title', '')}: {item.get('body', '')}\n"
            return formatted.strip()
        return f"Could not perform currency conversion for {amount} {from_curr} to {to_curr}."
    except Exception as e:
        logger.error(f"[Currency Tool] Exception: {e}")
        return f"Error converting currency: {e}"


# ---------------------------------------------------------
# 8. Translation
# ---------------------------------------------------------
@function_tool
async def translate_text(text: str, target_language: str = "English", source_language: str = "auto") -> str:
    """
    Translates text between languages (e.g. Bengali to English, English to Bengali, Hindi to English, French to English).
    Simultaneously opens Google Translate in Google Chrome browser.

    Args:
        text: The phrase, sentence, or paragraph to translate.
        target_language: Target language to translate into (default 'English').
        source_language: Source language of the text (default 'auto').
    """
    text_clean = text.strip()
    target_lang = target_language.strip()
    logger.info(f"[Translation Tool] Translating text to {target_lang}: '{text_clean[:40]}...'")

    lang_map = {
        "bengali": "bn", "bangla": "bn", "bn": "bn",
        "hindi": "hi", "hi": "hi",
        "english": "en", "en": "en",
        "spanish": "es", "es": "es",
        "french": "fr", "fr": "fr",
        "german": "de", "de": "de",
    }
    t_code = lang_map.get(target_lang.lower(), target_lang[:2].lower())

    # Simultaneously open Google Translate in Chrome browser
    _open_in_browser(f"https://translate.google.com/?sl=auto&tl={t_code}&text={urllib.parse.quote(text_clean)}")

    # Attempt Google Translate free API endpoint
    try:
        gt_url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto" if source_language == "auto" else source_language,
            "tl": t_code,
            "dt": "t",
            "q": text_clean
        }

        if _HAS_HTTPX:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(gt_url, params=params)
        else:
            import requests as _req
            resp = await asyncio.to_thread(_req.get, gt_url, params=params, timeout=4.0)

        if resp.status_code == 200:
            data = resp.json()
            translated = "".join([segment[0] for segment in data[0] if segment[0]])
            if translated:
                return f"Translation ({target_lang}):\n{translated}"
    except Exception as gt_err:
        logger.warning(f"[Translation Tool] Google Translate API failed: {gt_err}. Falling back to web search...")

    # Fallback search
    search_query = f"translate '{text_clean}' into {target_lang}"
    try:
        def _ddgs_trans():
            from ddgs import DDGS
            return list(DDGS().text(search_query, max_results=2))

        results = await asyncio.to_thread(_ddgs_trans)
        if results:
            formatted = f"Translation Result:\n"
            for item in results:
                formatted += f"- {item.get('title', '')}: {item.get('body', '')}\n"
            return formatted.strip()
        return f"Could not translate text into {target_lang}."
    except Exception as e:
        logger.error(f"[Translation Tool] Exception: {e}")
        return f"Error translating text: {e}"


# ---------------------------------------------------------
# 9. Latest AI News
# ---------------------------------------------------------
@function_tool
async def get_latest_ai_news(topic: str = "Artificial Intelligence OpenAI Gemini Anthropic LLM") -> str:
    """
    Fetches the latest artificial intelligence (AI) news, model release announcements (GPT-5, Gemini, Claude, Llama, DeepSeek, Sora), and breakthrough tech updates.
    Simultaneously opens AI news search in Google Chrome browser.

    Args:
        topic: Specific AI topic or model (e.g. 'OpenAI', 'Gemini 2.5', 'Claude 3.7', 'DeepSeek', 'Generative AI news').
    """
    query_clean = topic.strip()
    if "ai" not in query_clean.lower() and "intelligence" not in query_clean.lower():
        query_clean = f"AI {query_clean}"

    search_query = f"{query_clean} latest news update launch 2026"
    logger.info(f"[AI News Tool] Searching latest AI news for: '{search_query}'")

    # Simultaneously open search in Chrome browser
    _open_in_browser(f"https://www.google.com/search?q={urllib.parse.quote(search_query)}")

    try:
        def _ddgs_ai():
            from ddgs import DDGS
            return list(DDGS().news(search_query, max_results=4)) or list(DDGS().text(search_query, max_results=4))

        results = await asyncio.to_thread(_ddgs_ai)
        if results:
            formatted = f"Latest AI News & Breakthrough Updates:\n"
            for i, item in enumerate(results, start=1):
                source = item.get("source", "Tech News")
                title = item.get("title", "")
                body = item.get("body", "")
                formatted += f"{i}. [{source}] {title}: {body}\n"
            return formatted.strip()
        return "No recent AI news articles found for this topic."
    except Exception as e:
        logger.error(f"[AI News Tool] Exception: {e}")
        return f"Error fetching AI news: {e}"
