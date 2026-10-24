import os
import re
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.logger import logger
from app.schemas.ai import IntentClassificationResult


SYSTEM_PROMPT = """
Eres el Cerebro Clasificador de Intenciones Comerciales de una empresa líder en ventas omnicanal.
Tu misión exclusiva y crítica es interpretar el requerimiento del cliente a través de su historial conversacional (WhatsApp o Voz) y clasificarlo con precisión quirúrgica en una de tres categorías:

1. **COMPRA** (Cierre Inmediato / Intención Transaccional):
   - El cliente tiene intención firme o directa de compra, contratación o pago.
   - Pide link de pago, datos bancarios, transferencia, factura directa, cobro con tarjeta o cierre de orden.
   - Palabras/patrones típicos: "quiero comprar ya", "cómo lo pago", "pásame el CBU/link", "lo quiero hoy", "cobrame", "dónde abono", "resérvame 2 unidades de inmediato".

2. **COTIZACIÓN** (Presupuesto Formal / Evaluación / Propuesta Comercial):
   - El cliente está evaluando alternativas, requiere un documento formal, propuesta escrita, precios por volumen o información para presentar a gerencia/socios.
   - Palabras/patrones típicos: "necesito cotización", "presupuesto formal", "propuesta desglosada con membrete", "cuánto me saldría para 50 usuarios", "lista de precios mayorista para evaluar".

3. **OTRO** (Saludos / Dudas Generales / Fuera de Alcance):
   - Saludos de cortesía ("Hola", "Buenas tardes") sin requerimiento explícito aún.
   - Consultas informativas ("dónde queda el local", "¿abren sábados?"), soporte técnico o mensajes ininteligibles.

REGLAS DE DECISIÓN CRÍTICAS:
- Analiza SIEMPRE todo el contexto de la conversación, no solo la última frase aislada.
- Si hay ambigüedad entre compra y cotización: si el cliente expresa urgencia de pago ("para hoy", "ya"), clasifica como COMPRA. Si pide "presupuesto para evaluar", clasifica como COTIZACION.
- La respuesta sugerida (suggested_reply) debe ser cordial, empática, profesional y redactada en español neutro, lista para enviarse al cliente.
"""


class AIClassifierService:
    """
    Servicio de clasificación de intenciones comerciales potenciado por Google Gemini.
    Utiliza Schemas de salida estructurados para garantizar respuestas tipadas y deterministas.
    """

    def __init__(self):
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        """
        Inicializa o devuelve la instancia singleton del cliente de Gemini.
        """
        # Obtener API Key de settings o variables de entorno del sistema
        api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY no detectada. El servicio operará con heurística de respaldo.")
        return genai.Client(api_key=api_key) if api_key else genai.Client()

    def _format_conversation_history(self, history: List[Dict[str, str]], customer_name: Optional[str] = None) -> str:
        """
        Convierte la lista de mensajes en un formato conversacional claro para Gemini.
        """
        formatted_lines = []
        c_name = customer_name or "Cliente"
        
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "").strip()
            if role == "user":
                formatted_lines.append(f"{c_name}: {content}")
            else:
                formatted_lines.append(f"Asistente: {content}")

        return "\n".join(formatted_lines)

    def _fallback_heuristic_classification(
        self,
        text: str,
        customer_name: Optional[str] = None
    ) -> IntentClassificationResult:
        """
        Heurística determinista de respaldo en caso de desconexión o fallo de API externa.
        """
        t = text.lower()
        c_name = customer_name or "Cliente"

        # Detección de COMPRA
        compra_keywords = ["comprar", "pagar", "pago", "transferir", "cbu", "link de pago", "tarjeta", "adquirir ya", "compro", "quiero comprar"]
        if any(kw in t for kw in compra_keywords):
            return IntentClassificationResult(
                intent="COMPRA",
                confidence=0.85,
                reasoning="Clasificación por heurística de respaldo: palabras clave directas de compra/pago.",
                urgency_level="alta",
                suggested_reply=f"¡Hola {c_name}! Con gusto procesamos tu compra de inmediato. Un asesor comercial te enviará las opciones de pago."
            )

        # Detección de COTIZACIÓN
        cotiz_keywords = ["cotizacion", "cotización", "cotizar", "presupuesto", "propuesta", "precios por mayor", "cuánto saldría", "membrete"]
        if any(kw in t for kw in cotiz_keywords):
            return IntentClassificationResult(
                intent="COTIZACION",
                confidence=0.85,
                reasoning="Clasificación por heurística de respaldo: solicitud explícita de cotización o presupuesto.",
                urgency_level="media",
                suggested_reply=f"¡Hola {c_name}! Recibimos tu solicitud de cotización. Nuestro equipo especializado preparará la propuesta formal a la brevedad."
            )

        # OTRO
        return IntentClassificationResult(
            intent="OTRO",
            confidence=0.70,
            reasoning="Clasificación por heurística de respaldo: consulta general o saludo.",
            urgency_level="baja",
            suggested_reply=f"¡Hola {c_name}! Gracias por comunicarte con nosotros. ¿En qué producto o servicio te gustaría que te asesoremos?"
        )

    async def classify_conversation(
        self,
        history: List[Dict[str, str]],
        customer_name: Optional[str] = None
    ) -> IntentClassificationResult:
        """
        Clasifica la intención de una conversación utilizando el modelo Google Gemini configurado.
        """
        if not history:
            return self._fallback_heuristic_classification("Hola", customer_name)

        formatted_dialogue = self._format_conversation_history(history, customer_name)
        prompt = (
            f"Historial conversacional reciente del cliente:\n"
            f"---\n"
            f"{formatted_dialogue}\n"
            f"---\n"
            f"Determina si la intención principal actual corresponde a COMPRA, COTIZACION u OTRO."
        )

        try:
            client = self._get_client()
            response = await client.aio.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.1,  # Máxima determinismo para clasificación estricta
                    response_mime_type="application/json",
                    response_schema=IntentClassificationResult
                )
            )

            # En google-genai, response.parsed contiene la instancia Pydantic deserializada
            if response.parsed and isinstance(response.parsed, IntentClassificationResult):
                result: IntentClassificationResult = response.parsed
                logger.info(
                    f"🧠 [GEMINI CLASIFICACIÓN] Intención: {result.intent} | "
                    f"Confianza: {result.confidence:.2f} | "
                    f"Urgencia: {result.urgency_level} | Motivo: {result.reasoning}"
                )
                return result

            # Si por alguna razón parsed no está tipado, parsear el texto JSON
            if response.text:
                result = IntentClassificationResult.model_validate_json(response.text)
                return result

            raise ValueError("Respuesta vacía de Gemini")

        except Exception as e:
            logger.error(f"Error en llamada a Gemini ({str(e)}). Activando heurística de respaldo...", exc_info=False)
            last_msg = history[-1].get("content", "") if history else ""
            return self._fallback_heuristic_classification(last_msg, customer_name)


ai_classifier = AIClassifierService()
