from pathlib import Path
import os
import environ
import logging

# Initialize environment variables
env = environ.Env(
    DEBUG=(bool, False),
    USE_REDIS=(bool, True),
)
BASE_DIR = Path(__file__).resolve().parent.parent
environ.Env.read_env(BASE_DIR / '.env')

# Validate critical environment variables
def validate_env_vars():
    required_vars = ['SECRET_KEY']
    if not env('DEBUG'):
        required_vars.extend(['COINGECKO_API_KEY', 'NEWSAPI_KEY'])
    for var in required_vars:
        if not env(var):
            raise environ.ImproperlyConfigured(f"Environment variable '{var}' is required")

validate_env_vars()

# API Keys
COINGECKO_API_KEY = env('COINGECKO_API_KEY', default='')
NEWSAPI_KEY = env('NEWSAPI_KEY', default='')

# Security
SECRET_KEY = env('SECRET_KEY')
DEBUG = env.bool('DEBUG', default=False)

ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'cryptomonitor.live',
    'crypto-ijco.onrender.com',
    '*.onrender.com',
]

CSRF_TRUSTED_ORIGINS = [
    'https://crypto-ijco.onrender.com',
    'https://cryptomonitor.live',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# Production optimizations
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
    CONN_MAX_AGE = 60
    DEBUG_PROPAGATE_EXCEPTIONS = False

# Applications
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'tracker',
]

# Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# URLs & WSGI/ASGI
ROOT_URLCONF = 'crypto_tracker.urls'
WSGI_APPLICATION = 'crypto_tracker.wsgi.application'
ASGI_APPLICATION = 'crypto_tracker.asgi.application'

# Templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Database
if env('DATABASE_URL', default=None):
    import dj_database_url
    DATABASES = {'default': dj_database_url.parse(env('DATABASE_URL'))}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Caching Configuration
REDIS_URL = env('REDIS_URL', default='redis://localhost:6379/0')

def test_redis_connection():
    try:
        import redis
        r = redis.from_url(REDIS_URL, socket_connect_timeout=5, socket_timeout=5)
        r.ping()
        return True
    except Exception as e:
        logging.warning(f"Redis connection failed: {str(e)}")
        return False

USE_REDIS = env.bool('USE_REDIS', default=True) and test_redis_connection()

if USE_REDIS:
    logging.info("Using Redis for caching")
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_KWARGS': {
                    'max_connections': 20,
                    'retry_on_timeout': True,
                },
            },
            'TIMEOUT': 300,
        }
    }
else:
    logging.info("Redis unavailable, using in-memory cache")
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'crypto-tracker-cache',
            'TIMEOUT': 300,
            'OPTIONS': {'MAX_ENTRIES': 1000},
        }
    }

# Channels Configuration
if USE_REDIS:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
                'capacity': 1500,
                'expiry': 60,
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# Celery Configuration
if USE_REDIS:
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_TIMEZONE = 'UTC'
    CELERY_BEAT_SCHEDULE = {
        'update-market-data': {
            'task': 'tracker.tasks.update_market_data',
            'schedule': 300.0,
        },
    }
else:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

# Authentication
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Localization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'tracker' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Logging Configuration
def get_logging_config():
    log_handlers = ['console']
    file_handler_config = {}
    
    try:
        logs_dir = BASE_DIR / 'logs'
        logs_dir.mkdir(exist_ok=True)
        test_file = logs_dir / 'test.log'
        test_file.touch()
        test_file.unlink()
        
        file_handler_config = {
            'file': {
                'class': 'logging.FileHandler',
                'filename': logs_dir / 'django.log',
                'formatter': 'verbose',
            }
        }
        if DEBUG:
            log_handlers.append('file')
            
    except (OSError, PermissionError):
        logging.warning("File logging unavailable, falling back to console")
    
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '[{levelname}] {asctime} {name} {process:d} {thread:d} {message}',
                'style': '{',
            },
            'simple': {
                'format': '[{levelname}] {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'verbose' if DEBUG else 'simple',
            },
            **file_handler_config
        },
        'root': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'loggers': {
            'django': {
                'handlers': log_handlers,
                'level': 'INFO',
                'propagate': False,
            },
            'tracker': {
                'handlers': log_handlers,
                'level': 'DEBUG' if DEBUG else 'INFO',
                'propagate': False,
            },
        },
    }

LOGGING = get_logging_config()

# API Rate Limiting Settings
API_RATE_LIMITS = {
    'COINGECKO_REQUESTS_PER_MINUTE': 10,
    'NEWSAPI_REQUESTS_PER_DAY': 1000,
    'DEFAULT_TIMEOUT': 30,
    'MAX_RETRIES': 3,
    'RETRY_BACKOFF_FACTOR': 2,
}

# Session Configuration
SESSION_COOKIE_AGE = 86400
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# CSRF Configuration
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Redirects (fixed)
LOGIN_URL = '/login/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_REDIRECT_URL = '/dashboard/'

SENTIMENT_API_URL = env('SENTIMENT_API_URL', default='https://api.sentiment.io/v1/crypto-sentiment')
