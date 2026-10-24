import re
from typing import Optional, Dict, Any
import httpx

from app.core.config import settings
from app.core.logger import logger


class WhatsAppClientService:
    """
    Cliente saliente para el envío de mensajes de WhatsApp a través de Evolution API
    o en modo simulado para desarrollo y pruebas.
    """

    def clean_phone(self, phone: str) -> str:
        """
        Limpia el teléfono para la API de Evolution (dígitos sin signo +).
        """
        return re.sub(r"\D", "", phone)

    async def send_message(self, recipient_phone: str, text: str) -> bool:
        """
        Envía un mensaje de texto por WhatsApp al destinatario.
        """
        clean_num = self.clean_phone(recipient_phone)

        # Modo Simulación (útil cuando no hay instancia de Evolution activa en desarrollo local)
        if settings.SIMULATE_OUTGOING_WHATSAPP:
            logger.info(
                f"📤 [WHATSAPP SALIENTE SIMULADO] Destino: {recipient_phone} ({clean_num})\n"
                f"--- CONTENIDO ---\n{text}\n-----------------"
            )
            return True

        # Modo Real: Petición HTTP a Evolution API
        endpoint = f"{settings.EVOLUTION_API_URL.rstrip('/')}/message/sendText/{settings.EVOLUTION_INSTANCE_NAME}"
        headers = {
            "Content-Type": "application/json",
            "apikey": settings.EVOLUTION_API_KEY
        }
        payload = {
            "number": clean_num,
            "text": text,
            "options": {
                "delay": 1200,
                "presence": "composing"
            }
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(endpoint, json=payload, headers=headers)
                if res.status_code in [200, 201]:
                    logger.info(f"✅ Mensaje WhatsApp enviado exitosamente a {recipient_phone}")
                    return True
                else:
                    logger.error(f"❌ Error al enviar mensaje vía Evolution API: {res.status_code} - {res.text}")
                    return False
        except Exception as e:
            logger.error(f"Error de conexión con Evolution API ({endpoint}): {str(e)}")
            return False


whatsapp_client = WhatsAppClientService()
