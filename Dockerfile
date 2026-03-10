# ============================================================
# Dockerfile — Debate Manager (Python 3.11 Slim)
# ============================================================
FROM python:3.11-slim

LABEL maintainer="Debate Manager"
LABEL description="Sistema LAN de gestión de turnos para sala de debate"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PYTHONPATH=/app-debate/app

WORKDIR /app-debate

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

RUN mkdir -p /data && chmod 777 /data

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

CMD ["uvicorn", "app.main:socket_app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]