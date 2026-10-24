import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Set
from app.core.logger import logger
from app.schemas.webhook import NormalizedMessage
from app.database.session import async_session_factory
from app.services.memory_service import memory_service
from app.services.ai_classifier import ai_classifier
from app.services.routing_service import routing_service
from app.services.omnichannel_service import omnichannel_service


class MessageProcessorService:
    """
    Servicio de procesamiento y normalización de mensajes omnicanal.
    Convierte payloads heterogéneos (Evolution API, Meta Cloud API, Voz) en un formato
    unificado e inicia el flujo de procesamiento asíncrono.
    """

    def __init__(self):
        # Caché en memoria para deduplicación rápida de mensajes en tránsito
        self._processed_message_ids: Set[str] = set()

    def clean_phone_number(self, jid_or_phone: str) -> str:
        """
        Limpia y estandariza identificadores de WhatsApp (JIDs) a números internacionales.
        Ejemplo: '5491198765432@s.whatsapp.net' -> '+5491198765432'
        """
        if not jid_or_phone:
            return ""
        # Remover sufijos típicos de WhatsApp
        clean = jid_or_phone.split("@")[0]
        # Remover caracteres no numéricos
        digits = re.sub(r"\D", "", clean)
        return f"+{digits}" if digits else clean

    def extract_evolution_text(self, message_obj: Dict[str, Any]) -> str:
        """
        Extrae el contenido de texto de las diferentes estructuras de mensaje de WhatsApp.
        """
        if not isinstance(message_obj, dict):
            return ""

        # 1. Mensaje de texto simple
        if "conversation" in message_obj and message_obj["conversation"]:
            return str(message_obj["conversation"]).strip()

        # 2. Mensaje de texto extendido (links, respuestas, texto largo)
        if "extendedTextMessage" in message_obj:
            ext = message_obj["extendedTextMessage"]
            if isinstance(ext, dict) and "text" in ext:
                return str(ext.get("text", "")).strip()

        # 3. Caption de imagen
        if "imageMessage" in message_obj:
            img = message_obj["imageMessage"]
            if isinstance(img, dict) and "caption" in img:
                return str(img.get("caption", "")).strip()

        # 4. Transcripción o mensaje de audio
        if "audioMessage" in message_obj:
            return "[Mensaje de voz recibido]"

        return ""

    def normalize_payload(self, raw_data: Dict[str, Any]) -> Optional[NormalizedMessage]:
        """
        Analiza el payload entrante y lo transforma en un NormalizedMessage canónico.
        Retorna None si el mensaje debe ser ignorado (por ejemplo, enviado por el propio bot).
        """
        # Caso 1: Payload de Evolution API
        if "data" in raw_data and isinstance(raw_data["data"], dict):
            data = raw_data["data"]
            key = data.get("key", {})
            
            # FILTRO CRÍTICO: Ignorar mensajes salientes enviados por el propio bot (fromMe == True)
            if key.get("fromMe", False) is True:
                logger.info(f"Ignorando mensaje saliente propio (fromMe=True, id={key.get('id')})")
                return None

            message_id = key.get("id") or f"msg_{int(datetime.now().timestamp() * 1000)}"
            remote_jid = key.get("remoteJid", "")
            
            # Ignorar mensajes de grupos de WhatsApp si el bot solo atiende clientes individuales
            if "@g.us" in remote_jid:
                logger.info(f"Ignorando mensaje de grupo de WhatsApp: {remote_jid}")
                return None

            sender_id = self.clean_phone_number(remote_jid)
            sender_name = data.get("pushName") or "Cliente"
            message_obj = data.get("message", {})
            content = self.extract_evolution_text(message_obj)

            # Si el contenido está vacío pero hay mensaje, registrar
            if not content:
                content = "[Mensaje multimedia o sin texto interpretable]"

            # Determinar tipo de mensaje
            msg_type = "text"
            if "audioMessage" in message_obj:
                msg_type = "audio"
            elif "imageMessage" in message_obj:
                msg_type = "image"

            return NormalizedMessage(
                message_id=message_id,
                sender_id=sender_id,
                sender_name=sender_name,
                channel="whatsapp",
                message_type=msg_type,
                content=content,
                raw_payload=raw_data
            )

        # Caso 2: Payload de Meta Cloud API estándar
        if "entry" in raw_data and isinstance(raw_data["entry"], list):
            for entry in raw_data["entry"]:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    if messages:
                        msg = messages[0]
                        sender_id = f"+{msg.get('from', '')}"
                        contacts = value.get("contacts", [])
                        sender_name = contacts[0].get("profile", {}).get("name") if contacts else "Cliente"
                        text_body = msg.get("text", {}).get("body", "")
                        return NormalizedMessage(
                            message_id=msg.get("id", f"meta_{int(datetime.now().timestamp())}"),
                            sender_id=sender_id,
                            sender_name=sender_name,
                            channel="whatsapp",
                            message_type="text",
                            content=text_body,
                            raw_payload=raw_data
                        )

        # Caso 3: Payload simplificado / Formato genérico (útil para tests y simuladores)
        if "sender_id" in raw_data and "content" in raw_data:
            return NormalizedMessage(
                message_id=raw_data.get("message_id", f"gen_{int(datetime.now().timestamp() * 1000)}"),
                sender_id=self.clean_phone_number(raw_data["sender_id"]),
                sender_name=raw_data.get("sender_name", "Cliente"),
                channel=raw_data.get("channel", "whatsapp"),
                message_type=raw_data.get("message_type", "text"),
                content=str(raw_data["content"]),
                raw_payload=raw_data
            )

        logger.warning(f"Payload no reconocido o sin formato compatible: {list(raw_data.keys())}")
        return None

    async def process_incoming_message(self, message: NormalizedMessage) -> None:
        """
        Punto de entrada de la lógica de negocio ejecutada en BackgroundTasks.
        Garantiza que la respuesta HTTP al webhook no se bloquee.
        """
        # Deduplicación básica
        if message.message_id in self._processed_message_ids:
            logger.warning(f"Mensaje duplicado descartado: {message.message_id}")
            return

        self._processed_message_ids.add(message.message_id)
        # Limitar tamaño de la memoria de deduplicación
        if len(self._processed_message_ids) > 10000:
            self._processed_message_ids.clear()

        logger.info(
            f"📥 [MENSAJE RECIBIDO] Canal: {message.channel.upper()} | "
            f"Remitente: {message.sender_name} ({message.sender_id}) | "
            f"ID: {message.message_id} | "
            f"Contenido: '{message.content}'"
        )

        # Persistencia en Base de Datos y Gestión de Memoria (Día 2)
        try:
            async with async_session_factory() as session:
                # 1. Obtener o crear cliente
                customer = await memory_service.get_or_create_customer(
                    session=session,
                    phone=message.sender_id,
                    name=message.sender_name
                )

                # 2. Obtener o crear conversación activa
                conversation = await memory_service.get_or_create_active_conversation(
                    session=session,
                    customer_id=customer.id,
                    channel=message.channel
                )

                # 3. Guardar mensaje en el historial
                saved_msg = await memory_service.save_message(
                    session=session,
                    conversation_id=conversation.id,
                    sender_role="customer",
                    content=message.content,
                    message_id_origin=message.message_id,
                    message_type=message.message_type,
                    raw_metadata=message.raw_payload
                )

                # 4. Sincronización Omnicanal: Detectar continuidad de canal y recuperar contexto unificado (Día 6)
                cross_context = await omnichannel_service.detect_cross_channel_context(
                    session=session,
                    customer_id=customer.id,
                    current_channel=message.channel
                )

                if cross_context.continuity_detected:
                    logger.info(
                        f"🔄 [CONTINUIDAD OMNICANAL DETECTADA] Cliente #{customer.id} | "
                        f"Traspaso de canal: {cross_context.previous_channel} ➔ {cross_context.current_channel} | "
                        f"Asesor previo asignado: {cross_context.assigned_advisor}"
                    )

                # Historial omnicanal unificado (WhatsApp + Voz) para alimentar a Gemini
                history = await omnichannel_service.get_unified_omnichannel_history_for_llm(
                    session=session,
                    customer_id=customer.id,
                    limit=12
                )

                logger.info(
                    f"💾 [MEMORIA OMNICANAL ACTUALIZADA] Cliente #{customer.id} | "
                    f"Conv #{conversation.id} ({conversation.status}) | "
                    f"Historial consolidado: {len(history)} interacciones (Voz + Texto)"
                )

                # 5. Invocar motor de clasificación de IA con Google Gemini (Día 3)
                classification = await ai_classifier.classify_conversation(
                    history=history,
                    customer_name=customer.name
                )

                # 6. Actualizar la conversación con la intención detectada
                await memory_service.update_conversation_intent(
                    session=session,
                    conversation_id=conversation.id,
                    intent=classification.intent,
                    confidence=classification.confidence,
                    status="pending_routing" if classification.intent in ["COMPRA", "COTIZACION"] else "open"
                )

                logger.info(
                    f"🎯 [INTENCIÓN CLASIFICADA] Conv #{conversation.id} -> "
                    f"{classification.intent} (Confianza: {classification.confidence:.2f}) | "
                    f"Urgencia: {classification.urgency_level} | "
                    f"Motivo: {classification.reasoning}"
                )

                # 7. Ejecutar Enrutamiento Comercial y Despacho de Alertas (Día 4)
                routing_result = await routing_service.route_conversation(
                    session=session,
                    customer=customer,
                    conversation=conversation,
                    classification=classification,
                    last_message=message.content
                )

                if routing_result.status == "routed":
                    advisor_name = routing_result.assigned_advisor.name if routing_result.assigned_advisor else "N/A"
                    logger.info(
                        f"📢 [ALERTA DESPACHADA] Lead asignado exitosamente a {advisor_name} | "
                        f"Alerta enviada: {routing_result.alert_message_sent} | "
                        f"Cliente notificado: {routing_result.customer_notified}"
                    )

                # =========================================================================
                # Próximos pasos:
                # Día 5: Integración del módulo de voz con IA (Vapi/Retell AI)
                # Día 6: Sincronización omnicanal (unificar estado entre voz y texto)
                # =========================================================================

        except Exception as e:
            logger.error(f"Error al persistir mensaje en base de datos: {str(e)}", exc_info=True)


# Instancia singleton del servicio
message_processor = MessageProcessorService()
