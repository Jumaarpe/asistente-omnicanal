# ==============================================================================
# Dockerfile: Asistente Inteligente Omnicanal de WhatsApp y Voz (Día 7)
# ==============================================================================

FROM python:3.12-slim

# Metadatos del contenedor
LABEL maintainer="Antigravity Team"
LABEL description="Asistente Inteligente Omnicanal de WhatsApp y Voz con Enrutamiento Comercial"

# Configuración del entorno Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    HOST=0.0.0.0

# Instalar dependencias esenciales del sistema operativo (curl para healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario y grupo sin privilegios para ejecución segura
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# Directorio de trabajo en el contenedor
WORKDIR /app

# Copiar manifiesto de dependencias e instalar paquetes en caché limpia
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente y scripts
COPY app/ ./app/
COPY scripts/ ./scripts/

# Crear directorios para persistencia de base de datos SQLite y logs
RUN mkdir -p /app/data /app/logs && \
    chown -R appuser:appgroup /app && \
    chmod +x /app/scripts/start.sh

# Ejecutar como usuario no privilegiado
USER appuser

# Exponer el puerto de la aplicación
EXPOSE 8000

# Healthcheck nativo de Docker
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando de entrada
CMD ["/app/scripts/start.sh"]
