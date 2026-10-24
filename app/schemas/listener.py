from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class VendorMessageCreate(BaseModel):
    """
    Datos estructurados de un mensaje capturado en el modo oyente.
    """
    vendedor_id: str = Field(..., description="ID del vendedor o nombre de la instancia")
    cliente_telefono: str = Field(..., description="Teléfono del cliente en formato internacional")
    mensaje: str = Field(..., description="Contenido textual del mensaje")
    tipo: str = Field(default="cliente", description="Emisor: 'cliente' o 'vendedor' (o tipo de medio)")
    timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Fecha y hora del mensaje"
    )


class VendorMessageResponse(BaseModel):
    """
    Representación de un registro de mensaje almacenado en historial_vendedores.
    """
    id: int = Field(..., description="Identificador único del registro")
    vendedor_id: str = Field(..., description="ID del vendedor o instancia")
    cliente_telefono: str = Field(..., description="Teléfono del cliente")
    mensaje: str = Field(..., description="Texto del mensaje")
    tipo: str = Field(..., description="Tipo o emisor ('cliente' o 'vendedor')")
    timestamp: datetime = Field(..., description="Fecha y hora UTC")

    model_config = ConfigDict(from_attributes=True)


class ListenerWebhookResponse(BaseModel):
    """
    Respuesta inmediata HTTP 200 OK hacia Evolution API para confirmar
    recepción del webhook sin demoras.
    """
    status: Literal["received", "ignored", "error"] = Field(
        default="received",
        description="Estado de la recepción del webhook"
    )
    vendedor_id: Optional[str] = Field(None, description="Identificador del vendedor detectado")
    cliente_telefono: Optional[str] = Field(None, description="Teléfono del cliente detectado")
    detail: str = Field(..., description="Descripción del procesamiento pasivo")
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Marca de tiempo de recepción"
    )


class GeminiConversationMessage(BaseModel):
    """
    Turno individual estructurado para la conversación con Gemini.
    """
    emisor: str = Field(..., description="Rol: 'Vendedor' o 'Cliente'")
    tipo: str = Field(..., description="Tipo registrado en historial")
    mensaje: str = Field(..., description="Contenido del mensaje")
    timestamp: datetime = Field(..., description="Momento de emisión")


class GeminiContextResponse(BaseModel):
    """
    Estructura enriquecida preparada para alimentar la API de Google Gemini
    para realizar auditoría, coaching comercial y análisis de interacciones.
    """
    vendedor_id: Optional[str] = Field(None, description="Filtro de vendedor aplicado")
    cliente_telefono: Optional[str] = Field(None, description="Filtro de cliente aplicado")
    total_mensajes: int = Field(..., description="Cantidad total de mensajes recopilados")
    resumen_intercambio: Dict[str, int] = Field(
        default_factory=dict,
        description="Conteo de mensajes por interlocutor (ej. cliente: X, vendedor: Y)"
    )
    mensajes: List[VendorMessageResponse] = Field(..., description="Lista de mensajes cronológicos")
    transcripcion_formateada: str = Field(
        ...,
        description="Transcripción legible con roles y marcas temporales"
    )
    prompt_recomendado_gemini: str = Field(
        ...,
        description="Prompt listo para enviar como instrucción a Google Gemini"
    )
    gemini_contents_payload: List[Dict[str, Any]] = Field(
        ...,
        description="Estructura compatible directamente con el SDK google-genai ('contents')"
    )
    plantilla_analisis_sugerido: Dict[str, Any] = Field(
        ...,
        description="Esquema JSON recomendado para guiar la respuesta estructurada de Gemini"
    )
