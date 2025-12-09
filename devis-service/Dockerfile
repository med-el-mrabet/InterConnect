FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY devis-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY shared/ /app/shared/

# Copy application code
COPY devis-service/ .

# Expose port
EXPOSE 5002

# Set Python path to include shared
ENV PYTHONPATH="/app/shared:${PYTHONPATH}"

# Run the application
CMD ["python", "app.py"]
