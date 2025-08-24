import logging
import time
from typing import Dict, List, Optional, Union
from functools import wraps
from datetime import datetime, timedelta
import json

import requests
from django.core.cache import cache
from django.conf import settings
from django.http import HttpResponseForbidden
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

class BlockWpAdminMiddleware:
    """Middleware to block suspicious requests to wp-admin paths"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/wp-admin'):
            logger.warning(f"Blocked suspicious request to {request.path}")
            return HttpResponseForbidden("Access denied")
        return self.get_response(request)

def adaptive_rate_limit_handler(max_retries: int = 3, base_delay: int = 60, backoff_multiplier: float = 2):
    """
    Decorator for handling API rate limits with exponential backoff and caching

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        backoff_multiplier: Multiplier for exponential backoff
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            lock_key = f"lock:{func_name}"
            rate_limit_key = f"rate_limit:{func_name}"

            # Check rate limit status
            if rate_limit_until := cache.get(rate_limit_key):
                if time.time() < rate_limit_until:
                    wait_time = rate_limit_until - time.time()
                    logger.warning(f"{func_name} rate limited for {wait_time:.1f}s")
                    return _get_cached_data(func_name)

            # Check for concurrent execution
            if cache.get(lock_key):
                logger.info(f"Another instance of {func_name} is running")
                time.sleep(2)  # Prevent thundering herd
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
            "bitcoin": {
                "usd": 0.0, "usd_24h_change": 0.0, "volume_24h": 0.0,
                "market_cap": 0.0, "symbol": "BTC", "name": "Bitcoin",
                "market_cap_rank": 1, "last_updated": "EMERGENCY_DATA",
                "sentiment": "ERROR - No Real Data"
            },
            "ethereum": {
                "usd": 0.0, "usd_24h_change": 0.0, "volume_24h": 0.0,
                "market_cap": 0.0, "symbol": "ETH", "name": "Ethereum",
                "market_cap_rank": 2, "last_updated": "EMERGENCY_DATA",
                "sentiment": "ERROR - No Real Data"
            }
        }
    elif func_name == 'fetch_news':
        return []
    elif func_name == 'fetch_sentiment':
        return {"score": 0.5, "label": "Neutral"}
    return None

