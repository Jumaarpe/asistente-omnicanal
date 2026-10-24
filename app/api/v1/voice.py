from typing import Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, Request, status, HTTPException
from app.core.logger import logger
from app.schemas.webhook import WebhookAckResponse
from app.services.voice_adapter import voice_adapter
from app.services.message_processor import message_processor

router = APIRouter(prefix="/webhooks/voice", tags=["Voice AI (Vapi & Retell)"])


@router.get("", summary="Verificación del Webhook de Voz")
async def voice_webhook_status():
    """
    Verifica que la pasarela de voz con IA esté operativa.
    """
    return {
        "status": "active",
        "service": "Voice AI Webhook Adapter",
        "supported_providers": ["vapi", "retell", "generic"]
    }


@router.post("", response_model=WebhookAckResponse, summary="Webhook Universal de Voz (Auto-detección)")
async def receive_generic_voice_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Endpoint universal de llamadas de voz con IA.
    Detecta automáticamente si el webhook proviene de Vapi AI o Retell AI,
    extrae la transcripción, la asocia al cliente y activa la clasificación comercial.
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as e:
        logger.error(f"Error parseando JSON de llamada de voz: {str(e)}")
        return WebhookAckResponse(status="error", detail=f"Cuerpo no es un JSON válido: {str(e)}")

    voice_result = voice_adapter.auto_detect_and_parse(payload)
    if not voice_result:
        return WebhookAckResponse(
            status="ignored",
            detail="Evento de voz ignorado (no contiene transcripción final o formato desconocido)"
        )

    # Convertir a NormalizedMessage canónico
    normalized = voice_adapter.to_normalized_message(voice_result)

    # Encolar procesamiento asíncrono
    background_tasks.add_task(message_processor.process_incoming_message, normalized)

    logger.info(
        f"🎙️ [LLAMADA DE VOZ RECIBIDA] Proveedor: {voice_result.provider.upper()} | "
        f"Call ID: {voice_result.call_id} | Cliente: {voice_result.customer_phone}"
    )

    return WebhookAckResponse(
        status="received",
        message_id=voice_result.call_id,
        detail=f"Llamada de voz de {voice_result.provider.upper()} encolada para clasificación y enrutamiento"
    )


@router.post("/vapi", response_model=WebhookAckResponse, summary="Webhook específico para Vapi AI")
async def receive_vapi_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Endpoint dedicado para recibir eventos de fin de llamada (end-of-call-report) de Vapi AI.
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as e:
        return WebhookAckResponse(status="error", detail=f"JSON inválido: {str(e)}")

    voice_result = voice_adapter.parse_vapi_payload(payload)
    if not voice_result:
        return WebhookAckResponse(status="ignored", detail="Evento Vapi sin transcripción final")

    normalized = voice_adapter.to_normalized_message(voice_result)
    background_tasks.add_task(message_processor.process_incoming_message, normalized)

    return WebhookAckResponse(
        status="received",
        message_id=voice_result.call_id,
        detail="Llamada de Vapi AI encolada con éxito"
    )


@router.post("/retell", response_model=WebhookAckResponse, summary="Webhook específico para Retell AI")
async def receive_retell_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Endpoint dedicado para recibir eventos de fin de llamada (call_analyzed / call_ended) de Retell AI.
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as e:
        return WebhookAckResponse(status="error", detail=f"JSON inválido: {str(e)}")

    voice_result = voice_adapter.parse_retell_payload(payload)
    if not voice_result:
        return WebhookAckResponse(status="ignored", detail="Evento Retell sin transcripción final")

    normalized = voice_adapter.to_normalized_message(voice_result)
    background_tasks.add_task(message_processor.process_incoming_message, normalized)

    return WebhookAckResponse(
        status="received",
        message_id=voice_result.call_id,
        detail="Llamada de Retell AI encolada con éxito"
    )
