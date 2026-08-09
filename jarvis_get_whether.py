import os
import asyncio
import logging
from dotenv import load_dotenv
from livekit.agents import function_tool

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    import requests
    _HAS_HTTPX = False

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache the detected city for the session — avoids a network round-trip on every weather call
_cached_city: str = ""


async def detect_city_by_ip() -> str:
    """Detect city from IP address asynchronously, with session-level caching."""
    global _cached_city
    if _cached_city:
        logger.info(f"City cache hit: {_cached_city}")
        return _cached_city

    try:
        logger.info("IP के ज़रिए शहर detect करने की कोशिश की जा रही है")
        if _HAS_HTTPX:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get("https://ipapi.co/json/")
                ip_info = resp.json()
        else:
            import requests as _req
            ip_info = await asyncio.to_thread(_req.get, "https://ipapi.co/json/")
            ip_info = ip_info.json()

        city = ip_info.get("city", "")
        if city:
            logger.info(f"IP से शहर Detect किया गया: {city}")
            _cached_city = city
            return city
        else:
            logger.warning("City detect करने में विफल, default 'Delhi' इस्तेमाल किया जा रहा है।")
            _cached_city = "Delhi"
            return "Delhi"
    except Exception as e:
        logger.error(f"IP से city detect करने में error आया: {e}")
        _cached_city = "Delhi"
        return "Delhi"


@function_tool
async def get_weather(city: str = "") -> str:
    """Get current live real-time weather information for a given city or current detected location."""
    if not city:
        city = await detect_city_by_ip()

    import urllib.parse, webbrowser
    try:
        webbrowser.open(f"https://www.google.com/search?q=current+weather+in+{urllib.parse.quote(city)}")
    except Exception as e:
        logger.warning(f"Could not open browser for weather search: {e}")

    api_key = os.getenv("OPENWEATHER_API_KEY")

    if api_key:
        logger.info(f"Fetching weather for city from OpenWeather API: {city}")
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": api_key,
            "units": "metric"
        }

        try:
            if _HAS_HTTPX:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    response = await client.get(url, params=params)
            else:
                import requests as _req
                response = await asyncio.to_thread(_req.get, url, params=params)

            if response.status_code == 200:
                data = response.json()
                weather = data["weather"][0]["description"].title()
                temperature = data["main"]["temp"]
                humidity = data["main"]["humidity"]
                wind_speed = data["wind"]["speed"]

                result = (f"Weather in {city}:\n"
                          f"- Condition: {weather}\n"
                          f"- Temperature: {temperature}°C\n"
                          f"- Humidity: {humidity}%\n"
                          f"- Wind Speed: {wind_speed} m/s")

                logger.info(f"Weather result: \n{result}")
                return result
            else:
                logger.warning(f"OpenWeather API returned status {response.status_code}. Falling back to web search...")
        except Exception as e:
            logger.warning(f"OpenWeather API exception: {e}. Falling back to web search...")

    # Fallback to web search for weather
    logger.info(f"Performing web search for current weather in {city}...")
    try:
        def _ddgs_weather():
            from ddgs import DDGS
            return list(DDGS().text(f"current weather in {city}", max_results=3))

        results = await asyncio.to_thread(_ddgs_weather)
        if results:
            formatted = f"Real-time Weather Search for {city}:\n"
            for i, item in enumerate(results, start=1):
                title = item.get("title", "")
                body = item.get("body", "")
                formatted += f"{i}. {title}\n{body}\n\n"
            return formatted.strip()
        return f"Could not retrieve weather details for {city}."
    except Exception as e:
        logger.error(f"Weather search exception: {e}")
        return f"Error fetching weather for {city}: {e}"

