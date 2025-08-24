from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import (
    HealthCheckView, ReadinessCheckView,
    home, dashboard, portfolio, add_to_portfolio, edit_asset, remove_asset,
    watchlist, add_to_watchlist, alerts, add_alert, technical,
    custom_login, custom_logout, register, profile, settings,
    search, about, contact, terms, privacy, news, live_charts,
    market_data_api, alerts_api, clear_cache
)

urlpatterns = [
    # Health check endpoints
    path('health/', HealthCheckView.as_view(), name='health_check'),
    path('ready/', ReadinessCheckView.as_view(), name='readiness_check'),

    # Main pages
    path('', home, name='home'),
    path('dashboard/', dashboard, name='dashboard'),

    # Portfolio management
    path('portfolio/', portfolio, name='portfolio'),
    path('portfolio/add/', add_to_portfolio, name='add_to_portfolio'),
    path('portfolio/edit/<str:cryptocurrency>/', edit_asset, name='edit_asset'),
    path('portfolio/remove/<str:cryptocurrency>/', remove_asset, name='remove_asset'),

    # Watchlist
    path('watchlist/', watchlist, name='watchlist'),
    path('watchlist/add/', add_to_watchlist, name='add_to_watchlist'),

    # Alerts
    path('alerts/', alerts, name='alerts'),
    path('alerts/add/', add_alert, name='add_alert'),
    path('api/alerts/', alerts_api, name='alerts_api'),

    # Analysis
    path('technical/', technical, name='technical'),
    path('news/', news, name='news'),
    path('live-charts/', live_charts, name='live_charts'),

    # Authentication
    path('login/', custom_login, name='login'),
    path('logout/', custom_logout, name='logout'),
    path('register/', register, name='register'),

    # User management
    path('profile/', profile, name='profile'),
    path('settings/', settings, name='settings'),

    # Utility pages
    path('search/', search, name='search'),
    path('about/', about, name='about'),
    path('contact/', contact, name='contact'),
    path('terms/', terms, name='terms'),
    path('privacy/', privacy, name='privacy'),

    # API endpoints
    path('api/market-data/', market_data_api, name='market_data_api'),

    # Admin utilities
    path('clear-cache/', clear_cache, name='clear_cache'),

    # Password reset URLs (using Django's built-in views)
    path('password_reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset.html'
    ), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html'
    ), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html'
    ), name='password_reset_complete'),
]
