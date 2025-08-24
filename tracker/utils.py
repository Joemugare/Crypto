import requests
import logging
import time
from django.core.cache import cache
from django.conf import settings
from functools import wraps

logger = logging.getLogger(__name__)

def rate_limit_handler(max_retries=3, base_delay=20):
    """Decorator to handle rate limiting with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:  # Too Many Requests
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(f"Rate limit hit for {func.__name__}. Retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
                            time.sleep(delay)
                            continue
                        else:
                            logger.error(f"Max retries exceeded for {func.__name__}. Rate limit still active.")
                            return None
                    else:
                        raise e
                except Exception as e:
                    logger.error(f"Error in {func.__name__}: {e}")
                    return None
            return None
        return wrapper
    return decorator

@rate_limit_handler(max_retries=3, base_delay=20)
def fetch_market_data():
    """
    Fetch market data with caching and rate limit handling.
    Cache results for 5 minutes to reduce API calls.
    """
    # Check cache first
    cached_data = cache.get('market_data')
    if cached_data is not None:
        logger.info(f"Retrieved market data from cache ({len(cached_data)} coins)")
        return cached_data
    
    try:
        # Add timeout to prevent worker timeouts
        response = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1&sparkline=false",
            timeout=30  # 30 second timeout
        )
        response.raise_for_status()
        data = response.json()
        
        market_data = {
            coin['id']: {
                "usd": coin['current_price'],
                "usd_24h_change": coin['price_change_percentage_24h'],
                "volume_24h": coin['total_volume'],
                "sentiment": "Neutral"  # Placeholder
            } for coin in data
        }
        
        # Cache for 5 minutes
        cache.set('market_data', market_data, timeout=300)
        logger.info(f"Fetched and cached {len(data)} coins for market data")
        return market_data
        
    except requests.Timeout:
        logger.error("Timeout while fetching market data")
        return {}
    except requests.RequestException as e:
        logger.error(f"Error fetching market data: {e}")
        return {}

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
    Fetch sentiment data with caching.
    Cache results for 15 minutes.
    """
    # Check cache first
    cached_sentiment = cache.get('crypto_sentiment')
    if cached_sentiment is not None:
        logger.info("Retrieved sentiment data from cache")
        return cached_sentiment
    
    try:
        response = requests.get("https://api.sentiment.io/v1/crypto-sentiment", timeout=30)
        response.raise_for_status()
        data = response.json()
        score = data.get("score", 0.5)
        label = "Positive" if score > 0.6 else "Negative" if score < 0.4 else "Neutral"
        
        sentiment_data = {"score": score, "label": label}
        
        # Cache for 15 minutes
        cache.set('crypto_sentiment', sentiment_data, timeout=900)
        logger.info("Fetched and cached sentiment data")
        return sentiment_data
        
    except requests.RequestException as e:
        logger.error(f"Error fetching sentiment: {e}")
        return {"score": 0.5, "label": "Neutral"}

# Utility function to clear all caches if needed
def clear_all_caches():
    """Clear all cached data"""
    cache.delete_many(['market_data', 'valid_coins', 'crypto_news', 'crypto_sentiment'])
    logger.info("Cleared all cached data")
