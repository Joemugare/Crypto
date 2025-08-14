# tracker/utils.py
import requests
from django.core.cache import cache
from datetime import datetime, timedelta

def fetch_market_data():
    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1&sparkline=false"
        )
        response.raise_for_status()
        data = response.json()
        return {
            coin['id']: {
                "usd": coin['current_price'],
                "usd_24h_change": coin['price_change_percentage_24h'],
                "volume_24h": coin['total_volume'],
                "sentiment": "Neutral"  # Placeholder
            } for coin in data
        }
    except requests.RequestException:
        return {}

def fetch_news():
    try:
        # Replace 'YOUR_NEWSAPI_KEY' with your actual NewsAPI key
        api_key = "7e82ca805a4a46cbacee1c77a36c9028"  # <--- Replace with your NewsAPI key
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
    # Placeholder: Simple keyword-based sentiment analysis
    positive_keywords = ["bullish", "surge", "rise", "gain", "success", "growth"]
    negative_keywords = ["bearish", "drop", "fall", "crash", "loss", "decline"]
    text = text.lower()
    score = 0.5  # Neutral
    if any(keyword in text for keyword in positive_keywords):
        score = 0.7
    elif any(keyword in text for keyword in negative_keywords):
        score = 0.3
    label = "Positive" if score > 0.6 else "Negative" if score < 0.4 else "Neutral"
    return {"score": score, "label": label}

def fetch_sentiment():
    try:
        # Placeholder: Replace with a real sentiment API if available
        response = requests.get("https://api.sentiment.io/v1/crypto-sentiment")
        response.raise_for_status()
        data = response.json()
        score = data.get("score", 0.5)
        label = "Positive" if score > 0.6 else "Negative" if score < 0.4 else "Neutral"
        return {"score": score, "label": label}
    except requests.RequestException:
        return {"score": 0.5, "label": "Neutral"}