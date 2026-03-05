FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

# Cloud provider extras: aws, azure, gcp, or cloud (all providers)
ARG CLOUD_EXTRAS=aws

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY app/ ./app/
COPY scripts/start.sh /app/start.sh

# Install dependencies with cloud extras
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[${CLOUD_EXTRAS}]"

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chmod +x /app/start.sh

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["/app/start.sh"]
