import requests
from django.conf import settings
from tracker.models import CryptoPrice
from celery import shared_task

@shared_task
def fetch_crypto_prices():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        'ids': 'bitcoin,ethereum',  # Add more cryptocurrencies as needed
        'vs_currencies': 'usd',
        'x_cg_demo_api_key': settings.COINGECKO_API_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()

    for crypto, info in data.items():
        CryptoPrice.objects.create(
            cryptocurrency=crypto,
            price_usd=info['usd']
        )