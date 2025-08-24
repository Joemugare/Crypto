from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('portfolio/', views.portfolio, name='portfolio'),
    path('portfolio/add/', views.add_to_portfolio, name='add_to_portfolio'),
    path('portfolio/edit/<str:cryptocurrency>/', views.edit_asset, name='edit_asset'),  # New
    path('portfolio/remove/<str:cryptocurrency>/', views.remove_asset, name='remove_asset'),  # New
    path('watchlist/', views.watchlist, name='watchlist'),
    path('watchlist/add/', views.add_to_watchlist, name='add_to_watchlist'),
    path('alerts/', views.alerts, name='alerts'),
    path('alerts/add/', views.add_alert, name='add_alert'),
    path('alerts/api/', views.alerts_api, name='alerts_api'),
    path('technical/', views.technical, name='technical'),
    path('login/', views.custom_login, name='login'),
    path('logout/', views.custom_logout, name='logout'),
    path('register/', views.register, name='register'),
    path('profile/', views.profile, name='profile'),
    path('settings/', views.settings, name='settings'),
    path('search/', views.search, name='search'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('news/', views.news, name='news'),
    path('live-charts/', views.live_charts, name='live_charts'),
    path('api/market-data/', views.market_data_api, name='market_data_api'),
    path('clear-cache/', views.clear_cache, name='clear_cache'),
]
