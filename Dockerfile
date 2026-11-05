# SmartShelf FastAPI + persistent WebSocket backend (single instance).
# Frontend remains on Vercel; the backend may also serve it for local diagnostics.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements-cloud.txt ./
RUN python -m pip install --upgrade pip && python -m pip install -r requirements-cloud.txt
COPY . .
RUN mkdir -p /data/uploads && chmod +x scripts/start_backend.sh
EXPOSE 8000
CMD ["sh", "scripts/start_backend.sh"]
