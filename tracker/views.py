from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.core.cache import cache
from django.views import View
from decimal import Decimal
import requests
import logging
import time
from .models import Portfolio, Watchlist, Alert, CryptoPrice
from .utils import fetch_market_data, fetch_valid_coins, fetch_news, fetch_sentiment

logger = logging.getLogger(__name__)

def home(request):
    try:
        market_data = cache.get('market_data') or fetch_market_data() or {}
        formatted_data = {}
        for coin_id, data in market_data.items():
            formatted_data[coin_id] = {
                'usd': data['usd'],
                'usd_24h_change': data['usd_24h_change'],
                'volume_24h': data['volume_24h'],
                'sentiment': data.get('sentiment', 'Neutral'),
                'name': ' '.join(word.capitalize() for word in coin_id.replace('_', ' ').split())
            }
        cache.set('market_data', formatted_data, timeout=3600)  # Cache for 1 hour
    except Exception as e:
        logger.error(f"Error in home view: {e}")
        formatted_data = {}
        messages.error(request, "Failed to fetch market data. Please try again later.")
    return render(request, "home.html", {
        "market_data": formatted_data,
        "is_data_live": bool(formatted_data)
    })

@login_required
def dashboard(request):
    market_data = cache.get('market_data') or fetch_market_data() or {}
    cache.set('market_data', market_data, timeout=3600)
    price_map = {coin: Decimal(str(data["usd"])) for coin, data in market_data.items()}

    portfolio_qs = Portfolio.objects.filter(user=request.user)
    portfolio_empty = not portfolio_qs.exists()

    current_value = sum(p.amount * price_map.get(p.cryptocurrency, Decimal('0.0')) for p in portfolio_qs)
    invested = sum(p.amount * p.purchase_price for p in portfolio_qs)
    profit_loss = current_value - invested

    summary_data = {
        "current_value": current_value,
        "invested": invested,
        "profit_loss": profit_loss
    }

    price_history = CryptoPrice.objects.order_by("-timestamp")[:50]
    chart_data = {
        "labels": [p.timestamp.strftime("%Y-%m-%d %H:%M") for p in price_history],
        "values": [float(p.price_usd) for p in price_history]
    }

    portfolio_labels = [p.cryptocurrency.capitalize() for p in portfolio_qs]
    portfolio_values = [float(p.amount * price_map.get(p.cryptocurrency, Decimal('0.0'))) for p in portfolio_qs]

    return render(request, "dashboard.html", {
        "market_data": market_data,
        "summary_data": summary_data,
        "chart_data": chart_data,
        "portfolio_labels": portfolio_labels,
        "portfolio_values": portfolio_values,
        "portfolio_empty": portfolio_empty,
        "is_data_live": bool(market_data)
    })

@login_required
def portfolio(request):
    market_data = cache.get('market_data') or fetch_market_data() or {}
    cache.set('market_data', market_data, timeout=3600)
    price_map = {coin: Decimal(str(data["usd"])) for coin, data in market_data.items()}

    portfolio_qs = Portfolio.objects.filter(user=request.user)
    # Batch fetch prices for coins not in top 50
    missing_coins = [p.cryptocurrency for p in portfolio_qs if p.cryptocurrency not in price_map]
    if missing_coins:
        for attempt in range(3):
            try:
                coin_ids = ','.join(missing_coins)
                response = requests.get(
                    f"https://api.coingecko.com/api/v3/simple/price?ids={coin_ids}&vs_currencies=usd"
                )
                response.raise_for_status()
                data = response.json()
                for coin in missing_coins:
                    price = data.get(coin, {}).get('usd', 0.0)
                    price_map[coin] = Decimal(str(price))
                logger.info(f"Fetched prices for {len(missing_coins)} missing coins: {missing_coins}")
                break
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    wait_time = 2 ** attempt * 10
                    logger.warning(f"Rate limit hit for batch price fetch. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Error fetching batch prices: {e}")
                    break
            except requests.RequestException as e:
                logger.error(f"Error fetching batch prices: {e}")
                break

    portfolio_data = [{
        "cryptocurrency": p.cryptocurrency,
        "amount": p.amount,
        "purchase_price": p.purchase_price,
        "current_price": price_map.get(p.cryptocurrency, Decimal('0.0')),
        "profit_loss": (price_map.get(p.cryptocurrency, Decimal('0.0')) * p.amount) -
                       (p.purchase_price * p.amount)
    } for p in portfolio_qs]

    return render(request, "portfolio.html", {
        "portfolio": portfolio_data,
        "edit_item": None
    })

