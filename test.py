from tracker.models import CryptoPrice
from decimal import Decimal
from django.utils import timezone

CryptoPrice.objects.create(
    cryptocurrency='bitcoin',
    price_usd=Decimal('30000'),
    usd_24h_change=Decimal('1.5'),
    usd_market_cap=Decimal('600000000000'),
    usd_24h_vol=Decimal('25000000000'),
    timestamp=timezone.now()
)
