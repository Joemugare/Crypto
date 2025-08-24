import requests
import logging
import time
from django.core.cache import cache
from django.conf import settings
from functools import wraps
import os

logger = logging.getLogger(__name__)

def rate_limit_handler(max_retries=5, base_delay=180):
    """Decorator to handle rate limiting with exponential backoff and cache-based lock"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            lock_key = f"lock:{func.__name__}"
            acquired_lock = False

            try:
                # Try to acquire a cache-based lock to prevent concurrent calls
                if cache.get(lock_key):
                    logger.warning(f"API call for {func.__name__} locked; waiting for another instance")
                    time.sleep(10)
                    return cache.get(f"{func.__name__}_cache") or default_market_data() if func.__name__ == 'fetch_market_data' else None
                cache.set(lock_key, 1, timeout=120)
                acquired_lock = True

                for attempt in range(max_retries):
                    try:
                        result = func(*args, **kwargs)
                        return result
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 429:  # Too Many Requests
                            if attempt < max_retries - 1:
                                delay = base_delay * (2 ** attempt)  # Exponential backoff
                                logger.warning(f"Rate limit hit for {func.__name__}. Retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                                time.sleep(delay)
                                continue
                            else:
                                logger.error(f"Max retries ({max_retries}) exceeded for {func.__name__}. Rate limit still active.")
                                cached_data = cache.get(f"{func.__name__}_cache")
                                if cached_data is not None:
                                    logger.info(f"Returning stale cache data for {func.__name__} due to rate limit")
                                    return cached_data
                                return default_market_data() if func.__name__ == 'fetch_market_data' else None
                    except Exception as e:
                        logger.error(f"Error in {func.__name__}: {e}")
                        cached_data = cache.get(f"{func.__name__}_cache")
                        if cached_data is not None:
                            logger.info(f"Returning stale cache data for {func.__name__} due to error")
                            return cached_data
                        return default_market_data() if func.__name__ == 'fetch_market_data' else None
            finally:
                if acquired_lock:
                    cache.delete(lock_key)
            return default_market_data() if func.__name__ == 'fetch_market_data' else None
        return wrapper
    return decorator

@rate_limit_handler(max_retries=5, base_delay=180)
def fetch_market_data():
    """
    Fetch market data with caching and rate limit handling.
    Cache results for 2 hours to reduce API calls on Render.
    """
    # Log service spin-up and delay to avoid rate limits on Render
    logger.info("Checking service spin-up for fetch_market_data")
    spin_up_time = cache.get('service_spin_up')
    if not spin_up_time:
        cache.set('service_spin_up', time.time(), timeout=3600)
        logger.info("Service spin-up detected; delaying API call by 30s")
        time.sleep(30)  # Delay to avoid rate limit on Render spin-up
    
    # Check cache first
    cached_data = cache.get('market_data')
    if cached_data is not None:
        logger.info(f"Retrieved market data from cache ({len(cached_data)} coins)")
        return cached_data
    
    # Check last API call time to avoid rate limits
    last_call = cache.get('market_data_last_call')
    if last_call and (time.time() - last_call) < 180:  # Wait 180s between calls
        logger.warning("Skipping CoinGecko API call due to recent request")
        return cached_data if cached_data is not None else default_market_data()
    
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1&sparkline=false"
        logger.debug(f"Calling CoinGecko API: {url}")
        response = requests.get(url, timeout=30)
        logger.debug(f"CoinGecko API response status: {response.status_code}")
        response.raise_for_status()
        data = response.json()
        logger.debug(f"CoinGecko API response data: {data}")
        
        if not isinstance(data, list):
            logger.error(f"CoinGecko API returned unexpected data format: {type(data)}")
            return default_market_data()
        
        market_data = {
            coin['id']: {
                "usd": coin['current_price'],
                "usd_24h_change": coin['price_change_percentage_24h'],
                "volume_24h": coin['total_volume'],
                "sentiment": "Neutral"  # Placeholder
            } for coin in data if 'id' in coin and 'current_price' in coin
        }
        
        # Cache for 2 hours
        cache.set('market_data', market_data, timeout=7200)
        cache.set('market_data_last_call', time.time(), timeout=7200)
        cache.set('fetch_market_data_cache', market_data, timeout=86400)  # Stale cache for 24 hours
        logger.info(f"Fetched and cached {len(market_data)} coins for market data")
        return market_data
        
    except requests.Timeout:
        logger.error("Timeout while fetching market data from CoinGecko")
        return default_market_data()
    except requests.RequestException as e:
        logger.error(f"Error fetching market data from CoinGecko: {e}")
        return default_market_data()
    except ValueError as e:
        logger.error(f"Error parsing CoinGecko response: {e}")
        return default_market_data()

def default_market_data():
    """Return default market data as a fallback"""
    logger.warning("Returning default market data due to API failure")
    return {
        "bitcoin": {"usd": 0.0, "usd_24h_change": 0.0, "volume_24h": 0.0, "sentiment": "Neutral"},
        "ethereum": {"usd": 0.0, "usd_24h_change": 0.0, "volume_24h": 0.0, "sentiment": "Neutral"}
    }

def fetch_valid_coins():
    """
    Fetch the list of all valid cryptocurrency IDs from CoinGecko.
    Cache the result for 24 hours to avoid rate limits.
    """
    valid_coins = cache.get('valid_coins')
    if valid_coins is not None:
        logger.info(f"Retrieved {len(valid_coins)} valid coins from cache")
        return valid_coins
    
    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/coins/list",
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        valid_coins = [coin['id'].lower() for coin in data]
        cache.set('valid_coins', valid_coins, timeout=86400)  # Cache for 24 hours
        logger.info(f"Fetched {len(valid_coins)} valid coins from CoinGecko")
        return valid_coins
    except requests.RequestException as e:
        logger.error(f"Error fetching valid coins: {e}")
        return []

@rate_limit_handler(max_retries=2, base_delay=10)
def fetch_news():
    """
    Fetch news with caching to reduce API calls.
    Cache results for 10 minutes.
    """
    # Check cache first
    cached_news = cache.get('crypto_news')
    if cached_news is not None:
        logger.info(f"Retrieved {len(cached_news)} news articles from cache")
        return cached_news
    
    try:
        api_key = getattr(settings, 'NEWSAPI_KEY', 'your-newsapi-key')
        if api_key == 'your-newsapi-key':
            logger.warning("NewsAPI key not configured")
            return []
            
        url = f"https://newsapi.org/v2/everything?q=cryptocurrency+bitcoin+ethereum&apiKey={api_key}&language=en&sortBy=publishedAt&pageSize=20"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        articles = response.json().get('articles', [])
        
        news_data = [{
            "title": article["title"],
            "source": article["source"]["name"],
            "published_at": article["publishedAt"],
            "url": article["url"],
            "description": article["description"] or "",
            "sentiment": analyze_article_sentiment(article["title"] + " " + (article["description"] or ""))
        } for article in articles]
        
        # Cache for 10 minutes
        cache.set('crypto_news', news_data, timeout=600)
        logger.info(f"Fetched and cached {len(news_data)} news articles")
        return news_data
        
    except requests.RequestException as e:
        logger.error(f"Error fetching news: {e}")
        return []

def analyze_article_sentiment(text):
    """Analyze sentiment of article text"""
    positive_keywords = ["bullish", "surge", "rise", "gain", "success", "growth", "rally", "boom", "soar"]
    negative_keywords = ["bearish", "drop", "fall", "crash", "loss", "decline", "plunge", "dump", "tank"]
    
    text = text.lower()
    score = 0.5
    
    positive_count = sum(1 for keyword in positive_keywords if keyword in text)
    negative_count = sum(1 for keyword in negative_keywords if keyword in text)
    
    if positive_count > negative_count:
        score = min(0.9, 0.5 + (positive_count * 0.1))
    elif negative_count > positive_count:
        score = max(0.1, 0.5 - (negative_count * 0.1))
    
    label = "Positive" if score > 0.6 else "Negative" if score < 0.4 else "Neutral"
    return {"score": score, "label": label}

@rate_limit_handler(max_retries=2, base_delay=15)
def fetch_sentiment():
    """
    Fetch sentiment data with caching, falling back to news-based sentiment if API fails.
    Cache results for 15 minutes.
    """
    cached_sentiment = cache.get('crypto_sentiment')
    if cached_sentiment is not None:
        logger.info("Retrieved sentiment data from cache")
        return cached_sentiment
    
    try:
        # Optional: Check DNS resolution to avoid unnecessary retries
        import socket
        socket.gethostbyname('api.sentiment.io')  # Raises socket.gaierror if DNS fails
        
        response = requests.get("https://api.sentiment.io/v1/crypto-sentiment", timeout=30)
        response.raise_for_status()
        data = response.json()
        score = data.get("score", 0.5)
        label = "Positive" if score > 0.6 else "Negative" if score < 0.4 else "Neutral"
        
        sentiment_data = {"score": score, "label": label}
        cache.set('crypto_sentiment', sentiment_data, timeout=900)
        logger.info("Fetched and cached sentiment data from API")
        return sentiment_data
        
    except (requests.RequestException, socket.gaierror) as e:
        logger.error(f"Error fetching sentiment from API: {e}")
        # Fallback to news-based sentiment
        news = fetch_news()
        if news:
            avg_score = sum(article['sentiment']['score'] for article in news) / len(news)
            label = "Positive" if avg_score > 0.6 else "Negative" if avg_score < 0.4 else "Neutral"
            sentiment_data = {"score": avg_score, "label": label}
            logger.info("Using news-based sentiment as fallback")
            cache.set('crypto_sentiment', sentiment_data, timeout=900)
            return sentiment_data
        # Default fallback if news is unavailable
        logger.warning("No news data available, returning default sentiment")
        return {"score": 0.5, "label": "Neutral"}

# Utility function to clear all caches if needed
def clear_all_caches():
    """Clear all cached data"""
    cache.delete_many(['market_data', 'valid_coins', 'crypto_news', 'crypto_sentiment', 'market_data_last_call', 'fetch_market_data_cache', 'service_spin_up', 'lock:fetch_market_data'])