@adaptive_rate_limit_handler(max_retries=3, base_delay=45)
def fetch_market_data(diagnostic_mode: bool = False, min_coins: int = 30) -> Optional[Dict]:
    """
    Fetch real-time market data from CoinGecko API, ensuring at least min_coins are returned.

    Args:
        diagnostic_mode: If True, logs detailed information and saves API response.
        min_coins: Minimum number of coins to return.

    Returns:
        Dict of market data with at least min_coins entries or None if fetch fails.
    """
    # Check cache first
    cached_data = cache.get('market_data')
    cache_age = cache.get('market_data_timestamp')

    if cached_data and cache_age and (time.time() - cache_age) < 300 and len(cached_data) >= min_coins:
        logger.info(f"Using fresh market data cache ({(time.time() - cache_age)/60:.1f}m old, {len(cached_data)} coins)")
        return cached_data

    # Check recent API call timing
    if last_call := cache.get('market_data_last_call'):
        if (time.time() - last_call) < 10:
            logger.info(f"Recent API call detected, using cached data with {len(cached_data or {})} coins")
            if cached_data and len(cached_data) >= min_coins:
                return cached_data
            logger.warning(f"Cached data has only {len(cached_data or {})} coins, attempting fresh fetch")

    # Check rate limit
    if rate_limit_until := cache.get('rate_limit:fetch_market_data'):
        if time.time() < rate_limit_until:
            logger.warning(f"Rate limited for {(rate_limit_until - time.time()):.1f}s, using cached data")
            if cached_data and len(cached_data) >= min_coins:
                return cached_data
            logger.warning(f"Cached data has only {len(cached_data or {})} coins, returning fallback")
            return _get_fallback_data('fetch_market_data')

    market_data = {}
    page = 1
    max_pages = 3  # Limit to avoid excessive API calls

    try:
        while len(market_data) < min_coins and page <= max_pages:
            url = ("https://pro-api.coingecko.com/api/v3/coins/markets"
                   if hasattr(settings, 'COINGECKO_API_KEY') and settings.COINGECKO_API_KEY
                   else "https://api.coingecko.com/api/v3/coins/markets")
            headers = {'x-cg-pro-api-key': settings.COINGECKO_API_KEY} if hasattr(settings, 'COINGECKO_API_KEY') else {}
            params = {
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': 50,  # Increased to ensure enough coins
                'page': page,
                'sparkline': 'false',
                'price_change_percentage': '24h'
            }

            logger.info(f"Fetching market data from {url}, page {page} (diagnostic_mode={diagnostic_mode})")
            response = requests.get(url, headers=headers, params=params, timeout=30)

            # Log rate limit headers
            logger.info(f"API response: {response.status_code}, "
                       f"Rate limit remaining: {response.headers.get('X-RateLimit-Remaining', 'N/A')}, "
                       f"Used: {response.headers.get('X-RateLimit-Used', 'N/A')}")
            response.raise_for_status()

            data = response.json()

            if diagnostic_mode:
                logger.info(f"Raw API response (page {page}): {len(data)} coins received")
                with open(f'coingecko_response_page_{page}.json', 'w') as f:
                    json.dump(data, f, indent=2)
                    logger.info(f"Saved raw API response to coingecko_response_page_{page}.json")

            if not isinstance(data, list) or not data:
                logger.error(f"Invalid API response on page {page}: type={type(data)}, length={len(data)}")
                raise ValueError("Invalid API response format")

            skipped_coins = []
            for coin in data:
                # Relaxed validation to allow more coins
                if 'id' not in coin:
                    if diagnostic_mode:
                        skipped_coins.append({'reason': 'Missing id', 'coin': coin})
                    continue
                if coin.get('current_price') is None:
                    if diagnostic_mode:
                        skipped_coins.append({'reason': 'Missing/null price', 'coin': coin.get('id', 'unknown')})
                    continue

                market_data[coin['id']] = {
                    "usd": float(coin['current_price']),
                    "usd_24h_change": float(coin.get('price_change_percentage_24h', 0)),
                    "volume_24h": float(coin.get('total_volume', 0)),
                    "market_cap": float(coin.get('market_cap', 0)),
                    "market_cap_rank": coin.get('market_cap_rank', 0),
                    "symbol": coin.get('symbol', '').upper(),
                    "name": coin.get('name', ''),
                    "last_updated": coin.get('last_updated', ''),
                    "sentiment": "Neutral"
                }

            if diagnostic_mode and skipped_coins:
                logger.info(f"Skipped {len(skipped_coins)} coins on page {page}: {skipped_coins[:5]}")
                with open(f'skipped_coins_page_{page}.json', 'w') as f:
                    json.dump(skipped_coins, f, indent=2)
                    logger.info(f"Saved skipped coins to skipped_coins_page_{page}.json")

            logger.info(f"Page {page}: Added {len(market_data)} coins so far")
            page += 1
            time.sleep(1)  # Brief pause to avoid rate limits

        if len(market_data) < min_coins:
            logger.warning(f"Only retrieved {len(market_data)} coins, below target of {min_coins}")
            if cached_data and len(cached_data) >= min_coins:
                logger.info(f"Using cached data with {len(cached_data)} coins")
                return cached_data

        if not market_data:
            logger.error("No valid coin data after fetching all pages")
            raise ValueError("No valid coin data in API response")

        # Cache results
        cache.set('market_data', market_data, timeout=3600)
        cache.set('market_data_timestamp', time.time(), timeout=3600)
        cache.set('market_data_last_call', time.time(), timeout=3600)

        logger.info(f"Fetched {len(market_data)} coins successfully")
        return market_data

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error: {e.response.status_code} - {e}")
        return cached_data if cached_data and len(cached_data) >= min_coins else _get_fallback_data('fetch_market_data')
    except Exception as e:
        logger.error(f"Unexpected error fetching market data: {e}", exc_info=True)
        return cached_data if cached_data and len(cached_data) >= min_coins else _get_fallback_data('fetch_market_data')

@adaptive_rate_limit_handler(max_retries=2, base_delay=10)
def fetch_valid_coins() -> List[str]:
    """Fetch valid cryptocurrency IDs from CoinGecko"""
    if valid_coins := cache.get('valid_coins'):
        return valid_coins

    try:
        url = ("https://pro-api.coingecko.com/api/v3/coins/list"
               if hasattr(settings, 'COINGECKO_API_KEY') else
               "https://api.coingecko.com/api/v3/coins/list")
        headers = {'x-cg-pro-api-key': settings.COINGECKO_API_KEY} if hasattr(settings, 'COINGECKO_API_KEY') else {}

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        valid_coins = [coin['id'].lower() for coin in response.json() if 'id' in coin]
        cache.set('valid_coins', valid_coins, timeout=86400)
        return valid_coins

    except Exception as e:
        logger.error(f"Error fetching valid coins: {e}", exc_info=True)
        return ['bitcoin', 'ethereum', 'binancecoin', 'cardano', 'solana']

