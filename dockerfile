# 1. Base Image
FROM python:3.11-slim

# 2. Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Work Directory
WORKDIR /app

# 4. Non-root User & Data Directory
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

# 5. System Dependencies + Requirements (single layer to keep image small)
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

# 6. Copy Project Files
COPY . .

# 7. Switch to Non-root User
USER appuser

# 8. Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 9. Documentation
EXPOSE 8000

# 10. The Execution Command
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]

