FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SENTINEL_ENV=production \
    SENTINEL_DATASET_DIR=/app/Datasets

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install
COPY FULL_CODE/backend/requirements.txt /app/FULL_CODE/backend/
RUN pip install --no-cache-dir -r /app/FULL_CODE/backend/requirements.txt

# Copy source code and seed datasets
COPY FULL_CODE /app/FULL_CODE
COPY Datasets /app/Datasets

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn app.main:app --app-dir FULL_CODE/backend --host 0.0.0.0 --port ${PORT:-8000}"]
