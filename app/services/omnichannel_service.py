import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logger import logger
from app.models.customer import Customer
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.omnichannel import TimelineEvent, CustomerTimelineResponse, CrossChannelContext


class OmnichannelSyncService:
    """
    Servicio de Sincronización Omnicanal y Vista 360° del Cliente.
    Unifica el estado comercial y la memoria cronológica de interacciones
    entre llamadas de voz (Vapi/Retell) y mensajería de WhatsApp.
    """

    async def get_customer_timeline(
        self,
        session: AsyncSession,
        phone: str
    ) -> Optional[CustomerTimelineResponse]:
        """
        Genera la línea de tiempo cronológica unificada de todas las conversaciones
        y mensajes del cliente en todos los canales disponibles.
        """
        # Normalizar teléfono
        clean_phone = phone.strip()
        if not clean_phone.startswith("+"):
            clean_phone = f"+{clean_phone}"

        stmt = (
            select(Customer)
            .options(
                selectinload(Customer.conversations).selectinload(Conversation.messages)
            )
            .where(Customer.phone == clean_phone)
        )
        res = await session.execute(stmt)
        customer = res.scalar_one_or_none()

        if not customer:
            return None

        channels_used = set()
        flat_events: List[TimelineEvent] = []
        active_intent = None
        assigned_advisor = None

        # Ordenar conversaciones por antigüedad
        conversations = sorted(customer.conversations, key=lambda c: c.created_at)

        for conv in conversations:
            channels_used.add(conv.channel)
            if conv.intent:
                active_intent = conv.intent
            if conv.assigned_advisor:
                assigned_advisor = conv.assigned_advisor

            for msg in conv.messages:
                meta = json.loads(msg.raw_metadata) if msg.raw_metadata else None
                flat_events.append(
                    TimelineEvent(
                        id=msg.id,
                        conversation_id=conv.id,
                        channel=conv.channel,
                        sender_role=msg.sender_role,
                        message_type=msg.message_type,
                        content=msg.content,
                        timestamp=msg.timestamp,
                        metadata=meta
                    )
                )

        # Ordenar todos los eventos cronológicamente
        flat_events.sort(key=lambda e: e.timestamp)

        return CustomerTimelineResponse(
            customer_id=customer.id,
            phone=customer.phone,
            name=customer.name,
            status=customer.status,
            first_interaction_at=customer.first_interaction_at,
            last_interaction_at=customer.last_interaction_at,
            total_conversations=len(conversations),
            total_messages=len(flat_events),
            active_intent=active_intent,
            assigned_advisor=assigned_advisor,
            channels_used=sorted(list(channels_used)),
            timeline=flat_events
        )

    async def detect_cross_channel_context(
        self,
        session: AsyncSession,
        customer_id: int,
        current_channel: str
    ) -> CrossChannelContext:
        """
        Detecta si el cliente tiene una interacción activa previa en otro canal
        (ejemplo: cliente llamó por voz y ahora escribe por WhatsApp).
        """
        stmt = (
            select(Conversation)
            .where(Conversation.customer_id == customer_id)
            .order_by(desc(Conversation.created_at))
            .limit(2)
        )
        res = await session.execute(stmt)
        recent_convs = res.scalars().all()

        if not recent_convs:
            return CrossChannelContext(
                has_previous_interaction=False,
                current_channel=current_channel,
                continuity_detected=False
            )

        # Evaluar la conversación previa más reciente
        prev = recent_convs[0]
        continuity = (
            prev.channel != current_channel and
            prev.status in ["open", "pending_routing", "routed"]
        )

        return CrossChannelContext(
            has_previous_interaction=True,
            previous_channel=prev.channel,
            current_channel=current_channel,
            previous_intent=prev.intent,
            assigned_advisor=prev.assigned_advisor,
            continuity_detected=continuity,
            summary_of_previous_session=f"Conversación #{prev.id} previa en canal '{prev.channel}' con estado '{prev.status}' e intención '{prev.intent}'."
        )

    async def get_unified_omnichannel_history_for_llm(
        self,
        session: AsyncSession,
        customer_id: int,
        limit: int = 12
    ) -> List[Dict[str, str]]:
        """
        Construye un historial enriquecido omnicanal con prefijos de canal
        para que Google Gemini tenga visibilidad de llamadas y chats simultáneos.
        """
        stmt = (
            select(Message, Conversation.channel)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.customer_id == customer_id)
            .order_by(desc(Message.timestamp))
            .limit(limit)
        )
        res = await session.execute(stmt)
        rows = list(res.all())
        rows.reverse()

        unified_history = []
        for msg, channel in rows:
            canal_tag = "🎙️[Voz]" if channel == "voice" else "📱[WhatsApp]"
            role = "user" if msg.sender_role == "customer" else "assistant"
            
            unified_history.append({
                "role": role,
                "sender_role": msg.sender_role,
                "channel": channel,
                "content": f"{canal_tag} {msg.content}",
                "timestamp": msg.timestamp.isoformat()
            })

        return unified_history


omnichannel_service = OmnichannelSyncService()
