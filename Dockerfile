# Use official Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Copy .env file into container
COPY .env .env

# Install python-dotenv so Django can read .env
RUN pip install python-dotenv

# Set Django settings
ENV DJANGO_SETTINGS_MODULE=crypto_tracker.settings

# Collect static files (loads .env automatically)
RUN set -a && source .env && python manage.py collectstatic --noinput

# Expose port (Render uses PORT environment variable)
ENV PORT 8000
EXPOSE $PORT

# Run gunicorn with dynamic port
CMD ["sh", "-c", "set -a && source .env && gunicorn crypto_tracker.wsgi:application --bind 0.0.0.0:$PORT --workers 1"]
