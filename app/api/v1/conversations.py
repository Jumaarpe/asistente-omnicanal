from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from app.database.session import get_db
from app.models.customer import Customer
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.memory_service import memory_service

router = APIRouter(prefix="/conversations", tags=["Conversations & Memory"])


@router.get("/customers", summary="Listar clientes registrados")
async def list_customers(
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    Lista los clientes almacenados en la base de datos con su última fecha de interacción.
    """
    stmt = select(Customer).order_by(desc(Customer.last_interaction_at)).limit(limit)
    res = await db.execute(stmt)
    customers = res.scalars().all()
    return [
        {
            "id": c.id,
            "phone": c.phone,
            "name": c.name,
            "status": c.status,
            "first_interaction_at": c.first_interaction_at.isoformat(),
            "last_interaction_at": c.last_interaction_at.isoformat()
        }
        for c in customers
    ]


@router.get("/{phone}/history", summary="Obtener historial de conversación por teléfono")
async def get_history_by_phone(
    phone: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    Recupera el historial cronológico de mensajes del cliente correspondiente al número de teléfono.
    """
    # Limpiar formato básico
    clean_phone = phone.strip()
    if not clean_phone.startswith("+"):
        clean_phone = f"+{clean_phone}"

    stmt = select(Customer).where(Customer.phone == clean_phone)
    res = await db.execute(stmt)
    customer = res.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cliente con teléfono {clean_phone} no encontrado"
        )

    # Obtener última conversación de forma idempotente (read-only)
    stmt_conv = (
        select(Conversation)
        .where(Conversation.customer_id == customer.id)
        .order_by(desc(Conversation.created_at))
        .limit(1)
    )
    res_conv = await db.execute(stmt_conv)
    conv = res_conv.scalar_one_or_none()

    if not conv:
        return {
            "customer": {"id": customer.id, "phone": customer.phone, "name": customer.name},
            "conversation": None,
            "messages_count": 0,
            "history": []
        }
    history = await memory_service.get_conversation_history(db, conversation_id=conv.id, limit=limit)

    return {
        "customer": {
            "id": customer.id,
            "phone": customer.phone,
            "name": customer.name
        },
        "conversation": {
            "id": conv.id,
            "channel": conv.channel,
            "status": conv.status,
            "intent": conv.intent,
            "assigned_advisor": conv.assigned_advisor,
            "updated_at": conv.updated_at.isoformat()
        },
        "messages_count": len(history),
        "history": history
    }
