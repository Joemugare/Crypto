#!/usr/bin/env python
"""
Development Setup Script for Crypto Tracker
Helps diagnose and setup development environment
"""
import os
import sys
import subprocess
import platform

def check_redis():
    """Check if Redis is running"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0, socket_connect_timeout=1)
        r.ping()
        print("✓ Redis is running and accessible")
        return True
    except ImportError:
        print("✗ redis-py package not installed")
        print("  Install with: pip install redis")
        return False
    except Exception as e:
        print(f"✗ Redis is not running: {e}")
        print("  Start Redis to enable full functionality")
        return False

def check_dependencies():
    """Check if required packages are installed"""
    required_packages = [
        'django',
        'channels',
        'requests',
        'django-environ',
        'whitenoise'
    ]
    
    optional_packages = [
        'redis',
        'django-redis',
        'channels-redis',
        'dj-database-url',
        'psycopg2-binary'
    ]
    
    print("Checking required dependencies:")
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✓ {package}")
        except ImportError:
            print(f"✗ {package} - Install with: pip install {package}")
    
    print("\nChecking optional dependencies:")
    for package in optional_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✓ {package}")
        except ImportError:
            print(f"⚠ {package} (optional)")

def install_redis_windows():
    """Instructions for installing Redis on Windows"""
    print("\n=== Installing Redis on Windows ===")
    print("Option 1: Using Windows Subsystem for Linux (WSL)")
    print("  1. Install WSL2: wsl --install")
    print("  2. Install Ubuntu from Microsoft Store")
    print("  3. In WSL terminal: sudo apt update && sudo apt install redis-server")
    print("  4. Start Redis: redis-server")
    
    print("\nOption 2: Using Docker Desktop")
    print("  1. Install Docker Desktop")
    print("  2. Run: docker run -d --name redis -p 6379:6379 redis:alpine")
    
    print("\nOption 3: Download Windows build")
    print("  1. Download from: https://github.com/tporadowski/redis/releases")
    print("  2. Extract and run redis-server.exe")

def install_redis_mac():
    """Instructions for installing Redis on macOS"""
    print("\n=== Installing Redis on macOS ===")
    print("Using Homebrew (recommended):")
    print("  1. Install Homebrew: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
    print("  2. Install Redis: brew install redis")
    print("  3. Start Redis: brew services start redis")
    
    print("\nUsing Docker:")
    print("  1. Install Docker Desktop")
    print("  2. Run: docker run -d --name redis -p 6379:6379 redis:alpine")

def install_redis_linux():
    """Instructions for installing Redis on Linux"""
    print("\n=== Installing Redis on Linux ===")
    print("Ubuntu/Debian:")
    print("  sudo apt update && sudo apt install redis-server")
    print("  sudo systemctl start redis-server")
    
    print("\nCentOS/RHEL/Fedora:")
    print("  sudo yum install redis  # or sudo dnf install redis")
    print("  sudo systemctl start redis")
    
    print("\nUsing Docker:")
    print("  docker run -d --name redis -p 6379:6379 redis:alpine")

def create_env_file():
    """Create a sample .env file if it doesn't exist"""
    env_path = '.env'
    if os.path.exists(env_path):
        print(f"✓ {env_path} already exists")
        return
    
    env_content = """# Django Settings
SECRET_KEY=your-very-secret-key-here-change-this-in-production
DEBUG=True

# Database (optional - uses SQLite by default)
# DATABASE_URL=postgresql://user:password@localhost:5432/crypto_tracker

# Redis (optional - falls back to in-memory cache if not available)
REDIS_URL=redis://localhost:6379/0
USE_REDIS=True

# API Keys (optional but recommended)
COINGECKO_API_KEY=your-coingecko-api-key-here
NEWSAPI_KEY=your-newsapi-key-here

# Production settings (set to False in production)
# SECURE_SSL_REDIRECT=False
# SECURE_HSTS_SECONDS=0
"""
    
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print(f"✓ Created sample {env_path} file")
    print("  Edit this file to configure your settings")

def setup_database():
    """Setup database"""
    print("\n=== Setting up database ===")
    try:
        os.system('python manage.py makemigrations')
        os.system('python manage.py migrate')
        print("✓ Database migrations completed")
    except Exception as e:
        print(f"✗ Error setting up database: {e}")

def main():
    """Main setup function"""
    print("=== Crypto Tracker Development Setup ===\n")
    
    # Check Python version
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
        print(f"✗ Python {python_version.major}.{python_version.minor} detected. Python 3.8+ required.")
        return
    
    print(f"✓ Python {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # Check dependencies
    check_dependencies()
    
    # Check Redis
    redis_running = check_redis()
    
    # Show Redis installation instructions if not running
    if not redis_running:
        system = platform.system()
        if system == "Windows":
            install_redis_windows()
        elif system == "Darwin":  # macOS
            install_redis_mac()
        elif system == "Linux":
            install_redis_linux()
        
        print("\nNote: The application will work without Redis using in-memory cache,")
        print("but some features like real-time updates may be limited.")
    
    # Create .env file
    print(f"\n=== Environment Configuration ===")
    create_env_file()
    
    # Setup database
    if input("\nSetup database? (y/n): ").lower().startswith('y'):
        setup_database()
    
    print(f"\n=== Next Steps ===")
    print("1. Edit .env file with your API keys")
    print("2. Install Redis for full functionality (optional)")
    print("3. Run development server: python manage.py runserver")
    
    if redis_running:
        print("4. Optional: Start Celery worker: celery -A crypto_tracker worker -l info")
        print("5. Optional: Start Celery beat: celery -A crypto_tracker beat -l info")

if __name__ == "__main__":
    main()