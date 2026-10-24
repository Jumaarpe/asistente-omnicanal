from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.omnichannel import CustomerTimelineResponse, CrossChannelContext
from app.services.omnichannel_service import omnichannel_service

router = APIRouter(prefix="/customers", tags=["Omnichannel Customers 360°"])


@router.get(
    "/{phone}/timeline",
    response_model=CustomerTimelineResponse,
    summary="Línea de tiempo 360° unificada del cliente (WhatsApp + Voz)"
)
async def get_customer_timeline(
    phone: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna la visión 360° del cliente con todas sus interacciones (mensajes de WhatsApp,
    llamadas de voz de Vapi/Retell, alertas y asesores asignados) ordenadas cronológicamente.
    """
    timeline = await omnichannel_service.get_customer_timeline(session=db, phone=phone)
    if not timeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente con teléfono {phone} no encontrado en el sistema"
        )
    return timeline


@router.get(
    "/{phone}/cross-channel",
    response_model=CrossChannelContext,
    summary="Evaluar estado de continuidad omnicanal del cliente"
)
async def check_cross_channel_status(
    phone: str,
    channel: str = "whatsapp",
    db: AsyncSession = Depends(get_db)
):
    """
    Verifica si el cliente cuenta con interacciones activas en un canal distinto al consultado.
    """
    timeline = await omnichannel_service.get_customer_timeline(session=db, phone=phone)
    if not timeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente con teléfono {phone} no encontrado"
        )

    context = await omnichannel_service.detect_cross_channel_context(
        session=db,
        customer_id=timeline.customer_id,
        current_channel=channel
    )
    return context
