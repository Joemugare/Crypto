# Use official Python 3.12 slim image (compatible with Django 4.1)
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies for psycopg2, Pillow, etc.
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

# Collect static files
ENV DJANGO_SETTINGS_MODULE=crypto_tracker.settings
RUN python manage.py collectstatic --noinput

# Expose port (Render uses PORT environment variable)
EXPOSE $PORT

# Run gunicorn with dynamic port
CMD ["gunicorn", "crypto_tracker.wsgi:application", "--bind", "0.0.0.0:$PORT", "--workers", "1"]
