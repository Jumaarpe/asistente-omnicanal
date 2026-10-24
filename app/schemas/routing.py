from datetime import datetime, timezone
from typing import Optional, Literal
from pydantic import BaseModel, Field


class AdvisorInfo(BaseModel):
    """
    Información del asesor comercial asignado.
    """
    name: str = Field(..., description="Nombre del asesor")
    phone: str = Field(..., description="Teléfono internacional de WhatsApp del asesor")
    department: str = Field(..., description="Departamento comercial (Ventas Directas / Cuentas Corporativas)")
    specialty: str = Field(..., description="Especialidad o rol en la empresa")


class LeadCard(BaseModel):
    """
    Ficha estructurada del lead calificado para el equipo comercial y CRM.
    """
    customer_name: str
    customer_phone: str
    channel: str = "whatsapp"
    intent: Literal["COMPRA", "COTIZACION", "OTRO"]
    confidence: float
    urgency_level: Literal["alta", "media", "baja"]
    product_interest: Optional[str] = None
    quantity: Optional[int] = None
    reasoning: str
    last_message: str
    assigned_advisor: AdvisorInfo
    whatsapp_direct_link: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoutingResult(BaseModel):
    """
    Resultado de la derivación automática y envío de alertas.
    """
    status: Literal["routed", "unrouted", "skipped"]
    conversation_id: int
    intent: str
    assigned_advisor: Optional[AdvisorInfo] = None
    alert_message_sent: bool = False
    customer_notified: bool = False
    lead_card: Optional[LeadCard] = None
    detail: Optional[str] = None
