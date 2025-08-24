# tracker/utils.py
import requests
import logging
import time
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

def fetch_market_data():
    """
    Fetch market data for top 50 coins with rate limit handling.
    Cache for 1 hour to reduce API calls.
    """
    market_data = cache.get('market_data')
    if market_data is not None:
        logger.info(f"Retrieved market data from cache for {len(market_data)} coins")
        return market_data
    for attempt in range(3):  # Retry up to 3 times
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1&sparkline=false"
            )
            response.raise_for_status()
            data = response.json()
            market_data = {
                coin['id']: {
                    "usd": coin['current_price'],
                    "usd_24h_change": coin['price_change_percentage_24h'],
                    "volume_24h": coin['total_volume'],
                    "sentiment": "Neutral"
                } for coin in data
            }
            cache.set('market_data', market_data, timeout=3600)  # Cache for 1 hour
            logger.info(f"Fetched {len(market_data)} coins for market data: {list(market_data.keys())}")
            return market_data
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                wait_time = 2 ** attempt * 10  # Exponential backoff: 10s, 20s, 40s
                logger.warning(f"Rate limit hit for market data. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Error fetching market data: {e}")
                return {}
        except requests.RequestException as e:
            logger.error(f"Error fetching market data: {e}")
            return {}
    logger.error("Failed to fetch market data after retries")
    return {}  # Fallback to empty dict

def fetch_valid_coins():
    """
    Fetch all valid cryptocurrency IDs from CoinGecko.
    Cache for 24 hours to avoid rate limits.
    """
    valid_coins = cache.get('valid_coins')
    if valid_coins is not None:
        logger.info(f"Retrieved {len(valid_coins)} valid coins from cache")
        return valid_coins
    for attempt in range(3):
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/coins/list"
            )
            response.raise_for_status()
            data = response.json()
            valid_coins = [coin['id'].lower() for coin in data]
            cache.set('valid_coins', valid_coins, timeout=86400)  # Cache for 24 hours
            logger.info(f"Fetched {len(valid_coins)} valid coins from CoinGecko")
            return valid_coins
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                wait_time = 2 ** attempt * 10
                logger.warning(f"Rate limit hit for valid coins. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Error fetching valid coins: {e}")
                return []
        except requests.RequestException as e:
            logger.error(f"Error fetching valid coins: {e}")
            return []
    logger.error("Failed to fetch valid coins after retries")
    return []  # Fallback to empty list

def fetch_news():
    try:
        api_key = getattr(settings, 'NEWSAPI_KEY', 'your-newsapi-key')
        url = f"https://newsapi.org/v2/everything?q=cryptocurrency+bitcoin+ethereum&apiKey={api_key}&language=en&sortBy=publishedAt&pageSize=20"
        response = requests.get(url)
        response.raise_for_status()
        articles = response.json().get('articles', [])
        return [{
            "title": article["title"],
            "source": article["source"]["name"],
            "published_at": article["publishedAt"],
            "url": article["url"],
            "description": article["description"] or "",
            "sentiment": analyze_article_sentiment(article["title"] + " " + (article["description"] or ""))
        } for article in articles]
    except requests.RequestException:
        return []

def analyze_article_sentiment(text):
    positive_keywords = ["bullish", "surge", "rise", "gain", "success", "growth"]
    negative_keywords = ["bearish", "drop", "fall", "crash", "loss", "decline"]
    text = text.lower()
    score = 0.5
    if any(keyword in text for keyword in positive_keywords):
        score = 0.7
    elif any(keyword in text for keyword in negative_keywords):
        score = 0.3
    label = "Positive" if score > 0.6 else "Negative" if score < 0.4 else "Neutral"
    return {"score": score, "label": label}

def fetch_sentiment():
    try:
        response = requests.get("https://api.sentiment.io/v1/crypto-sentiment")
        response.raise_for_status()
        data = response.json()
        score = data.get("score", 0.5)
        label = "Positive" if score > 0.6 else "Negative" if score < 0.4 else "Neutral"
        return {"score": score, "label": label}
    except requests.RequestException:
        return {"score": 0.5, "label": "Neutral"}
