import logging
import time
from typing import Dict, Optional
from functools import wraps
import json

import requests
from django.core.cache import cache
from django.conf import settings
from django.http import HttpResponseForbidden

# Explicitly configure logging to avoid 'logger not defined'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
    cached_data = cache.get('market_data')
    cache_age = cache.get('market_data_timestamp')

    if cached_data and cache_age and (time.time() - cache_age) < 300 and len(cached_data) >= min_coins:
        logger.info(f"Using fresh market data cache ({(time.time() - cache_age)/60:.1f}m old, {len(cached_data)} coins)")
        return cached_data

    if last_call := cache.get('market_data_last_call'):
        if (time.time() - last_call) < 10:
            logger.info(f"Recent API call detected, using cached data with {len(cached_data or {})} coins")
            if cached_data and len(cached_data) >= min_coins:
                return cached_data
            logger.warning(f"Cached data has only {len(cached_data or {})} coins, attempting fresh fetch")

    if rate_limit_until := cache.get('rate_limit:fetch_market_data'):
        if time.time() < rate_limit_until:
            logger.warning(f"Rate limited for {(rate_limit_until - time.time()):.1f}s, using cached data")
            if cached_data and len(cached_data) >= min_coins:
                return cached_data
            logger.warning(f"Cached data has only {len(cached_data or {})} coins, returning fallback")
            return _get_fallback_data('fetch_market_data')

    market_data = {}
    page = 1
    max_pages = 3

    try:
        while len(market_data) < min_coins and page <= max_pages:
            url = ("https://pro-api.coingecko.com/api/v3/coins/markets"
                   if hasattr(settings, 'COINGECKO_API_KEY') and settings.COINGECKO_API_KEY
                   else "https://api.coingecko.com/api/v3/coins/markets")
            headers = {'x-cg-pro-api-key': settings.COINGECKO_API_KEY} if hasattr(settings, 'COINGECKO_API_KEY') else {}
            params = {
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': 50,
                'page': page,
                'sparkline': 'false',
                'price_change_percentage': '24h'
            }

            logger.info(f"Fetching market data from {url}, page {page} (diagnostic_mode={diagnostic_mode})")
            response = requests.get(url, headers=headers, params=params, timeout=30)

            logger.info(f"API response: {response.status_code}, "
                       f"Rate limit remaining: {response.headers.get('X-RateLimit-Remaining', 'N/A')}")
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
            time.sleep(1)

        if len(market_data) < min_coins:
            logger.warning(f"Only retrieved {len(market_data)} coins, below target of {min_coins}")
            if cached_data and len(cached_data) >= min_coins:
                logger.info(f"Using cached data with {len(cached_data)} coins")
                return cached_data

        if not market_data:
            logger.error("No valid coin data after fetching all pages")
            raise ValueError("No valid coin data in API response")

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

def clear_all_caches() -> None:
    """Clear all cached data and rate limits"""
    cache_keys = [
        'market_data', 'market_data_timestamp', 'market_data_last_call', 'service_spin_up'
    ]
    for func in ['fetch_market_data']:
        cache_keys.extend([f'lock:{func}', f'{func}_cache', f'{func}_cache_timestamp'])

    cache.delete_many(cache_keys)
    logger.info(f"Cleared {len(cache_keys)} cache keys")

def clear_rate_limits() -> None:
    """Clear all active rate limits"""
    logger.warning("Clearing all active rate limits")
    cache.delete_many([f'rate_limit:fetch_{func}' for func in ['market_data']])
    logger.info("Rate limits cleared")