@login_required
def add_to_portfolio(request):
    if request.method == "POST":
        cryptocurrency = request.POST.get("cryptocurrency")
        amount = request.POST.get("amount")
        purchase_price = request.POST.get("purchase_price")

        try:
            if not cryptocurrency or not amount or not purchase_price:
                raise ValidationError("All fields are required.")
            amount = Decimal(amount)
            purchase_price = Decimal(purchase_price)
            if amount <= 0 or purchase_price <= 0:
                raise ValidationError("Amount and purchase price must be positive.")
            valid_coins = fetch_valid_coins()
            if not valid_coins:
                logger.warning("Valid coins list empty, skipping validation")
            elif cryptocurrency.lower() not in valid_coins:
                logger.info(f"Invalid cryptocurrency: {cryptocurrency.lower()} not in {valid_coins[:10]}...")
                raise ValidationError("Invalid cryptocurrency.")
        except (ValidationError, ValueError) as e:
            messages.error(request, str(e))
            return redirect("portfolio")

        Portfolio.objects.create(
            user=request.user,
            cryptocurrency=cryptocurrency.lower(),
            amount=amount,
            purchase_price=purchase_price
        )
        messages.success(request, f"Added {cryptocurrency} to portfolio")
        return redirect("portfolio")

    return redirect("portfolio")

@login_required
def edit_asset(request, cryptocurrency):
    portfolio_item = get_object_or_404(Portfolio, user=request.user, cryptocurrency=cryptocurrency.lower())

    if request.method == "POST":
        amount = request.POST.get("amount")
        purchase_price = request.POST.get("purchase_price")

        try:
            if not amount or not purchase_price:
                raise ValidationError("All fields are required.")
            amount = Decimal(amount)
            purchase_price = Decimal(purchase_price)
            if amount <= 0 or purchase_price <= 0:
                raise ValidationError("Amount and purchase price must be positive.")
        except (ValidationError, ValueError) as e:
            messages.error(request, str(e))
            return redirect("portfolio")

        portfolio_item.amount = amount
        portfolio_item.purchase_price = purchase_price
        portfolio_item.save()
        messages.success(request, f"Updated {cryptocurrency} in portfolio")
        return redirect("portfolio")

    market_data = cache.get('market_data') or fetch_market_data() or {}
    cache.set('market_data', market_data, timeout=3600)
    price_map = {coin: Decimal(str(data["usd"])) for coin, data in market_data.items()}
    portfolio_qs = Portfolio.objects.filter(user=request.user)
    portfolio_data = [{
        "cryptocurrency": p.cryptocurrency,
        "amount": p.amount,
        "purchase_price": p.purchase_price,
        "current_price": price_map.get(p.cryptocurrency, Decimal('0.0')),
        "profit_loss": (price_map.get(p.cryptocurrency, Decimal('0.0')) * p.amount) -
                       (p.purchase_price * p.amount)
    } for p in portfolio_qs]

    return render(request, "portfolio.html", {
        "portfolio": portfolio_data,
        "edit_item": portfolio_item
    })

@login_required
def remove_asset(request, cryptocurrency):
    if request.method == "POST":
        portfolio_item = get_object_or_404(Portfolio, user=request.user, cryptocurrency=cryptocurrency.lower())
        portfolio_item.delete()
        messages.success(request, f"Removed {cryptocurrency} from portfolio")
        return redirect("portfolio")
    return redirect("portfolio")

@login_required
def watchlist(request):
    market_data = cache.get('market_data') or fetch_market_data() or {}
    cache.set('market_data', market_data, timeout=3600)
    price_map = {coin: Decimal(str(data["usd"])) for coin, data in market_data.items()}
    watchlist_qs = Watchlist.objects.filter(user=request.user)
    watchlist_data = [{
        "cryptocurrency": w.cryptocurrency,
        "current_price": price_map.get(w.cryptocurrency, Decimal('0.0'))
    } for w in watchlist_qs]
    return render(request, "watchlist.html", {"watchlist": watchlist_data})

@login_required
def add_to_watchlist(request):
    if request.method == "POST":
        cryptocurrency = request.POST.get("cryptocurrency")
        try:
            if not cryptocurrency:
                raise ValidationError("Cryptocurrency is required.")
            valid_coins = fetch_valid_coins()
            if not valid_coins:
                logger.warning("Valid coins list empty, skipping validation")
            elif cryptocurrency.lower() not in valid_coins:
                logger.info(f"Invalid cryptocurrency for watchlist: {cryptocurrency.lower()}")
                raise ValidationError("Invalid cryptocurrency.")
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect("watchlist")

        Watchlist.objects.create(
            user=request.user,
            cryptocurrency=cryptocurrency.lower()
        )
        messages.success(request, f"Added {cryptocurrency} to watchlist")
        return redirect("watchlist")

    return redirect("watchlist")

@login_required
def alerts(request):
    alerts_qs = Alert.objects.filter(user=request.user)
    return render(request, "alerts.html", {"alerts": alerts_qs})

@login_required
def add_alert(request):
    if request.method == "POST":
        cryptocurrency = request.POST.get("cryptocurrency")
        target_price = request.POST.get("target_price")
        condition = request.POST.get("condition")

        try:
            if not cryptocurrency or not target_price or not condition:
                raise ValidationError("All fields are required.")
            target_price = Decimal(target_price)
            if target_price <= 0:
                raise ValidationError("Target price must be positive.")
            valid_coins = fetch_valid_coins()
            if not valid_coins:
                logger.warning("Valid coins list empty, skipping validation")
            elif cryptocurrency.lower() not in valid_coins:
                logger.info(f"Invalid cryptocurrency for alert: {cryptocurrency.lower()}")
                raise ValidationError("Invalid cryptocurrency.")
            if condition not in ["above", "below"]:
                raise ValidationError("Invalid condition.")
        except (ValidationError, ValueError) as e:
            messages.error(request, str(e))
            return redirect("alerts")

        Alert.objects.create(
            user=request.user,
            cryptocurrency=cryptocurrency.lower(),
            target_price=target_price,
            condition=condition
        )
        messages.success(request, f"Alert set for {cryptocurrency}")
        return redirect("alerts")

    return redirect("alerts")

