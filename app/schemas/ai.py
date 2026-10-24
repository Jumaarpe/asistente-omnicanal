from typing import Optional, Literal, List, Dict
from pydantic import BaseModel, Field


class IntentClassificationResult(BaseModel):
    """
    Resultado estructurado de la clasificación semántica mediante Google Gemini.
    Distingue con rigor entre COMPRA directa, COTIZACIÓN formal y OTRO.
    """
    intent: Literal["COMPRA", "COTIZACION", "OTRO"] = Field(
        ...,
        description="Categoría comercial principal: 'COMPRA' (intención inmediata de pagar, comprar, contratar o reservar), 'COTIZACION' (solicitud de presupuesto formal, precios por volumen o desglose para evaluar), o 'OTRO' (saludos, consultas generales, soporte o dudas no comerciales)."
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Grado de certeza del modelo de 0.0 a 1.0."
    )
    reasoning: str = Field(
        ...,
        description="Justificación sucinta en español de por qué se asignó esta intención basándose en el lenguaje del cliente."
    )
    product_interest: Optional[str] = Field(
        None,
        description="Producto, servicio, plan o solución mencionada por el cliente."
    )
    quantity: Optional[int] = Field(
        None,
        description="Cantidad de unidades, usuarios o licencias requeridas si el cliente lo especificó."
    )
    urgency_level: Literal["alta", "media", "baja"] = Field(
        default="media",
        description="Nivel de urgencia detectado: 'alta' (hoy, urgente, ya, ahora), 'media' (esta semana, pronto), 'baja' (evaluación futura, sin apuro)."
    )
    suggested_reply: str = Field(
        ...,
        description="Propuesta de respuesta cordial, profesional y personalizada en español para responder al cliente por WhatsApp o voz."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "intent": "COMPRA",
                "confidence": 0.95,
                "reasoning": "El cliente solicita link de pago y desea adquirir 10 licencias empresariales de inmediato.",
                "product_interest": "Licencias Empresariales Pro",
                "quantity": 10,
                "urgency_level": "alta",
                "suggested_reply": "¡Hola Carlos! Con gusto te comparto el link de pago seguro para las 10 licencias empresariales."
            }
        }
    }


class ClassificationRequest(BaseModel):
    """
    Petición para el endpoint interactivo de clasificación de IA.
    """
    text: Optional[str] = Field(None, description="Mensaje puntual a clasificar")
    history: Optional[List[Dict[str, str]]] = Field(None, description="Historial de mensajes previos")
    customer_name: Optional[str] = Field(None, description="Nombre del cliente para personalizar")
