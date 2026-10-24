from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    """
    Evento unificado en la línea de tiempo omnicanal del cliente.
    Combina interacciones de WhatsApp, llamadas de voz y alertas del sistema.
    """
    id: int
    conversation_id: int
    channel: Literal["whatsapp", "voice"]
    sender_role: Literal["customer", "assistant", "system", "advisor"]
    message_type: str = "text"
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class CustomerTimelineResponse(BaseModel):
    """
    Vista 360° consolidada del cliente con su historial omnicanal completo.
    """
    customer_id: int
    phone: str
    name: Optional[str] = None
    status: str
    first_interaction_at: datetime
    last_interaction_at: datetime
    total_conversations: int
    total_messages: int
    active_intent: Optional[str] = None
    assigned_advisor: Optional[str] = None
    channels_used: List[str] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(default_factory=list)


class CrossChannelContext(BaseModel):
    """
    Contexto detectado cuando un cliente cambia de canal (ej. de Voz a WhatsApp o viceversa).
    """
    has_previous_interaction: bool
    previous_channel: Optional[str] = None
    current_channel: str
    previous_intent: Optional[str] = None
    assigned_advisor: Optional[str] = None
    summary_of_previous_session: Optional[str] = None
    continuity_detected: bool = False
