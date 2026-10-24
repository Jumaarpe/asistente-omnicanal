#!/usr/bin/env bash
set -e

echo "============================================================"
echo "🚀 INICIANDO ASISTENTE INTELIGENTE OMNICANAL (PRODUCCIÓN)"
echo "============================================================"

# Asegurar directorios de persistencia
mkdir -p ./data ./logs

# Variables de ejecución
WORKERS="${WORKERS:-1}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
LOG_LEVEL="${LOG_LEVEL:-info}"

echo "⚙️  Configuración del Servidor:"
echo "   • Host:        ${HOST}"
echo "   • Puerto:      ${PORT}"
echo "   • Workers:     ${WORKERS}"
echo "   • Nivel Log:   ${LOG_LEVEL}"
echo "============================================================"

# Ejecutar servidor de aplicaciones uvicorn
exec uvicorn app.main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    --log-level "${LOG_LEVEL}" \
    --proxy-headers
