from typing import Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, Request, Query, Header, HTTPException, status
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.logger import logger
from app.schemas.webhook import WebhookAckResponse
from app.services.message_processor import message_processor

router = APIRouter()


@router.get("/webhooks/whatsapp", summary="Verificación de Webhook (Meta / Challenge)")
async def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    token: Optional[str] = Query(None, description="Token alternativo de verificación directa")
):
    """
    Endpoint GET para suscripción y validación del webhook según estándar Meta Cloud API
    y pruebas directas con token.
    """
    # Verificación estándar de Meta (Cloud API)
    if hub_mode == "subscribe":
        if hub_verify_token == settings.WEBHOOK_VERIFY_TOKEN:
            logger.info("Verificación de webhook Meta exitosa con hub.challenge")
            return PlainTextResponse(content=hub_challenge or "", status_code=status.HTTP_200_OK)
        else:
            logger.warning(f"Intento de verificación fallido. Token recibido inválido: {hub_verify_token}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token de verificación inválido"
            )

    # Verificación alternativa por query param
    if token:
        if token == settings.WEBHOOK_VERIFY_TOKEN:
            return {"status": "ok", "message": "Webhook activo y verificado"}
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token inválido"
        )

    return {"status": "active", "message": "Endpoint de Webhook WhatsApp listo para recibir eventos POST"}


@router.post("/webhooks/whatsapp", response_model=WebhookAckResponse, summary="Recepción de eventos de WhatsApp")
async def receive_whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    apikey: Optional[str] = Header(None, alias="apikey")
):
    """
    Endpoint principal para la recepción de eventos de WhatsApp (Evolution API, Meta, etc.).
    
    Flujo de arquitectura:
    1. Valida opcionalmente clave de API si está configurada.
    2. Recibe el payload JSON en bruto.
    3. Normaliza el mensaje a la estructura canónica agnóstica.
    4. Si es un mensaje válido de un cliente, programa su procesamiento en BackgroundTasks.
    5. Devuelve inmediatamente 200 OK con WebhookAckResponse (< 50ms) para evitar reintentos.
    """
    # Verificación opcional de API Key si está configurada en settings
    received_key = x_api_key or apikey
    if settings.WEBHOOK_API_KEY and received_key != settings.WEBHOOK_API_KEY:
        logger.warning(f"Rechazado evento webhook por API Key inválida: {received_key}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key no autorizada para el webhook"
        )

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as e:
        logger.error(f"Error parseando JSON del webhook: {str(e)}")
        return WebhookAckResponse(
            status="error",
            detail=f"Cuerpo no es un JSON válido: {str(e)}"
        )

    # Normalización del evento
    normalized = message_processor.normalize_payload(payload)

    if normalized is None:
        return WebhookAckResponse(
            status="ignored",
            detail="Evento ignorado (mensaje saliente del bot, evento de estado o formato no aplicable)"
        )

    # Encolar procesamiento en segundo plano (asíncrono no bloqueante)
    background_tasks.add_task(message_processor.process_incoming_message, normalized)

    return WebhookAckResponse(
        status="received",
        message_id=normalized.message_id,
        detail="Mensaje recibido y encolado para procesamiento"
    )
