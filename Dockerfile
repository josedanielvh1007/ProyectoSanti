# ============================================================
# Dockerfile — Debate Manager (Python 3.11 Slim)
# ============================================================
# Imagen base ligera para minimizar el tamaño del contenedor.
# El servidor escucha en 0.0.0.0 para ser visible en la LAN.
# ============================================================

FROM python:3.11-slim

# ── Metadatos ─────────────────────────────────────────────
LABEL maintainer="Debate Manager"
LABEL description="Sistema LAN de gestión de turnos para sala de debate"

# ── Variables de entorno ──────────────────────────────────
# Evita que Python genere archivos .pyc y deshabilita el buffer de stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Puerto donde escucha el servidor
    PORT=8000

# ── Directorio de trabajo dentro del contenedor ───────────
WORKDIR /app-debate

# ── Instalar dependencias del sistema (mínimas) ───────────
# build-essential solo si algún paquete Python necesita compilar C
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Copiar e instalar dependencias Python ─────────────────
# Copiamos requirements.txt primero para aprovechar el cache de Docker:
# si el archivo no cambia, Docker reutiliza la capa de instalación.
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Copiar el código fuente ────────────────────────────────
COPY app/ ./app/

# ── Crear y dar permisos al directorio de datos (CSV) ─────
# El directorio /data se usa para almacenar los archivos CSV exportados.
# Debe tener permisos de escritura para el usuario del contenedor.
RUN mkdir -p /data && chmod 777 /data

# ── Exponer el puerto de la aplicación ────────────────────
EXPOSE ${PORT}

# ── Healthcheck (Docker verifica que el servidor responde) ─
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# ── Comando de inicio ─────────────────────────────────────
# Usamos uvicorn directamente (más eficiente que via 'python main.py')
# --host 0.0.0.0  → escucha en todas las interfaces (necesario para LAN)
# --port 8000     → puerto expuesto
# --workers 1     → IMPORTANTE: un solo worker para compartir estado en memoria
#                   (múltiples workers necesitarían Redis para sincronizar)
CMD ["uvicorn", "app.main:socket_app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]