@adaptive_rate_limit_handler(max_retries=2, base_delay=10)
def fetch_news() -> List[Dict]:
    """Fetch cryptocurrency news from NewsAPI"""
    if cached_news := cache.get('crypto_news'):
        if cache_age := cache.get('crypto_news_timestamp'):
            if (time.time() - cache_age) < 1800:
                return cached_news

    try:
        if not hasattr(settings, 'NEWSAPI_KEY'):
            logger.warning("NewsAPI key not configured")
            return []

        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                'q': 'cryptocurrency OR bitcoin OR ethereum',
                'apiKey': settings.NEWSAPI_KEY,
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': 20,
                'from': (datetime.now() - timedelta(days=1)).isoformat()
            },
            timeout=30
        )
        response.raise_for_status()

        articles = response.json().get('articles', [])
        news_data = [
            {
                "title": article["title"],
                "source": article.get("source", {}).get("name", "Unknown"),
                "published_at": article.get("publishedAt", ""),
                "url": article.get("url", ""),
                "description": article.get("description") or "",
                "sentiment": analyze_article_sentiment(
                    article["title"] + " " + (article.get("description") or "")
                )
            }
            for article in articles
            if article.get('title') and article.get('title') != '[Removed]'
        ]

        cache.set('crypto_news', news_data, timeout=1800)
        cache.set('crypto_news_timestamp', time.time(), timeout=1800)
        return news_data

    except Exception as e:
        logger.error(f"Error fetching news: {e}", exc_info=True)
        return cached_news or []

def analyze_article_sentiment(text: str) -> Dict[str, Union[float, str]]:
    """Analyze sentiment of article text using VADER"""
    if not text or len(text.strip()) < 10:
        return {"score": 0.5, "label": "Neutral"}

    try:
        analyzer = SentimentIntensityAnalyzer()
        score = (analyzer.polarity_scores(text)['compound'] + 1) / 2

        label = ("Very Positive" if score > 0.65 else
                 "Positive" if score > 0.55 else
                 "Neutral" if score > 0.45 else
                 "Negative" if score > 0.35 else
                 "Very Negative")

        return {"score": round(score, 3), "label": label}
    except Exception as e:
        logger.error(f"Error analyzing sentiment: {e}", exc_info=True)
        return {"score": 0.5, "label": "Neutral"}

@adaptive_rate_limit_handler(max_retries=2, base_delay=10)
def fetch_sentiment() -> Dict[str, Union[float, str, int]]:
    """Calculate overall market sentiment based on news articles"""
    if cached_sentiment := cache.get('crypto_sentiment'):
        if cache_age := cache.get('crypto_sentiment_timestamp'):
            if (time.time() - cache_age) < 600:
                return cached_sentiment

    try:
        news = fetch_news()
        if not news:
            return {"score": 0.5, "label": "Neutral", "article_count": 0}

        total_weight, weighted_score = 0, 0
        for article in news:
            try:
                pub_time = datetime.fromisoformat(article['published_at'].replace('Z', '+00:00'))
                hours_old = (datetime.now(pub_time.tzinfo) - pub_time).total_seconds() / 3600
                weight = max(0.1, 1 - (hours_old / 24))
            except:
                weight = 0.5

            weighted_score += article['sentiment']['score'] * weight
            total_weight += weight

        avg_score = weighted_score / total_weight if total_weight > 0 else 0.5
        label = ("Very Positive" if avg_score > 0.65 else
                 "Positive" if avg_score > 0.55 else
                 "Neutral" if avg_score > 0.45 else
                 "Negative" if avg_score > 0.35 else
                 "Very Negative")

        sentiment_data = {
            "score": round(avg_score, 3),
            "label": label,
            "article_count": len(news),
            "updated_at": datetime.now().isoformat()
        }

        cache.set('crypto_sentiment', sentiment_data, timeout=600)
        cache.set('crypto_sentiment_timestamp', time.time(), timeout=600)
        return sentiment_data

    except Exception as e:
        logger.error(f"Error computing sentiment: {e}", exc_info=True)
        return {"score": 0.5, "label": "Neutral", "article_count": 0}

def get_api_status() -> Dict:
    """Get current status of all APIs"""
    status = {
        'coingecko': {'rate_limited': False, 'last_call': None, 'cache_age': None, 'using_real_data': True},
        'newsapi': {'rate_limited': False, 'last_call': None, 'cache_age': None}
    }

    for key, api in [('market_data', 'coingecko'), ('crypto_news', 'newsapi')]:
        if timestamp := cache.get(f'{key}_timestamp'):
            status[api]['cache_age'] = time.time() - timestamp
        status[api]['rate_limited'] = bool(cache.get(f'rate_limit:fetch_{key}'))
        status[api]['last_call'] = cache.get(f'{key}_last_call')

    if market_data := cache.get('market_data'):
        status['coingecko']['using_real_data'] = not any(
            coin.get('last_updated') == 'EMERGENCY_DATA' or coin.get('usd', 1) == 0
            for coin in market_data.values()
        )

    return status

