from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class CryptoPrice(models.Model):
    cryptocurrency = models.CharField(max_length=100)
    price_usd = models.DecimalField(max_digits=20, decimal_places=2, null=True)
    usd_24h_change = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    usd_market_cap = models.DecimalField(max_digits=20, decimal_places=2, null=True)
    usd_24h_vol = models.DecimalField(max_digits=20, decimal_places=2, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['cryptocurrency', 'timestamp']),
        ]

class Portfolio(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    cryptocurrency = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    purchase_price = models.DecimalField(max_digits=20, decimal_places=2)

    class Meta:
        unique_together = ('user', 'cryptocurrency')  # Ensure uniqueness for user-cryptocurrency pair

    def __str__(self):
        return f"{self.user.username} - {self.cryptocurrency}"

class Watchlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    cryptocurrency = models.CharField(max_length=100)

class Alert(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    cryptocurrency = models.CharField(max_length=100)
    target_price = models.DecimalField(max_digits=20, decimal_places=2)
    condition = models.CharField(max_length=10, choices=[('above', 'Above'), ('below', 'Below')])
    is_active = models.BooleanField(default=True)