@login_required
def technical(request):
    price_history = CryptoPrice.objects.order_by("-timestamp")[:50]
    chart_data = {
        "labels": [p.timestamp.strftime("%Y-%m-%d %H:%M") for p in price_history],
        "values": [float(p.price_usd) for p in price_history]
    }
    return render(request, "technical.html", {"chart_data": chart_data})

def custom_login(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "Logged in successfully!")
            return redirect("dashboard")
        messages.error(request, "Invalid credentials")
        return render(request, "registration/login.html", {"form": form})
    return render(request, "registration/login.html", {"form": AuthenticationForm()})

def custom_logout(request):
    logout(request)
    messages.success(request, "Logged out successfully!")
    return redirect("home")

def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account created successfully! Please log in.")
            return redirect("login")
        messages.error(request, "Please correct the errors below.")
        return render(request, "registration/register.html", {"form": form})
    return render(request, "registration/register.html", {"form": UserCreationForm()})

def profile(request):
    return render(request, 'profile.html', {'user': request.user})

def settings(request):
    return render(request, 'settings.html')

def search(request):
    query = request.GET.get('q', '')
    market_data = cache.get('market_data') or fetch_market_data() or {}
    cache.set('market_data', market_data, timeout=3600)
    results = {k: v for k, v in market_data.items() if query.lower() in k.lower()}
    return render(request, 'search.html', {'query': query, 'results': results})

def about(request):
    return render(request, 'about.html')

def contact(request):
    return render(request, 'contact.html')

def terms(request):
    return render(request, 'terms.html')

def privacy(request):
    return render(request, 'privacy.html')

def news(request):
    try:
        news_data = fetch_news() or []
    except Exception:
        news_data = []
        messages.error(request, "Failed to fetch news. Please try again later.")
    return render(request, "news.html", {"news_data": news_data})

def live_charts(request):
    market_data = cache.get('market_data') or fetch_market_data() or {}
    cache.set('market_data', market_data, timeout=3600)
    return render(request, "live_charts.html", {"market_data": market_data})

def market_data_api(request):
    try:
        market_data = cache.get('market_data') or fetch_market_data() or {}
        query = request.GET.get('search', '').lower()
        if query:
            valid_coins = fetch_valid_coins()
            if not valid_coins:
                logger.warning("Valid coins list empty, returning empty market data")
                market_data = {}
            else:
                filtered_coins = [coin for coin in valid_coins if query in coin]
                market_data = {
                    coin: market_data.get(coin, {"usd": 0.0, "usd_24h_change": 0.0, "volume_24h": 0.0, "sentiment": "Neutral"})
                    for coin in filtered_coins[:50]
                }
        cache.set('market_data', market_data, timeout=3600)
        sentiment_data = fetch_sentiment() or {"score": 0.5, "label": "Neutral"}
        response = {
            "market_data": market_data,
            "sentiment": sentiment_data
        }
    except Exception as e:
        logger.error(f"Error in market_data_api: {e}")
        response = {"market_data": {}, "sentiment": {"score": 0.5, "label": "Neutral"}}
    return JsonResponse(response)

@login_required
def alerts_api(request):
    try:
        alerts_qs = Alert.objects.filter(user=request.user)
        alerts_data = [{
            "cryptocurrency": alert.cryptocurrency,
            "target_price": float(alert.target_price),
            "condition": alert.condition,
            "created_at": alert.created_at.strftime("%Y-%m-%d %H:%M:%S")
        } for alert in alerts_qs]
        return JsonResponse({"alerts": alerts_data})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def clear_cache(request):
    cache.clear()

    messages.success(request, "Cache cleared successfully!")
    return redirect("home")

# Health Check Views
class HealthCheckView(View):
    """Simple health check endpoint"""
    def get(self, request):
        return JsonResponse({
            'status': 'healthy',
            'timestamp': time.time(),
            'service': 'crypto_tracker'
        })

class ReadinessCheckView(View):
    """Readiness check endpoint"""
    def get(self, request):
        try:
            # Check database connectivity
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            
            # Check cache connectivity
            cache.set('readiness_check', 'ok', timeout=60)
            cache_status = cache.get('readiness_check')
            
            if cache_status != 'ok':
                raise Exception("Cache not accessible")
            
            return JsonResponse({
                'status': 'ready',
                'timestamp': time.time(),
                'checks': {
                    'database': 'ok',
                    'cache': 'ok'
                }
            })
        except Exception as e:
            return JsonResponse({
                'status': 'not ready',
                'error': str(e),
                'timestamp': time.time(),
                'checks': {
                    'database': 'error',
                    'cache': 'error'
                }
            }, status=503)