def clear_all_caches() -> None:
    """Clear all cached data and rate limits"""
    cache_keys = [
        'market_data', 'market_data_timestamp', 'valid_coins', 'crypto_news',
        'crypto_news_timestamp', 'crypto_sentiment', 'crypto_sentiment_timestamp',
        'market_data_last_call', 'service_spin_up'
    ]
    for func in ['fetch_market_data', 'fetch_news', 'fetch_sentiment', 'fetch_valid_coins']:
        cache_keys.extend([f'lock:{func}', f'{func}_cache', f'{func}_cache_timestamp'])

    cache.delete_many(cache_keys)
    logger.info(f"Cleared {len(cache_keys)} cache keys")

class APIMonitor:
    """Utility class for monitoring API usage and health"""

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"

    @staticmethod
    def get_detailed_status() -> Dict:
        """Get comprehensive API status information"""
        now = time.time()
        status = {
            'timestamp': datetime.now().isoformat(),
            'cache_status': {},
            'rate_limits': {},
            'api_health': {},
            'data_quality': {},
            'recommendations': []
        }

        # Cache status
        caches = {
            'market_data': {'key': 'market_data', 'timestamp_key': 'market_data_timestamp'},
            'news': {'key': 'crypto_news', 'timestamp_key': 'crypto_news_timestamp'},
            'sentiment': {'key': 'crypto_sentiment', 'timestamp_key': 'crypto_sentiment_timestamp'},
            'valid_coins': {'key': 'valid_coins', 'timestamp_key': None}
        }

        for name, info in caches.items():
            data = cache.get(info['key'])
            timestamp = cache.get(info['timestamp_key']) if info['timestamp_key'] else None
            cache_info = {
                'exists': data is not None,
                'size': len(data) if data else 0,
                'age_seconds': time.time() - timestamp if timestamp else None,
                'age_human': APIMonitor._format_duration(time.time() - timestamp) if timestamp else None
            }
            status['cache_status'][name] = cache_info

        # Data quality
        if market_data := cache.get('market_data'):
            quality_check = {
                'total_coins': len(market_data),
                'using_real_data': True,
                'zero_prices': sum(1 for coin in market_data.values() if coin.get('usd', 0) == 0),
                'emergency_data': any(coin.get('last_updated') == 'EMERGENCY_DATA' for coin in market_data.values())
            }
            quality_check['zero_price_percentage'] = (quality_check['zero_prices'] / quality_check['total_coins'] * 100
                                                    if quality_check['total_coins'] > 0 else 0)
            quality_check['using_real_data'] = not quality_check['emergency_data']
            status['data_quality']['market_data'] = quality_check

        # Rate limits
        for func in ['fetch_market_data', 'fetch_news', 'fetch_sentiment']:
            limit_until = cache.get(f'rate_limit:{func}')
            status['rate_limits'][func] = {
                'active': bool(limit_until and limit_until > now),
                'remaining_seconds': max(0, limit_until - now) if limit_until else 0,
                'remaining_human': APIMonitor._format_duration(max(0, limit_until - now)) if limit_until and limit_until > now else None
            }

        # API health
        for api, key in [('market_data', 'market_data_last_call'), ('news', 'crypto_news_timestamp')]:
            health = {'status': 'unknown', 'last_successful': None}
            if last_call := cache.get(key):
                age = now - last_call
                health['last_successful'] = APIMonitor._format_duration(age) + ' ago'
                health['status'] = ('healthy' if age < 300 else
                                   'stale' if age < 1800 else
                                   'outdated')
            status['api_health'][api] = health

        status['recommendations'] = APIMonitor._generate_recommendations(status)
        return status

    @staticmethod
    def _generate_recommendations(status: Dict) -> List[Dict]:
        """Generate recommendations based on API status"""
        recommendations = []

        if quality := status['data_quality'].get('market_data', {}):
            if quality.get('emergency_data'):
                recommendations.append({
                    'type': 'critical',
                    'message': "Using emergency hardcoded data",
                    'action': "Check API connectivity and keys"
                })
            elif quality.get('zero_price_percentage', 0) > 50:
                recommendations.append({
                    'type': 'error',
                    'message': f"{quality['zero_price_percentage']:.1f}% of coins have zero prices",
                    'action': "Investigate API data validity"
                })

        if active_limits := [k for k, v in status['rate_limits'].items() if v.get('active')]:
            recommendations.append({
                'type': 'warning',
                'message': f"Active rate limits: {', '.join(active_limits)}",
                'action': "Wait for rate limits to expire"
            })

        for name, cache_info in status['cache_status'].items():
            if not cache_info['exists']:
                recommendations.append({
                    'type': 'error',
                    'message': f"No cached data for {name}",
                    'action': f"Trigger {name} fetch"
                })
            elif name == 'market_data' and cache_info['age_seconds'] and cache_info['age_seconds'] > 300:
                recommendations.append({
                    'type': 'warning',
                    'message': f"Stale market data cache ({cache_info['age_human']})",
                    'action': "Refresh market data cache"
                })
            elif cache_info['age_seconds'] and cache_info['age_seconds'] > 3600:
                recommendations.append({
                    'type': 'warning',
                    'message': f"Stale cache for {name} ({cache_info['age_human']})",
                    'action': "Refresh cache"
                })

        for api, health in status['api_health'].items():
            if health['status'] == 'outdated':
                recommendations.append({
                    'type': 'error',
                    'message': f"{api} API appears to be failing",
                    'action': "Check API keys and connectivity"
                })

        if not recommendations:
            recommendations.append({
                'type': 'success',
                'message': "All systems functioning normally",
                'action': None
            })

        return recommendations

    @staticmethod
    def log_status() -> Dict:
        """Log detailed API status"""
        status = APIMonitor.get_detailed_status()
        logger.info(f"=== API STATUS REPORT ===\nGenerated at: {status['timestamp']}")

        if quality := status.get('data_quality', {}).get('market_data', {}):
            logger.info(f"Data Quality:\n  Market data: {quality['total_coins']} coins\n"
                        f"  Using real data: {'YES' if quality['using_real_data'] else 'NO'}\n"
                        f"  Zero prices: {quality['zero_prices']} ({quality['zero_price_percentage']:.1f}%)")
            if quality['emergency_data']:
                logger.critical("  ⚠️ EMERGENCY HARDCODED DATA IN USE")

        logger.info("Cache Status:")
        for name, info in status['cache_status'].items():
            age_info = f" (age: {info['age_human']})" if info['age_human'] else ""
            logger.info(f"  {name}: {info['size']} items{age_info}")

        logger.info("Rate Limits:")
        active_limits = [k for k, v in status['rate_limits'].items() if v.get('active')]
        if active_limits:
            for api in active_limits:
                logger.warning(f"  {api}: ACTIVE ({status['rate_limits'][api]['remaining_human']} remaining)")
        else:
            logger.info("  No active rate limits")

        logger.info("API Health:")
        status_icon = {"healthy": "✓", "stale": "⚠", "outdated": "✗", "unknown": "?"}
        for api, health in status['api_health'].items():
            logger.info(f"  {api}: {status_icon.get(health['status'], '?')} {health['status']} "
                        f"(last: {health['last_successful'] or 'never'})")

        logger.info("Recommendations:")
        for rec in status['recommendations']:
            level = {"success": logging.INFO, "warning": logging.WARNING,
                     "error": logging.ERROR, "critical": logging.CRITICAL}
            action = f" → {rec['action']}" if rec['action'] else ""
            logger.log(level.get(rec['type'], logging.INFO), f"  {rec['message']}{action}")

        logger.info("========================")
        return status

