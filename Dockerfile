# LegalLens Pro - Production Dockerfile v9.0
FROM python:3.11-slim

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=7860
ENV PYTHONPATH=/app

# Working directory
WORKDIR /app

# System dependencies (voor PDF parsing en database)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads data static && \
    chmod -R 755 uploads data static

# Expose port
EXPOSE 7860

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import requests; r = requests.get('http://localhost:7860/health', timeout=5); exit(0 if r.status_code == 200 else 1)" || exit 1

# Run application
CMD ["python", "app.py"]
