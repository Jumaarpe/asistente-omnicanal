import re
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.core.logger import logger
from app.schemas.webhook import NormalizedMessage
from app.schemas.voice import VoiceCallNormalizedResult


class VoiceAdapterService:
    """
    Adaptador Híbrido Universal para APIs de Voz con IA (Vapi AI y Retell AI).
    Interpreta las transcripciones y eventos de llamadas entrantes o salientes
    y las normaliza al modelo canónico del sistema para ejecutar la clasificación y enrutamiento.
    """

    def clean_phone_number(self, phone: Optional[str]) -> str:
        """
        Limpia y estandariza el número telefónico del cliente al formato internacional E.164.
        """
        if not phone:
            return ""
        digits = re.sub(r"\D", "", phone)
        return f"+{digits}" if digits else phone

    def parse_vapi_payload(self, raw_data: Dict[str, Any]) -> Optional[VoiceCallNormalizedResult]:
        """
        Extrae datos de llamadas de Vapi AI (end-of-call-report, assistant-request o webhook directo).
        """
        # Vapi frecuentemente anida el evento dentro de la clave 'message'
        data = raw_data.get("message", raw_data)

        # Identificadores de Vapi
        call_obj = data.get("call", {})
        call_id = call_obj.get("id") or data.get("call_id") or f"vapi_{int(datetime.now().timestamp() * 1000)}"

        # Teléfono y nombre del cliente
        customer_obj = call_obj.get("customer", {})
        customer_phone = customer_obj.get("number") or call_obj.get("customerNumber") or data.get("customerNumber") or ""
        customer_name = customer_obj.get("name") or "Cliente Llamada"

        # Transcripción
        transcript = data.get("transcript") or call_obj.get("transcript") or ""
        if not transcript and "artifact" in data:
            transcript = data["artifact"].get("transcript", "")

        # Resumen y grabación
        summary = data.get("summary") or call_obj.get("summary")
        recording_url = data.get("recordingUrl") or call_obj.get("recordingUrl")

        if not transcript and not summary:
            logger.warning(f"Vapi: Evento recibido sin transcripción ni resumen aprovechable (call_id: {call_id})")
            return None

        clean_phone = self.clean_phone_number(customer_phone) or "+5491100000000"

        return VoiceCallNormalizedResult(
            provider="vapi",
            call_id=str(call_id),
            customer_phone=clean_phone,
            customer_name=customer_name,
            transcript=transcript or summary or "[Audio de llamada procesado]",
            summary=summary,
            recording_url=recording_url,
            raw_payload=raw_data
        )

    def parse_retell_payload(self, raw_data: Dict[str, Any]) -> Optional[VoiceCallNormalizedResult]:
        """
        Extrae datos de llamadas de Retell AI (call_analyzed, call_ended).
        Soporta atributos tanto en el nivel raíz como anidados en el objeto 'call'.
        """
        call_obj = raw_data.get("call") if isinstance(raw_data.get("call"), dict) else raw_data

        call_id = (
            raw_data.get("call_id") or call_obj.get("call_id") or
            call_obj.get("id") or f"retell_{int(datetime.now().timestamp() * 1000)}"
        )
        
        # En Retell, el número del cliente suele venir en from_number o customer_number
        customer_phone = (
            raw_data.get("from_number") or raw_data.get("customer_number") or raw_data.get("caller_number") or
            call_obj.get("from_number") or call_obj.get("customer_number") or call_obj.get("caller_number") or ""
        )
        customer_name = raw_data.get("customer_name") or call_obj.get("customer_name") or "Cliente Llamada"

        # Transcripción (texto o reconstrucción desde transcript_object)
        transcript = raw_data.get("transcript") or call_obj.get("transcript", "")
        if not transcript and ("transcript_object" in raw_data or "transcript_object" in call_obj):
            utterances = raw_data.get("transcript_object") or call_obj.get("transcript_object")
            if isinstance(utterances, list):
                parts = []
                for u in utterances:
                    role = "Cliente" if u.get("role") == "user" else "Agente"
                    parts.append(f"{role}: {u.get('content', '')}")
                transcript = "\n".join(parts)

        # Resumen de Retell
        analysis = raw_data.get("call_analysis") or call_obj.get("call_analysis", {})
        summary = analysis.get("call_summary") if isinstance(analysis, dict) else None
        recording_url = raw_data.get("recording_url") or call_obj.get("recording_url")

        if not transcript and not summary:
            logger.warning(f"Retell: Evento recibido sin transcripción (call_id: {call_id})")
            return None

        clean_phone = self.clean_phone_number(customer_phone) or "+5491100000000"

        return VoiceCallNormalizedResult(
            provider="retell",
            call_id=str(call_id),
            customer_phone=clean_phone,
            customer_name=customer_name,
            transcript=transcript or summary or "[Llamada de voz de Retell]",
            summary=summary,
            recording_url=recording_url,
            raw_payload=raw_data
        )

    def auto_detect_and_parse(self, raw_data: Dict[str, Any]) -> Optional[VoiceCallNormalizedResult]:
        """
        Auto-detecta si el payload proviene de Vapi AI o Retell AI y lo procesa acordemente.
        """
        # Detección de Retell AI
        if "call_id" in raw_data and ("call_analysis" in raw_data or "transcript_object" in raw_data or raw_data.get("event", "").startswith("call_")):
            logger.info("Detectado payload de voz proveniente de Retell AI")
            return self.parse_retell_payload(raw_data)

        # Detección de Vapi AI
        if "call" in raw_data or ("message" in raw_data and isinstance(raw_data["message"], dict) and "call" in raw_data["message"]):
            logger.info("Detectado payload de voz proveniente de Vapi AI")
            return self.parse_vapi_payload(raw_data)

        # Si viene con provider explícito
        provider = raw_data.get("provider", "").lower()
        if provider == "vapi":
            return self.parse_vapi_payload(raw_data)
        elif provider == "retell":
            return self.parse_retell_payload(raw_data)

        # Formato genérico de voz
        if "transcript" in raw_data and ("phone" in raw_data or "sender_id" in raw_data or "from_number" in raw_data):
            phone = raw_data.get("phone") or raw_data.get("sender_id") or raw_data.get("from_number") or ""
            return VoiceCallNormalizedResult(
                provider="generic",
                call_id=raw_data.get("call_id", f"call_{int(datetime.now().timestamp() * 1000)}"),
                customer_phone=self.clean_phone_number(phone) or "+5491100000000",
                customer_name=raw_data.get("customer_name") or "Cliente Llamada",
                transcript=str(raw_data["transcript"]),
                summary=raw_data.get("summary"),
                recording_url=raw_data.get("recording_url"),
                raw_payload=raw_data
            )

        logger.warning(f"No se pudo determinar el proveedor de voz para el payload: {list(raw_data.keys())}")
        return None

    def to_normalized_message(self, call_result: VoiceCallNormalizedResult) -> NormalizedMessage:
        """
        Transforma el resultado de la llamada de voz en un NormalizedMessage canónico
        listo para ser procesado por el cerebro del sistema.
        """
        return NormalizedMessage(
            message_id=call_result.call_id,
            sender_id=call_result.customer_phone,
            sender_name=call_result.customer_name,
            channel="voice",
            message_type="audio",
            content=call_result.transcript,
            raw_payload={
                **call_result.raw_payload,
                "voice_metadata": {
                    "provider": call_result.provider,
                    "call_id": call_result.call_id,
                    "summary": call_result.summary,
                    "recording_url": call_result.recording_url
                }
            }
        )


voice_adapter = VoiceAdapterService()
