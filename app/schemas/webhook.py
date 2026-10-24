from datetime import datetime, timezone
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class NormalizedMessage(BaseModel):
    """
    Modelo canónico que unifica los mensajes recibidos desde cualquier canal
    (WhatsApp vía Evolution API / Meta Cloud API, o Voz vía Vapi/Retell).
    
    Garantiza que la lógica de negocio (clasificación y enrutamiento) sea agnóstica
    del proveedor de mensajería subyacente.
    """
    message_id: str = Field(..., description="ID único del mensaje en la plataforma de origen")
    sender_id: str = Field(..., description="Identificador del remitente (número de teléfono o ID de llamada)")
    sender_name: Optional[str] = Field(None, description="Nombre de contacto o pushName detectado")
    channel: Literal["whatsapp", "voice"] = Field(..., description="Canal de origen del mensaje")
    message_type: Literal["text", "audio", "image", "other"] = Field(default="text", description="Tipo de contenido")
    content: str = Field(..., description="Contenido en texto del mensaje o transcripción del audio")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Marca de tiempo en formato UTC"
    )
    raw_payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Payload original completo para auditoría y depuración"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "message_id": "3EB0C8F27D123456",
                "sender_id": "+5491198765432",
                "sender_name": "Carlos Rodríguez",
                "channel": "whatsapp",
                "message_type": "text",
                "content": "Buenas tardes, quisiera comprar 10 unidades del modelo Pro.",
                "timestamp": "2026-10-14T20:00:00Z",
                "raw_payload": {}
            }
        }
    }


class WebhookAckResponse(BaseModel):
    """
    Respuesta HTTP inmediata hacia la pasarela para confirmar recepción
    y prevenir reintentos por timeout.
    """
    status: Literal["received", "ignored", "error"] = Field(..., description="Estado de la recepción")
    message_id: Optional[str] = Field(None, description="ID del mensaje procesado")
    detail: Optional[str] = Field(None, description="Detalle del procesamiento o motivo de descarte")
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Momento exacto del acuse de recibo"
    )
