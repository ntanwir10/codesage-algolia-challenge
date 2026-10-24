FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl gcc git \
    && apt-get clean && find /var/lib/apt/lists -type f -delete

# Runtime dependencies only
COPY requirements.txt .
RUN pip install -r requirements.txt

# Non-root user (uid 1000 matches prod)
RUN adduser --disabled-password --gecos '' --uid 1000 appuser

COPY . .

# The SQLite dir must be writable by appuser. Named volumes mounted here
# inherit this ownership on first creation.
RUN mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Single worker: WebSocket, rate-limit and job state are in-process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload", "--reload-dir", "app"]