def debug_cache_contents() -> None:
    """Print detailed cache contents for debugging"""
    logger.info("=== CACHE DEBUG INFO ===")
    cache_keys = [
        'market_data', 'market_data_timestamp', 'valid_coins', 'crypto_news',
        'crypto_news_timestamp', 'crypto_sentiment', 'crypto_sentiment_timestamp',
        'market_data_last_call', 'service_spin_up'
    ]

    for key in cache_keys:
        if value := cache.get(key):
            if isinstance(value, (dict, list)):
                logger.info(f"{key}: {type(value).__name__} with {len(value)} items")
                if key == 'market_data' and isinstance(value, dict):
                    for coin_id, coin_data in list(value.items())[:5]:
                        logger.info(f"  Sample: {coin_id} = ${coin_data.get('usd', 'N/A')} "
                                    f"{'(EMERGENCY!)' if coin_data.get('last_updated') == 'EMERGENCY_DATA' else '(real)'}")
            elif isinstance(value, (int, float)):
                age = time.time() - value if 'timestamp' in key else None
                logger.info(f"{key}: {value}{' (' + APIMonitor._format_duration(age) + ' ago)' if age else ''}")
            else:
                logger.info(f"{key}: {type(value).__name__} = {str(value)[:100]}")
        else:
            logger.info(f"{key}: None")
    logger.info("========================")

