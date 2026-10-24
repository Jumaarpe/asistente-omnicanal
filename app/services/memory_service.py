import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logger import logger
from app.models.customer import Customer
from app.models.conversation import Conversation
from app.models.message import Message


class ConversationMemoryService:
    """
    Servicio de gestión de memoria conversacional y persistencia de clientes.
    Garantiza el contexto histórico requerido por el motor de IA (Día 3)
    y el seguimiento omnicanal unificado (Día 6).
    """

    async def get_or_create_customer(
        self,
        session: AsyncSession,
        phone: str,
        name: Optional[str] = None
    ) -> Customer:
        """
        Obtiene un cliente existente por su número de teléfono o crea uno nuevo.
        Actualiza el nombre si se detecta un nuevo pushName y renueva last_interaction_at.
        """
        stmt = select(Customer).where(Customer.phone == phone)
        result = await session.execute(stmt)
        customer = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if customer:
            customer.last_interaction_at = now
            if name and (not customer.name or customer.name == "Cliente"):
                customer.name = name
            await session.commit()
            await session.refresh(customer)
            return customer

        # Crear nuevo cliente
        new_customer = Customer(
            phone=phone,
            name=name or "Cliente",
            status="active",
            first_interaction_at=now,
            last_interaction_at=now
        )
        session.add(new_customer)
        try:
            await session.commit()
            await session.refresh(new_customer)
            logger.info(f"👤 [NUEVO CLIENTE REGISTRADO] ID: {new_customer.id} | Tel: {new_customer.phone} | Nombre: {new_customer.name}")
            return new_customer
        except Exception:
            # En caso de colisión concurrente (IntegrityError por phone unique)
            await session.rollback()
            stmt = select(Customer).where(Customer.phone == phone)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                return existing
            raise

    async def get_or_create_active_conversation(
        self,
        session: AsyncSession,
        customer_id: int,
        channel: str = "whatsapp"
    ) -> Conversation:
        """
        Recupera el hilo de conversación activo del cliente o abre uno nuevo si:
        1. No tiene conversaciones previas.
        2. La última conversación ya fue cerrada ('closed').
        3. Han transcurrido más de CONVERSATION_EXPIRATION_HOURS desde el último mensaje.
        """
        stmt = (
            select(Conversation)
            .where(
                and_(
                    Conversation.customer_id == customer_id,
                    Conversation.channel == channel,
                    Conversation.status.in_(["open", "pending_classification", "pending_routing", "routed"])
                )
            )
            .order_by(desc(Conversation.created_at))
            .limit(1)
        )
        result = await session.execute(stmt)
        conversation = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        expiration_delta = timedelta(hours=settings.CONVERSATION_EXPIRATION_HOURS)

        if conversation:
            # Comprobar expiración por inactividad
            # Normalizar conversation.updated_at a UTC si es naive
            updated_at = conversation.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)

            if (now - updated_at) > expiration_delta:
                logger.info(f"Conversación #{conversation.id} expirada por inactividad. Cerrando y abriendo nueva...")
                conversation.status = "closed"
                await session.commit()
            else:
                # Conversación activa vigente en este canal
                conversation.updated_at = now
                await session.commit()
                await session.refresh(conversation)
                return conversation

        # Herencia de estado previo si el cliente ya interactuó en otro canal
        recent_stmt = (
            select(Conversation)
            .where(
                and_(
                    Conversation.customer_id == customer_id,
                    Conversation.status.in_(["pending_routing", "routed"])
                )
            )
            .order_by(desc(Conversation.updated_at))
            .limit(1)
        )
        recent_res = await session.execute(recent_stmt)
        prev_active = recent_res.scalar_one_or_none()

        inherited_advisor = prev_active.assigned_advisor if prev_active else None
        inherited_intent = prev_active.intent if prev_active else None
        inherited_confidence = prev_active.intent_confidence if prev_active else None

        # Crear nueva conversación para este canal
        new_conversation = Conversation(
            customer_id=customer_id,
            channel=channel,
            status="routed" if inherited_advisor else "open",
            intent=inherited_intent,
            intent_confidence=inherited_confidence,
            assigned_advisor=inherited_advisor,
            created_at=now,
            updated_at=now
        )
        session.add(new_conversation)
        await session.commit()
        await session.refresh(new_conversation)
        logger.info(f"💬 [NUEVA CONVERSACIÓN] ID: {new_conversation.id} | Cliente ID: {customer_id} | Canal: {channel} | Asesor Heredado: {inherited_advisor}")
        return new_conversation

    async def save_message(
        self,
        session: AsyncSession,
        conversation_id: int,
        sender_role: str,
        content: str,
        message_id_origin: Optional[str] = None,
        message_type: str = "text",
        raw_metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """
        Persiste un mensaje en el historial cronológico de la conversación.
        """
        # Deduplicación por message_id_origin si aplica
        if message_id_origin:
            stmt = select(Message).where(
                and_(
                    Message.conversation_id == conversation_id,
                    Message.message_id_origin == message_id_origin
                )
            )
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                logger.warning(f"Mensaje ID {message_id_origin} ya existía en BD para conv #{conversation_id}")
                return existing

        now = datetime.now(timezone.utc)
        meta_str = json.dumps(raw_metadata) if raw_metadata else None

        msg = Message(
            conversation_id=conversation_id,
            message_id_origin=message_id_origin,
            sender_role=sender_role,
            message_type=message_type,
            content=content,
            timestamp=now,
            raw_metadata=meta_str
        )
        session.add(msg)

        # Actualizar timestamp de la conversación
        conv_stmt = select(Conversation).where(Conversation.id == conversation_id)
        conv_res = await session.execute(conv_stmt)
        conv = conv_res.scalar_one_or_none()
        if conv:
            conv.updated_at = now

        await session.commit()
        await session.refresh(msg)
        return msg

    async def get_conversation_history(
        self,
        session: AsyncSession,
        conversation_id: int,
        limit: int = 10
    ) -> List[Dict[str, str]]:
        """
        Recupera los últimos N mensajes de la conversación formateados para inyección
        directa en el prompt del LLM (Día 3).
        
        Retorna:
            [{"role": "user"|"assistant"|"system", "content": "...", "timestamp": "..."}]
        """
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.timestamp))
            .limit(limit)
        )
        result = await session.execute(stmt)
        messages = list(result.scalars().all())
        # Revertir a orden cronológico natural (ascendente)
        messages.reverse()

        history = []
        for m in messages:
            role = "user" if m.sender_role == "customer" else "assistant"
            history.append({
                "role": role,
                "sender_role": m.sender_role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat()
            })

        return history

    async def update_conversation_intent(
        self,
        session: AsyncSession,
        conversation_id: int,
        intent: str,
        confidence: Optional[float] = None,
        advisor: Optional[str] = None,
        status: str = "routed"
    ) -> Optional[Conversation]:
        """
        Actualiza el estado comercial e intención detectada por el LLM en la conversación.
        """
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        res = await session.execute(stmt)
        conversation = res.scalar_one_or_none()
        if not conversation:
            return None

        conversation.intent = intent
        conversation.intent_confidence = confidence
        if advisor:
            conversation.assigned_advisor = advisor
        conversation.status = status
        conversation.updated_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(conversation)
        logger.info(
            f"🎯 [INTENCIÓN ACTUALIZADA] Conv #{conversation_id} | "
            f"Intención: {intent} (confianza: {confidence}) | Asesor: {advisor} | Estado: {status}"
        )
        return conversation


memory_service = ConversationMemoryService()
