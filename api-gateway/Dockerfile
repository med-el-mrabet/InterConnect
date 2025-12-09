FROM python:3.11-slim

WORKDIR /app

# Copy requirements from api-gateway folder
COPY api-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code from api-gateway folder
COPY api-gateway/ .

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
