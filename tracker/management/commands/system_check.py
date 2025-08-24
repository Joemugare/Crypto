# tracker/management/commands/system_check.py
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.conf import settings
import requests

class Command(BaseCommand):
    help = 'Check system status and configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed information',
        )

    def handle(self, *args, **options):
        verbose = options['verbose']
        
        self.stdout.write(
            self.style.SUCCESS('=== Crypto Tracker System Check ===\n')
        )

        # Check Django settings
        self.check_django_settings(verbose)
        
        # Check cache
        self.check_cache()
        
        # Check database
        self.check_database()
        
        # Check API connectivity
        self.check_api_connectivity()
        
        # Check environment variables
        self.check_environment_variables(verbose)

    def check_django_settings(self, verbose):
        """Check Django configuration"""
        self.stdout.write("Django Configuration:")
        
        self.stdout.write(f"  Debug Mode: {settings.DEBUG}")
        self.stdout.write(f"  Secret Key: {'✓ Set' if settings.SECRET_KEY != 'django-insecure-dkp=mo(0wx+1n_ayw_!+ihyxe34!)_xu@fe(aju3j33aef=lj4' else '⚠ Using default (change in production)'}")
        
        if verbose:
            self.stdout.write(f"  Allowed Hosts: {settings.ALLOWED_HOSTS}")
            self.stdout.write(f"  Installed Apps: {len(settings.INSTALLED_APPS)} apps")

    def check_cache(self):
        """Check cache functionality"""
        self.stdout.write("\nCache System:")
        
        try:
            # Test cache write/read
            test_key = 'system_check_test'
            test_value = 'test_data'
            cache.set(test_key, test_value, 60)
            retrieved_value = cache.get(test_key)
            
            if retrieved_value == test_value:
                cache_backend = settings.CACHES['default']['BACKEND']
                if 'redis' in cache_backend.lower():
                    self.stdout.write("  ✓ Redis cache working")
                else:
                    self.stdout.write("  ✓ In-memory cache working")
                
                cache.delete(test_key)  # Cleanup
            else:
                self.stdout.write(self.style.ERROR("  ✗ Cache read/write failed"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Cache error: {e}"))

    def check_database(self):
        """Check database connectivity"""
        self.stdout.write("\nDatabase:")
        
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
                if row:
                    db_engine = settings.DATABASES['default']['ENGINE']
                    if 'sqlite' in db_engine:
                        self.stdout.write("  ✓ SQLite database connected")
                    elif 'postgresql' in db_engine:
                        self.stdout.write("  ✓ PostgreSQL database connected")
                    else:
                        self.stdout.write(f"  ✓ Database connected ({db_engine})")
                        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Database error: {e}"))

    def check_api_connectivity(self):
        """Check external API connectivity"""
        self.stdout.write("\nAPI Connectivity:")
        
        # Test CoinGecko API
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/ping",
                timeout=10
            )
            if response.status_code == 200:
                self.stdout.write("  ✓ CoinGecko API accessible")
            else:
                self.stdout.write(f"  ⚠ CoinGecko API returned status {response.status_code}")
        except requests.RequestException as e:
            self.stdout.write(self.style.WARNING(f"  ⚠ CoinGecko API unreachable: {e}"))

        # Test News API (if key is provided)
        newsapi_key = getattr(settings, 'NEWSAPI_KEY', '')
        if newsapi_key and newsapi_key != 'your-newsapi-key':
            try:
                response = requests.get(
                    f"https://newsapi.org/v2/everything?q=bitcoin&apiKey={newsapi_key}&pageSize=1",
                    timeout=10
                )
                if response.status_code == 200:
                    self.stdout.write("  ✓ News API accessible")
                else:
                    self.stdout.write(f"  ⚠ News API returned status {response.status_code}")
            except requests.RequestException as e:
                self.stdout.write(self.style.WARNING(f"  ⚠ News API unreachable: {e}"))
        else:
            self.stdout.write("  - News API key not configured")

    def check_environment_variables(self, verbose):
        """Check environment configuration"""
        self.stdout.write("\nEnvironment Variables:")
        
        # Check API keys
        coingecko_key = getattr(settings, 'COINGECKO_API_KEY', '')
        if coingecko_key:
            self.stdout.write("  ✓ CoinGecko API key configured")
        else:
            self.stdout.write("  - CoinGecko API key not set (optional)")

        newsapi_key = getattr(settings, 'NEWSAPI_KEY', '')
        if newsapi_key and newsapi_key != 'your-newsapi-key':
            self.stdout.write("  ✓ News API key configured")
        else:
            self.stdout.write("  - News API key not configured (optional)")

        if verbose:
            # Show rate limit settings
            rate_limits = getattr(settings, 'API_RATE_LIMITS', {})
            if rate_limits:
                self.stdout.write("\nAPI Rate Limits:")
                for key, value in rate_limits.items():
                    self.stdout.write(f"  {key}: {value}")

        self.stdout.write(f"\n✓ System check completed!")
        
        # Provide recommendations
        self.stdout.write("\nRecommendations:")
        if not coingecko_key:
            self.stdout.write("  • Get a CoinGecko API key for higher rate limits")
        if not newsapi_key or newsapi_key == 'your-newsapi-key':
            self.stdout.write("  • Configure News API key for news features")
        if settings.DEBUG:
            self.stdout.write("  • Set DEBUG=False in production")