def emergency_reset() -> bool:
    """Emergency reset of all caches and locks"""
    logger.warning("EMERGENCY RESET: Clearing all caches and locks")
    cache_keys = [
        'market_data', 'market_data_timestamp', 'valid_coins', 'crypto_news',
        'crypto_news_timestamp', 'crypto_sentiment', 'crypto_sentiment_timestamp',
        'market_data_last_call', 'service_spin_up'
    ]
    for func in ['fetch_market_data', 'fetch_news', 'fetch_sentiment', 'fetch_valid_coins']:
        cache_keys.extend([f'rate_limit:{func}', f'lock:{func}', f'{func}_cache', f'{func}_cache_timestamp'])

    try:
        cache.delete_many(cache_keys)
        logger.info(f"Emergency reset complete: cleared {len(cache_keys)} cache keys")
        return True
    except Exception as e:
        logger.error(f"Emergency reset failed: {e}")
        return False

def health_check() -> Dict:
    """Perform comprehensive system health check"""
    results = {
        'timestamp': datetime.now().isoformat(),
        'cache_backend': 'unknown',
        'redis_available': False,
        'api_keys_configured': {},
        'cache_connectivity': False,
        'api_connectivity': {},
        'data_quality': {},
        'overall_health': 'unknown'
    }

    # Cache backend check
    try:
        cache_info = str(cache.__class__).lower()
        results['cache_backend'] = 'Redis' if 'redis' in cache_info else 'LocalMemory'
        results['redis_available'] = 'redis' in cache_info

        test_key = f'health_check_{int(time.time())}'
        cache.set(test_key, 'test_value', 30)
        results['cache_connectivity'] = cache.get(test_key) == 'test_value'
        cache.delete(test_key)
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        results['cache_connectivity'] = False

    # API key check
    results['api_keys_configured'] = {
        'coingecko': bool(hasattr(settings, 'COINGECKO_API_KEY') and settings.COINGECKO_API_KEY),
        'newsapi': bool(hasattr(settings, 'NEWSAPI_KEY') and settings.NEWSAPI_KEY)
    }

    # API connectivity check
    try:
        for api, url in [('coingecko', 'https://api.coingecko.com/api/v3/ping'),
                         ('newsapi', 'https://newsapi.org')]:
            try:
                response = requests.get(url, timeout=10)
                results['api_connectivity'][api] = {
                    'status': response.status_code in ([200] if api == 'coingecko' else [200, 401, 403]),
                    'response_time': response.elapsed.total_seconds()
                }
            except Exception as e:
                results['api_connectivity'][api] = {'status': False, 'error': str(e)}
    except ImportError:
        results['api_connectivity'] = {'error': 'requests_unavailable'}

    # Data quality check
    if market_data := cache.get('market_data'):
        quality_check = {
            'total_coins': len(market_data),
            'using_real_data': True,
            'zero_prices': 0,
            'emergency_data': False,
            'valid_prices': 0
        }
        for coin_data in market_data.values():
            price = coin_data.get('usd', 0)
            if price == 0:
                quality_check['zero_prices'] += 1
            else:
                quality_check['valid_prices'] += 1
            if coin_data.get('last_updated') == 'EMERGENCY_DATA':
                quality_check['emergency_data'] = True
                quality_check['using_real_data'] = False
        quality_check['valid_price_percentage'] = (quality_check['valid_prices'] / quality_check['total_coins'] * 100
                                                 if quality_check['total_coins'] > 0 else 0)
        results['data_quality']['market_data'] = quality_check

    # Overall health assessment
    cache_ok = results['cache_connectivity']
    apis_ok = all(api.get('status', False) for api in results['api_connectivity'].values())
    keys_ok = any(results['api_keys_configured'].values())
    data_ok = results['data_quality'].get('market_data', {}).get('using_real_data', True)

    results['overall_health'] = (
        'excellent' if cache_ok and apis_ok and keys_ok and data_ok else
        'good' if cache_ok and (apis_ok or keys_ok) and data_ok else
        'fair' if cache_ok and data_ok else
        'poor' if cache_ok else
        'critical'
    )

    logger.info(f"Health check complete: {results['overall_health']}")
    return results

