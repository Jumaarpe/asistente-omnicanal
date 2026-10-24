from typing import Optional, List, Dict, Any
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.database.session import get_db
from app.schemas.listener import (
    ListenerWebhookResponse,
    VendorMessageResponse,
    GeminiContextResponse
)
from app.services.listener_service import listener_service

router = APIRouter(prefix="/listener", tags=["Passive Listener (Modo Oyente Vendedores)"])


@router.post(
    "/webhook",
    response_model=ListenerWebhookResponse,
    summary="Recepción pasiva de webhooks de WhatsApp para números de vendedores"
)
@router.post(
    "/webhook/{vendedor_id}",
    response_model=ListenerWebhookResponse,
    summary="Recepción pasiva de webhooks indicando ID del vendedor en URL"
)
async def receive_vendor_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    vendedor_id: Optional[str] = None
):
    """
    Endpoint del MODO OYENTE (Escucha Pasiva).
    
    Características clave:
    1. Recibe webhooks de Evolution API configurados en las líneas de los vendedores.
    2. Procesa tanto los mensajes del cliente como las respuestas del vendedor humano.
    3. Es 100% pasivo y silencioso: NUNCA responde ni envía mensajes al cliente.
    4. Utiliza BackgroundTasks para guardar en SQLite (tabla 'historial_vendedores')
       sin bloquear la respuesta HTTP 200 OK (< 50ms).
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as e:
        logger.warning(f"[Modo Oyente] Petición entrante no contiene JSON válido: {str(e)}")
        return ListenerWebhookResponse(
            status="error",
            vendedor_id=vendedor_id,
            cliente_telefono=None,
            detail=f"Cuerpo no es un JSON válido: {str(e)}"
        )

    # Normalizar payload del webhook
    parsed = listener_service.parse_webhook_payload(
        payload=payload,
        fallback_vendedor_id=vendedor_id
    )

    if parsed is None:
        logger.debug("[Modo Oyente] Evento ignorado (grupo de WhatsApp o sin datos suficientes)")
        return ListenerWebhookResponse(
            status="ignored",
            vendedor_id=vendedor_id,
            cliente_telefono=None,
            detail="Evento ignorado (mensaje de grupo o formato no procesable)"
        )

    v_id, c_phone, msg_text, tipo, ts = parsed

    # Encolar persistencia en BackgroundTasks para responder inmediatamente con 200 OK
    background_tasks.add_task(
        listener_service.save_vendor_message,
        vendedor_id=v_id,
        cliente_telefono=c_phone,
        mensaje=msg_text,
        tipo=tipo,
        timestamp=ts
    )

    return ListenerWebhookResponse(
        status="received",
        vendedor_id=v_id,
        cliente_telefono=c_phone,
        detail="Mensaje capturado de forma pasiva y encolado para persistencia en historial_vendedores"
    )


@router.get(
    "/history",
    response_model=List[VendorMessageResponse],
    summary="Consultar historial en crudo de mensajes de vendedores"
)
@router.get(
    "/messages",
    response_model=List[VendorMessageResponse],
    summary="Alias para consultar historial de mensajes"
)
async def get_vendor_history(
    vendedor_id: Optional[str] = Query(None, description="Filtrar por identificador de vendedor"),
    cliente_telefono: Optional[str] = Query(None, description="Filtrar por teléfono del cliente"),
    limit: int = Query(100, ge=1, le=500, description="Límite máximo de mensajes"),
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna la lista de mensajes registrados en la tabla 'historial_vendedores'.
    Permite filtrar por vendedor y/o cliente.
    """
    registros = await listener_service.get_history(
        session=db,
        vendedor_id=vendedor_id,
        cliente_telefono=cliente_telefono,
        limit=limit
    )

    return [
        VendorMessageResponse(
            id=r.id,
            vendedor_id=r.vendedor_id,
            cliente_telefono=r.cliente_telefono,
            mensaje=r.mensaje,
            tipo=r.tipo,
            timestamp=r.timestamp
        )
        for r in registros
    ]


@router.get(
    "/gemini-context",
    response_model=GeminiContextResponse,
    summary="Recopilar y estructurar mensajes para análisis con la API de Google Gemini"
)
async def get_gemini_context(
    vendedor_id: Optional[str] = Query(None, description="ID del vendedor a auditar"),
    cliente_telefono: Optional[str] = Query(None, description="Teléfono del cliente involucrado"),
    limit: int = Query(50, ge=1, le=200, description="Cantidad de mensajes para el contexto de análisis"),
    db: AsyncSession = Depends(get_db)
):
    """
    Recopila los mensajes capturados en modo oyente y los transforma en una estructura
    lista para ser consumida directamente por Google Gemini para auditoría de ventas,
    evaluación de objeciones y coaching comercial.
    """
    context = await listener_service.build_gemini_context(
        session=db,
        vendedor_id=vendedor_id,
        cliente_telefono=cliente_telefono,
        limit=limit
    )
    return context
