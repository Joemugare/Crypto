import logging
import time
from typing import Dict, List, Optional, Union
from functools import wraps
from datetime import datetime, timedelta
import json
import os

import requests
from django.core.cache import cache
from django.conf import settings
from django.http import HttpResponseForbidden
from dotenv import load_dotenv

# Load .env keys
load_dotenv()

COINGECKO_API_KEY = getattr(settings, 'COINGECKO_API_KEY', os.getenv("COINGECKO_API_KEY"))
NEWSAPI_KEY = getattr(settings, 'NEWSAPI_KEY', os.getenv("NEWSAPI_KEY"))

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Check for vaderSentiment
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    logger.warning("vaderSentiment not installed. Sentiment analysis disabled.")

# ------------------ Middleware ------------------

class BlockWpAdminMiddleware:
    """Middleware to block suspicious requests to wp-admin paths"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/wp-admin'):
            logger.warning(f"Blocked suspicious request to {request.path}")
            return HttpResponseForbidden("Access denied")
        return self.get_response(request)

# ------------------ Rate Limiting ------------------

def adaptive_rate_limit_handler(max_retries: int = 3, base_delay: int = 60, backoff_multiplier: float = 2):
    """Decorator for handling API rate limits with exponential backoff and caching"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            lock_key = f"lock:{func_name}"
            rate_limit_key = f"rate_limit:{func_name}"

            if rate_limit_until := cache.get(rate_limit_key):
                if time.time() < rate_limit_until:
                    wait_time = rate_limit_until - time.time()
                    logger.warning(f"{func_name} rate limited for {wait_time:.1f}s")
                    return _get_cached_data(func_name)

            if cache.get(lock_key):
                logger.info(f"Another instance of {func_name} is running")
                time.sleep(2)
                return _get_cached_data(func_name)

            cache.set(lock_key, 1, timeout=120)
            try:
                for attempt in range(max_retries):
                    try:
                        result = func(*args, **kwargs)
                        cache.delete(rate_limit_key)
                        if result:
                            cache.set(f"{func_name}_cache", result, timeout=86400)
                            cache.set(f"{func_name}_cache_timestamp", time.time(), timeout=86400)
                        return result

                    except requests.exceptions.HTTPError as e:
                        wait_time = _handle_http_error(e, func_name, attempt, max_retries, base_delay, backoff_multiplier)
                        if wait_time and attempt < max_retries - 1:
                            time.sleep(wait_time)
                            continue
                        return _get_cached_data(func_name)

                    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                        logger.warning(f"{type(e).__name__} for {func_name} (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            time.sleep(base_delay * (backoff_multiplier ** attempt))
                            continue
                        return _get_cached_data(func_name)

                    except Exception as e:
                        logger.error(f"Unexpected error in {func_name}: {e}", exc_info=True)
                        return _get_cached_data(func_name)
            finally:
                cache.delete(lock_key)
        return wrapper
    return decorator

def _handle_http_error(e: requests.exceptions.HTTPError, func_name: str, attempt: int,
                      max_retries: int, base_delay: int, backoff_multiplier: float) -> Optional[float]:
    """Handle HTTP errors with appropriate rate limiting logic"""
    if e.response.status_code == 429:
        retry_after = int(e.response.headers.get('Retry-After', base_delay))
        reset_time = e.response.headers.get('X-RateLimit-Reset')
        wait_time = _calculate_wait_time(retry_after, reset_time, base_delay, backoff_multiplier, attempt)
        logger.warning(f"Rate limit hit for {func_name}. Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
        cache.set(f"rate_limit:{func_name}", time.time() + wait_time, timeout=int(wait_time) + 60)
        return wait_time
    elif e.response.status_code == 403:
        logger.error(f"API key invalid or quota exceeded for {func_name}")
    else:
        logger.error(f"HTTP error {e.response.status_code} for {func_name}: {e}")
    return base_delay * (backoff_multiplier ** attempt)

def _calculate_wait_time(retry_after: int, reset_time: Optional[str], base_delay: int,
                        backoff_multiplier: float, attempt: int) -> float:
    """Calculate wait time for rate limiting"""
    if reset_time:
        try:
            return max(float(reset_time) - time.time(), retry_after)
        except (ValueError, TypeError):
            pass
    return min(retry_after, base_delay * (backoff_multiplier ** attempt))

def _get_cached_data(func_name: str) -> Optional[Dict]:
    """Get cached data if available and fresh enough"""
    cached_data = cache.get(f"{func_name}_cache")
    cache_timestamp = cache.get(f"{func_name}_cache_timestamp")
    if cached_data and cache_timestamp and (time.time() - cache_timestamp < 3600):
        logger.info(f"Using cached {func_name} data")
        return cached_data
    logger.warning(f"No fresh cached data for {func_name}")
    return _get_fallback_data(func_name)

def _get_fallback_data(func_name: str) -> Optional[Dict]:
    """Return fallback data when API calls fail"""
    if func_name == 'fetch_market_data':
        logger.critical("USING EMERGENCY DEFAULT PRICES - NOT FOR TRADING")
        return {
            "bitcoin": {"usd":0.0,"usd_24h_change":0.0,"volume_24h":0.0,"market_cap":0.0,"symbol":"BTC","name":"Bitcoin","market_cap_rank":1,"last_updated":"EMERGENCY_DATA","sentiment":"ERROR - No Real Data"},
            "ethereum": {"usd":0.0,"usd_24h_change":0.0,"volume_24h":0.0,"market_cap":0.0,"symbol":"ETH","name":"Ethereum","market_cap_rank":2,"last_updated":"EMERGENCY_DATA","sentiment":"ERROR - No Real Data"}
        }
    elif func_name == 'fetch_news':
        return []
    elif func_name == 'fetch_sentiment':
        return {"score":0.5,"label":"Neutral"}
    elif func_name == 'fetch_valid_coins':
        return ['bitcoin','ethereum','binancecoin','cardano','solana']
    return None

# ------------------ Market Data ------------------

@adaptive_rate_limit_handler(max_retries=3, base_delay=45)
def fetch_market_data(diagnostic_mode: bool=False, min_coins: int=30) -> Optional[Dict]:
    """Fetch real-time market data from CoinGecko Pro API"""
    cached_data = cache.get('market_data')
    cache_age = cache.get('market_data_timestamp')
    if cached_data and cache_age and (time.time()-cache_age)<300 and len(cached_data)>=min_coins:
        logger.info(f"Using cached market data ({len(cached_data)} coins)")
        return cached_data

    market_data = {}
    page = 1
    max_pages = 3
    try:
        while len(market_data) < min_coins and page <= max_pages:
            url = "https://pro-api.coingecko.com/api/v3/coins/markets" if COINGECKO_API_KEY else "https://api.coingecko.com/api/v3/coins/markets"
            headers = {'x-cg-pro-api-key': COINGECKO_API_KEY} if COINGECKO_API_KEY else {}
            params = {
                'vs_currency':'usd','order':'market_cap_desc','per_page':50,'page':page,'sparkline':'false','price_change_percentage':'1h,24h,7d'
            }
            logger.info(f"Fetching market data page {page}")
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            skipped = []
            for coin in data:
                if 'id' not in coin or coin.get('current_price') is None:
                    skipped.append(coin.get('id','unknown'))
                    continue
                market_data[coin['id']] = {
                    "usd": float(coin['current_price']),
                    "usd_24h_change": float(coin.get('price_change_percentage_24h',0)),
                    "volume_24h": float(coin.get('total_volume',0)),
                    "market_cap": float(coin.get('market_cap',0)),
                    "market_cap_rank": coin.get('market_cap_rank',0),
                    "symbol": coin.get('symbol','').upper(),
                    "name": coin.get('name',''),
                    "last_updated": coin.get('last_updated',''),
                    "sentiment": "Neutral"
                }
            page += 1
            time.sleep(1)

        cache.set('market_data', market_data, timeout=3600)
        cache.set('market_data_timestamp', time.time(), timeout=3600)
        return market_data
    except Exception as e:
        logger.error(f"Error fetching market data: {e}", exc_info=True)
        return cached_data if cached_data else _get_fallback_data('fetch_market_data')

# ------------------ Valid Coins ------------------

@adaptive_rate_limit_handler(max_retries=2, base_delay=10)
def fetch_valid_coins() -> List[str]:
    """Fetch valid cryptocurrency IDs from CoinGecko"""
    if valid_coins := cache.get('valid_coins'):
        return valid_coins
    try:
        url = "https://pro-api.coingecko.com/api/v3/coins/list" if COINGECKO_API_KEY else "https://api.coingecko.com/api/v3/coins/list"
        headers = {'x-cg-pro-api-key': COINGECKO_API_KEY} if COINGECKO_API_KEY else {}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        valid_coins = [coin['id'].lower() for coin in response.json() if 'id' in coin]
        cache.set('valid_coins', valid_coins, timeout=86400)
        return valid_coins
    except Exception as e:
        logger.error(f"Error fetching valid coins: {e}", exc_info=True)
        return ['bitcoin','ethereum','binancecoin','cardano','solana']

# ------------------ News & Sentiment ------------------

def analyze_article_sentiment(text: str) -> Dict[str, Union[float,str]]:
    if not VADER_AVAILABLE or not text or len(text.strip())<10:
        return {"score":0.5,"label":"Neutral"}
    try:
        analyzer = SentimentIntensityAnalyzer()
        score = (analyzer.polarity_scores(text)['compound']+1)/2
        label = ("Very Positive" if score>0.65 else "Positive" if score>0.55 else "Neutral" if score>0.45 else "Negative" if score>0.35 else "Very Negative")
        return {"score":round(score,3),"label":label}
    except Exception as e:
        logger.error(f"Error analyzing sentiment: {e}", exc_info=True)
        return {"score":0.5,"label":"Neutral"}

@adaptive_rate_limit_handler(max_retries=2, base_delay=10)
def fetch_news() -> List[Dict]:
    """Fetch cryptocurrency news from NewsAPI"""
    cached_news = cache.get('crypto_news')
    if cached_news and cache.get('crypto_news_timestamp') and (time.time()-cache.get('crypto_news_timestamp'))<1800:
        return cached_news
    if not NEWSAPI_KEY:
        logger.warning("NewsAPI key not configured")
        return []
    try:
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                'q': 'cryptocurrency OR bitcoin OR ethereum',
                'apiKey': NEWSAPI_KEY,
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': 20,
                'from': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            },
            timeout=30
        )
        response.raise_for_status()
        articles = response.json().get('articles', [])
        
        processed_articles = []
        for article in articles:
            sentiment = analyze_article_sentiment(article.get('title', '') + ' ' + article.get('description', ''))
            processed_articles.append({
                'title': article.get('title'),
                'description': article.get('description'),
                'url': article.get('url'),
                'publishedAt': article.get('publishedAt'),
                'sentiment': sentiment
            })
        
        cache.set('crypto_news', processed_articles, timeout=1800)
        cache.set('crypto_news_timestamp', time.time(), timeout=1800)
        return processed_articles
    except Exception as e:
        logger.error(f"Error fetching news: {e}", exc_info=True)
        return cached_news if cached_news else _get_fallback_data('fetch_news')