def check_rate_limits() -> Dict:
    """Check current rate limit status"""
    now = time.time()
    limits = {}
    for func in ['fetch_market_data', 'fetch_news', 'fetch_sentiment']:
        limit_key = f'rate_limit:{func}'
        limit_until = cache.get(limit_key)
        limits[func] = {
            'limited': bool(limit_until and limit_until > now),
            'remaining_seconds': max(0, limit_until - now) if limit_until else 0,
            'remaining_human': APIMonitor._format_duration(max(0, limit_until - now)) if limit_until and limit_until > now else None
        }
    return limits

def clear_rate_limits() -> None:
    """Clear all active rate limits"""
    logger.warning("Clearing all active rate limits")
    cache.delete_many([f'rate_limit:fetch_{func}' for func in ['market_data', 'news', 'sentiment']])
    logger.info("Rate limits cleared")

def simulate_api_failure(api_name: str, duration_minutes: int = 5) -> bool:
    """Simulate API failure for testing (DEBUG mode only)"""
    if not settings.DEBUG:
        logger.error("simulate_api_failure requires DEBUG mode")
        return False

    logger.warning(f"Simulating {api_name} API failure for {duration_minutes} minutes")
    cache.set(f'rate_limit:fetch_{api_name}', time.time() + (duration_minutes * 60), timeout=duration_minutes * 60 + 60)
    return True

def force_cache_refresh(api_name: Optional[str] = None) -> Dict:
    """Force refresh of cached data"""
    results = {}

    if not api_name or api_name == 'all':
        clear_all_caches()
        targets = ['market_data', 'news', 'sentiment']
    else:
        targets = [api_name]

    for target in targets:
        cache.delete_many([f'{target}', f'{target}_timestamp', f'{target}_last_call',
                          f'fetch_{target}_cache', f'fetch_{target}_cache_timestamp'])
        try:
            result = globals()[f'fetch_{target}']()
            results[target] = {
                'success': result is not None,
                'count': len(result) if result else 0,
                'using_real_data': not any(coin.get('last_updated') == 'EMERGENCY_DATA'
                                         for coin in (result or {}).values()) if target == 'market_data' else True
            }
        except Exception as e:
            logger.error(f"Failed to refresh {target}: {e}")
            results[target] = {'success': False, 'error': str(e)}

    return results

def get_performance_metrics() -> Dict:
    """Get performance metrics for API calls and caching"""
    metrics = {
        'timestamp': datetime.now().isoformat(),
        'cache_sizes': {},
        'data_quality': {}
    }

    for key in ['market_data', 'crypto_news', 'valid_coins', 'crypto_sentiment']:
        data = cache.get(key)
        metrics['cache_sizes'][key] = len(data) if data else 0

    if market_data := cache.get('market_data'):
        total_coins = len(market_data)
        valid_prices = sum(1 for coin in market_data.values() if coin.get('usd', 0) > 0)
        metrics['data_quality']['market_data'] = {
            'total_coins': total_coins,
            'valid_prices': valid_prices,
            'valid_percentage': (valid_prices / total_coins * 100) if total_coins > 0 else 0,
            'using_emergency_data': any(coin.get('last_updated') == 'EMERGENCY_DATA' for coin in market_data.values())
        }

    for ts_key in ['market_data_timestamp', 'crypto_news_timestamp', 'crypto_sentiment_timestamp']:
        if timestamp := cache.get(ts_key):
            age = time.time() - timestamp
            cache_name = ts_key.replace('_timestamp', '')
            metrics[f'{cache_name}_age'] = {
                'seconds': age,
                'human': APIMonitor._format_duration(age)
            }

    return metrics

