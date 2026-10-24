import re
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.models.customer import Customer
from app.models.conversation import Conversation
from app.schemas.ai import IntentClassificationResult
from app.schemas.routing import AdvisorInfo, LeadCard, RoutingResult
from app.services.whatsapp_client import whatsapp_client
from app.services.memory_service import memory_service


class RoutingService:
    """
    Motor de Enrutamiento Inteligente y Despacho de Alertas Comerciales.
    Asigna asesores según la intención detectada por la IA (COMPRA vs COTIZACIÓN)
    y genera alertas accionables por WhatsApp con acceso directo al cliente.
    """

    def get_advisor_for_intent(self, intent: str) -> Optional[AdvisorInfo]:
        """
        Devuelve la información del asesor comercial según la intención clasificada.
        """
        if intent == "COMPRA":
            return AdvisorInfo(
                name=settings.ADVISOR_PURCHASE_NAME,
                phone=settings.ADVISOR_PURCHASE_PHONE,
                department="Ventas Directas",
                specialty="Cierre Inmediato, Pagos y Facturación"
            )
        elif intent == "COTIZACION":
            return AdvisorInfo(
                name=settings.ADVISOR_QUOTE_NAME,
                phone=settings.ADVISOR_QUOTE_PHONE,
                department="Cuentas Corporativas",
                specialty="Cotizaciones Formales, Presupuestos y Descuentos por Volumen"
            )
        return None

    def build_lead_card(
        self,
        customer: Customer,
        conversation: Conversation,
        classification: IntentClassificationResult,
        advisor: AdvisorInfo,
        last_message: str
    ) -> LeadCard:
        """
        Construye la ficha comercial estructurada del prospecto.
        """
        clean_digits = re.sub(r"\D", "", customer.phone)
        wa_link = f"https://wa.me/{clean_digits}"

        return LeadCard(
            customer_name=customer.name or "Cliente",
            customer_phone=customer.phone,
            channel=conversation.channel,
            intent=classification.intent,
            confidence=classification.confidence,
            urgency_level=classification.urgency_level,
            product_interest=classification.product_interest,
            quantity=classification.quantity,
            reasoning=classification.reasoning,
            last_message=last_message,
            assigned_advisor=advisor,
            whatsapp_direct_link=wa_link
        )

    def format_advisor_alert(self, lead: LeadCard) -> str:
        """
        Genera el mensaje de alerta formateado para enviar al WhatsApp del asesor comercial.
        """
        icono = "🔥" if lead.intent == "COMPRA" else "📋"
        urgencia_icono = "🔴" if lead.urgency_level == "alta" else "🟡"
        canal_label = "🎙️ LLAMADA DE VOZ (IA)" if lead.channel == "voice" else "📱 WhatsApp"

        return (
            f"🚨 *NUEVO LEAD CALIFICADO - {lead.intent}* {icono}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Cliente:* {lead.customer_name}\n"
            f"📞 *Teléfono:* {lead.customer_phone}\n"
            f"🌐 *Canal:* {canal_label}\n"
            f"🎯 *Intención:* {lead.intent} (Certeza: {int(lead.confidence * 100)}%)\n"
            f"{urgencia_icono} *Urgencia:* {lead.urgency_level.upper()}\n"
            f"📦 *Producto/Servicio:* {lead.product_interest or 'No especificado'}\n"
            f"🔢 *Cantidad:* {lead.quantity or 'No especificada'}\n"
            f"📝 *Justificación IA:* {lead.reasoning}\n"
            f"💬 *Último mensaje:* \"{lead.last_message}\"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👉 *Iniciar chat directo:* {lead.whatsapp_direct_link}"
        )

    def build_customer_notification(
        self,
        customer: Customer,
        advisor: AdvisorInfo,
        intent: str,
        suggested_reply: Optional[str] = None
    ) -> str:
        """
        Genera la respuesta cordial para el cliente confirmando la asignación del asesor.
        """
        nombre = customer.name or "estimado cliente"
        
        if intent == "COMPRA":
            return (
                f"¡Hola {nombre}! 🎉 Recibimos tu solicitud de compra. "
                f"Te hemos asignado a nuestro asesor especialista *{advisor.name}* ({advisor.department}), "
                f"quien te contactará de inmediato para facilitarte las opciones de pago y entrega."
            )
        elif intent == "COTIZACION":
            return (
                f"¡Hola {nombre}! 📋 Hemos registrado tu solicitud de cotización formal. "
                f"Tu asesor asignado es *{advisor.name}* ({advisor.department}), "
                f"quien está preparando la propuesta detallada para enviártela a la brevedad."
            )
        else:
            return suggested_reply or f"¡Hola {nombre}! Gracias por contactarnos. ¿En qué podemos orientarte hoy?"

    async def route_conversation(
        self,
        session: AsyncSession,
        customer: Customer,
        conversation: Conversation,
        classification: IntentClassificationResult,
        last_message: str
    ) -> RoutingResult:
        """
        Ejecuta el flujo completo de enrutamiento:
        1. Evalúa si la intención califica para derivación comercial.
        2. Determina el asesor correspondiente.
        3. Genera y envía la alerta al asesor por WhatsApp.
        4. Opcionalmente responde al cliente notificándole la asignación.
        5. Actualiza el estado de la conversación a 'routed'.
        """
        intent = classification.intent

        # Si es OTRO, no requiere enrutamiento comercial
        if intent not in ["COMPRA", "COTIZACION"]:
            logger.info(f"Conv #{conversation.id} clasificada como {intent}. No requiere enrutamiento a asesor comercial.")
            
            # Si auto-reply está activo para clientes generales, enviar sugerencia
            if settings.AUTO_REPLY_CUSTOMER and classification.suggested_reply:
                await whatsapp_client.send_message(customer.phone, classification.suggested_reply)
                await memory_service.save_message(
                    session=session,
                    conversation_id=conversation.id,
                    sender_role="assistant",
                    content=classification.suggested_reply
                )

            return RoutingResult(
                status="skipped",
                conversation_id=conversation.id,
                intent=intent,
                detail="Intención no comercial (OTRO); conversación no enrutada"
            )

        # Verificar umbral mínimo de confianza
        if classification.confidence < settings.CONFIDENCE_THRESHOLD:
            logger.warning(
                f"Conv #{conversation.id}: Confianza ({classification.confidence:.2f}) "
                f"inferior al umbral ({settings.CONFIDENCE_THRESHOLD}). Enrutamiento en pausa."
            )
            return RoutingResult(
                status="unrouted",
                conversation_id=conversation.id,
                intent=intent,
                detail=f"Confianza inferior al umbral mínimo ({settings.CONFIDENCE_THRESHOLD})"
            )

        advisor = self.get_advisor_for_intent(intent)
        if not advisor:
            return RoutingResult(
                status="unrouted",
                conversation_id=conversation.id,
                intent=intent,
                detail="No se encontró un asesor configurado para la intención"
            )

        # 1. Crear ficha de lead
        lead_card = self.build_lead_card(
            customer=customer,
            conversation=conversation,
            classification=classification,
            advisor=advisor,
            last_message=last_message
        )

        # 2. Generar y enviar alerta al WhatsApp del asesor
        alert_text = self.format_advisor_alert(lead_card)
        alert_sent = await whatsapp_client.send_message(advisor.phone, alert_text)

        # Registrar alerta en el historial del sistema
        await memory_service.save_message(
            session=session,
            conversation_id=conversation.id,
            sender_role="system",
            content=f"[ALERTA ENVIADA AL ASESOR {advisor.name} ({advisor.phone})]"
        )

        # 3. Notificar al cliente si está configurado
        customer_notified = False
        if settings.AUTO_REPLY_CUSTOMER:
            customer_reply = self.build_customer_notification(
                customer=customer,
                advisor=advisor,
                intent=intent,
                suggested_reply=classification.suggested_reply
            )
            customer_notified = await whatsapp_client.send_message(customer.phone, customer_reply)
            
            # Persistir respuesta al cliente en BD
            await memory_service.save_message(
                session=session,
                conversation_id=conversation.id,
                sender_role="assistant",
                content=customer_reply
            )

        # 4. Actualizar estado de la conversación a 'routed'
        await memory_service.update_conversation_intent(
            session=session,
            conversation_id=conversation.id,
            intent=intent,
            confidence=classification.confidence,
            advisor=f"{advisor.name} ({advisor.phone})",
            status="routed"
        )

        logger.info(
            f"🚀 [LEAD ENRUTADO EXITOSAMENTE] Conv #{conversation.id} | "
            f"Cliente: {customer.name} -> Asesor: {advisor.name} ({advisor.phone}) | "
            f"Alerta enviada: {alert_sent} | Cliente notificado: {customer_notified}"
        )

        return RoutingResult(
            status="routed",
            conversation_id=conversation.id,
            intent=intent,
            assigned_advisor=advisor,
            alert_message_sent=alert_sent,
            customer_notified=customer_notified,
            lead_card=lead_card
        )


routing_service = RoutingService()
