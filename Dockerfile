<<<<<<< HEAD
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg2, Pillow, etc.
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
=======
﻿# Use official Python 3.12 slim image (compatible with Django 4.1)
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    python3-dev \
>>>>>>> 7ef00e6 (Clean commit: re-add all files after fixes to cart remove method)
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
<<<<<<< HEAD
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

CMD ["gunicorn", "crypo_tracker.wsgi:application", "--bind", "0.0.0.0:8000"]
=======
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port (Render uses PORT environment variable, default to 8000 for local)
EXPOSE 8000

# Run gunicorn
CMD ["gunicorn", "cryto_tracker.wsgi:application", "--bind", "0.0.0.0:8000"]
>>>>>>> 7ef00e6 (Clean commit: re-add all files after fixes to cart remove method)