try:
    from django.core.management.base import BaseCommand

    class Command(BaseCommand):
        """Django management command for API monitoring"""
        help = 'Monitor API status and cache health'

        def add_arguments(self, parser):
            parser.add_argument('--format', choices=['text', 'json'], default='text')
            parser.add_argument('--clear-cache', action='store_true')
            parser.add_argument('--clear-limits', action='store_true')
            parser.add_argument('--test-apis', action='store_true')
            parser.add_argument('--health-check', action='store_true')
            parser.add_argument('--emergency-reset', action='store_true')
            parser.add_argument('--force-refresh', choices=['market_data', 'news', 'sentiment', 'all'])
            parser.add_argument('--verify-real-data', action='store_true')

        def handle(self, *args, **options):
            if options['emergency_reset']:
                self.stdout.write(self.style.WARNING("Performing emergency reset..."))
                self.stdout.write(self.style.SUCCESS("Emergency reset completed") if emergency_reset()
                               else self.style.ERROR("Emergency reset failed"))
                return

            if options['clear_cache']:
                clear_all_caches()
                self.stdout.write(self.style.SUCCESS("Caches cleared"))

            if options['clear_limits']:
                clear_rate_limits()
                self.stdout.write(self.style.SUCCESS("Rate limits cleared"))

            if options['force_refresh']:
                refresh_target = options['force_refresh']
                result = force_cache_refresh(refresh_target)
                if refresh_target == 'all':
                    for api, info in result.items():
                        status = (f"✓ {info.get('count', 'N/A')} items"
                                  f" ({'REAL' if info.get('using_real_data', True) else 'EMERGENCY'} data)"
                                  if info['success'] else f"✗ {info.get('error', 'Failed')}")
                        color = self.style.SUCCESS if info['success'] else self.style.ERROR
                        self.stdout.write(f"  {api}: {color(status)}")
                else:
                    status = f"✓ Successfully refreshed {refresh_target}" if result[refresh_target]['success'] else f"✗ Failed to refresh {refresh_target}"
                    color = self.style.SUCCESS if result[refresh_target]['success'] else self.style.ERROR
                    self.stdout.write(color(status))

            if options['verify_real_data']:
                self.verify_real_data()
                return

            if options['health_check']:
                health_results = health_check()
                self.stdout.write(json.dumps(health_results, indent=2) if options['format'] == 'json'
                                else self.display_health_results(health_results))
                return

            if options['test_apis']:
                self.test_api_connectivity()

            status = APIMonitor.get_detailed_status()
            self.stdout.write(json.dumps(status, indent=2) if options['format'] == 'json'
                            else self.display_text_status(status))

        def verify_real_data(self):
            """Verify cached data contains real prices"""
            self.stdout.write(self.style.HTTP_INFO("=== REAL DATA VERIFICATION ==="))
            if not (market_data := cache.get('market_data')):
                self.stdout.write(self.style.ERROR("No market data in cache"))
                return

            total_coins = len(market_data)
            valid_prices = sum(1 for coin in market_data.values() if coin.get('usd', 0) > 0)
            zero_prices = sum(1 for coin in market_data.values() if coin.get('usd', 0) == 0)
            emergency_data = any(coin.get('last_updated') == 'EMERGENCY_DATA' for coin in market_data.values())
            sample_prices = [(coin_id, coin_data['usd']) for coin_id, coin_data in list(market_data.items())[:5] if coin_data.get('usd', 0) > 0]

            self.stdout.write(f"Total coins: {total_coins}\n"
                             f"Valid prices: {self.style.SUCCESS(str(valid_prices))} ({(valid_prices/total_coins)*100:.1f}%)\n"
                             f"Zero prices: {self.style.WARNING(str(zero_prices))} ({(zero_prices/total_coins)*100:.1f}%)\n"
                             f"Emergency data: {self.style.ERROR('YES - Using hardcoded defaults!') if emergency_data else self.style.SUCCESS('NO - Using real API data')}")

            if sample_prices:
                self.stdout.write("\nSample real prices:")
                for coin_id, price in sample_prices:
                    self.stdout.write(f"  {coin_id}: ${price:,.6f}")

            assessment = (
                self.style.ERROR('CRITICAL - Using emergency hardcoded data') if emergency_data else
                self.style.SUCCESS('EXCELLENT - Using real market data') if valid_prices / total_coins > 0.9 else
                self.style.WARNING('FAIR - Some invalid prices detected') if valid_prices / total_coins > 0.7 else
                self.style.ERROR('POOR - Many invalid prices')
            )
            self.stdout.write(f"\nAssessment: {assessment}")

        def display_health_results(self, results):
            """Display health check results in text format"""
            self.stdout.write(f"Health check complete: {results['overall_health']}\n"
                             f"Cache backend: {results['cache_backend']} (connected: {results['cache_connectivity']})\n"
                             f"API keys: {results['api_keys_configured']}\n"
                             f"API connectivity: {results['api_connectivity']}")
            if quality := results['data_quality'].get('market_data'):
                self.stdout.write(f"Data quality: {quality['valid_prices']}/{quality['total_coins']} coins "
                                 f"({quality['valid_price_percentage']:.1f}%)")

        def display_text_status(self, status):
            """Display status in text format"""
            APIMonitor.log_status()

        def test_api_connectivity(self):
            """Test API connectivity"""
            results = health_check()['api_connectivity']
            for api, info in results.items():
                status = f"✓ Connected ({info['response_time']:.2f}s)" if info.get('status') else f"✗ Failed ({info.get('error', 'Unknown error')})"
                color = self.style.SUCCESS if info.get('status') else self.style.ERROR
                self.stdout.write(f"{api}: {color(status)}")
except ImportError:
    pass
