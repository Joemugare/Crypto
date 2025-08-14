# tracker/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('portfolio/', views.portfolio, name='portfolio'),
    path('watchlist/', views.watchlist, name='watchlist'),
    path('alerts/', views.alerts, name='alerts'),
    path('technical/', views.technical, name='technical'),
    path('portfolio/add/', views.add_to_portfolio, name='add_to_portfolio'),
    path('watchlist/add/', views.add_to_watchlist, name='add_to_watchlist'),
    path('alerts/add/', views.add_alert, name='add_alert'),
    path('register/', views.register, name='register'),
    path('login/', views.custom_login, name='login'),
    path('logout/', views.custom_logout, name='logout'),
    path('api/market-data/', views.market_data_api, name='market_data_api'),
    path('profile/', views.profile, name='profile'),
    path('settings/', views.settings, name='settings'),
    path('search/', views.search, name='search'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('news/', views.news, name='news'),
    path('live-charts/', views.live_charts, name='live_charts'),
]