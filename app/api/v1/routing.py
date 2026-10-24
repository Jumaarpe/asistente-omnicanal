from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.database.session import get_db
from app.models.customer import Customer
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.routing import AdvisorInfo, LeadCard
from app.services.routing_service import routing_service

router = APIRouter(prefix="/routing", tags=["Commercial Routing & Leads"])


@router.get("/advisors", summary="Consultar asesores comerciales configurados")
async def get_advisors():
    """
    Lista los asesores comerciales configurados para atención de COMPRA y COTIZACIÓN.
    """
    return {
        "compra": routing_service.get_advisor_for_intent("COMPRA"),
        "cotizacion": routing_service.get_advisor_for_intent("COTIZACION")
    }


@router.get("/leads", summary="Listar leads calificados y enrutados")
async def list_routed_leads(
    limit: int = Query(20, ge=1, le=100),
    intent: Optional[str] = Query(None, description="Filtrar por intención: COMPRA o COTIZACION"),
    db: AsyncSession = Depends(get_db)
):
    """
    Recupera las conversaciones que han sido calificadas y derivadas a un asesor comercial.
    """
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.customer), selectinload(Conversation.messages))
        .where(Conversation.status == "routed")
    )
    if intent:
        stmt = stmt.where(Conversation.intent == intent.upper())

    stmt = stmt.order_by(desc(Conversation.updated_at)).limit(limit)
    res = await db.execute(stmt)
    conversations = res.scalars().all()

    leads = []
    for conv in conversations:
        last_msg = conv.messages[-1].content if conv.messages else ""
        leads.append({
            "conversation_id": conv.id,
            "channel": conv.channel,
            "intent": conv.intent,
            "confidence": conv.intent_confidence,
            "assigned_advisor": conv.assigned_advisor,
            "routed_at": conv.updated_at.isoformat(),
            "customer": {
                "id": conv.customer.id,
                "phone": conv.customer.phone,
                "name": conv.customer.name
            },
            "last_message": last_msg
        })

    return {
        "count": len(leads),
        "leads": leads
    }
