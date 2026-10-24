import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.database.session import async_session_factory
from app.models.vendor_history import HistorialVendedor
from app.schemas.listener import (
    VendorMessageResponse,
    GeminiContextResponse,
)


class ListenerService:
    """
    Servicio para el Módulo de Escucha Pasiva (Modo Oyente de Vendedores).
    
    Gestiona la captura silenciosa de conversaciones de WhatsApp de los números
    de los vendedores sin interactuar con el cliente, y estructura el historial
    para análisis comercial y auditoría de ventas con la API de Google Gemini.
    """

    def clean_phone_number(self, jid_or_phone: Optional[str]) -> str:
        """
        Limpia y estandariza identificadores de WhatsApp a números internacionales (+E.164).
        Ejemplo: '5491198765432@s.whatsapp.net' -> '+5491198765432'
        """
        if not jid_or_phone:
            return ""
        clean = jid_or_phone.split("@")[0]
        digits = re.sub(r"\D", "", clean)
        return f"+{digits}" if digits else clean

    def extract_evolution_text(self, message_obj: Any) -> str:
        """
        Extrae el contenido de texto de las variadas estructuras de mensaje de WhatsApp.
        """
        if isinstance(message_obj, str):
            return message_obj.strip()

        if not isinstance(message_obj, dict):
            return ""

        # 1. Mensaje de texto plano
        if "conversation" in message_obj and message_obj["conversation"]:
            return str(message_obj["conversation"]).strip()

        # 2. Mensaje de texto extendido (links, citas, texto enriquecido)
        if "extendedTextMessage" in message_obj:
            ext = message_obj["extendedTextMessage"]
            if isinstance(ext, dict) and "text" in ext:
                return str(ext.get("text", "")).strip()

        # 3. Caption o pie de foto
        if "imageMessage" in message_obj:
            img = message_obj["imageMessage"]
            if isinstance(img, dict) and "caption" in img:
                return str(img.get("caption", "")).strip()
            return "[Imagen recibida]"

        # 4. Mensajes de audio / notas de voz
        if "audioMessage" in message_obj:
            return "[Nota de voz recibida]"

        # 5. Documentos
        if "documentMessage" in message_obj:
            doc = message_obj["documentMessage"]
            title = doc.get("title") or doc.get("fileName") or "documento" if isinstance(doc, dict) else "documento"
            return f"[Documento adjunto: {title}]"

        return "[Mensaje multimedia o sin texto]"

    def parse_webhook_payload(
        self,
        payload: Dict[str, Any],
        fallback_vendedor_id: Optional[str] = None
    ) -> Optional[Tuple[str, str, str, str, datetime]]:
        """
        Normaliza el payload recibido desde Evolution API o formatos simplificados.
        
        Retorna:
            (vendedor_id, cliente_telefono, mensaje, tipo, timestamp)
            o None si el evento debe ser ignorado.
        """
        # Caso 1: Estructura nativa de Evolution API
        if "data" in payload and isinstance(payload["data"], dict):
            data = payload["data"]
            key = data.get("key", {})
            remote_jid = key.get("remoteJid", "")

            # Ignorar mensajes de grupos de WhatsApp para auditoría 1 a 1 de vendedores
            if "@g.us" in remote_jid:
                logger.debug(f"[Modo Oyente] Ignorando mensaje de grupo: {remote_jid}")
                return None

            cliente_telefono = self.clean_phone_number(remote_jid)
            if not cliente_telefono:
                return None

            vendedor_id = (
                fallback_vendedor_id
                or payload.get("instance")
                or data.get("instance")
                or "vendedor_desconocido"
            )

            # En modo oyente:
            # fromMe == True -> Mensaje emitido por el vendedor humano
            # fromMe == False -> Mensaje emitido por el cliente
            from_me = key.get("fromMe", False)
            tipo = "vendedor" if from_me else "cliente"

            message_obj = data.get("message", {})
            mensaje = self.extract_evolution_text(message_obj)

            # Extraer timestamp
            msg_ts = data.get("messageTimestamp")
            if msg_ts and isinstance(msg_ts, (int, float)):
                timestamp = datetime.fromtimestamp(msg_ts, tz=timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)

            return vendedor_id, cliente_telefono, mensaje, tipo, timestamp

        # Caso 2: Formato directo / simplificado (para integraciones directas o tests)
        if "cliente_telefono" in payload or "phone" in payload or "sender_id" in payload:
            phone_raw = (
                payload.get("cliente_telefono")
                or payload.get("phone")
                or payload.get("sender_id")
            )
            cliente_telefono = self.clean_phone_number(str(phone_raw))
            vendedor_id = (
                fallback_vendedor_id
                or payload.get("vendedor_id")
                or payload.get("instance")
                or "vendedor_desconocido"
            )
            mensaje = str(
                payload.get("mensaje")
                or payload.get("message")
                or payload.get("content")
                or ""
            ).strip()

            tipo = str(payload.get("tipo") or ("vendedor" if payload.get("fromMe") else "cliente"))
            
            ts_val = payload.get("timestamp")
            if isinstance(ts_val, str):
                try:
                    timestamp = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
                except Exception:
                    timestamp = datetime.now(timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)

            return vendedor_id, cliente_telefono, mensaje, tipo, timestamp

        return None

    async def save_vendor_message(
        self,
        vendedor_id: str,
        cliente_telefono: str,
        mensaje: str,
        tipo: str,
        timestamp: datetime
    ) -> None:
        """
        Tarea en segundo plano (BackgroundTasks) para persistir el mensaje en SQLite
        de forma 100% pasiva y silenciosa.
        
        Garantiza que la respuesta HTTP 200 OK hacia la pasarela ya se haya entregado.
        """
        try:
            async with async_session_factory() as session:
                registro = HistorialVendedor(
                    vendedor_id=vendedor_id,
                    cliente_telefono=cliente_telefono,
                    mensaje=mensaje,
                    tipo=tipo,
                    timestamp=timestamp
                )
                session.add(registro)
                await session.commit()
                await session.refresh(registro)

                logger.info(
                    f"👂 [MODO OYENTE] Mensaje guardado en historial_vendedores (ID={registro.id}) | "
                    f"Vendedor: {vendedor_id} | Cliente: {cliente_telefono} | Tipo: {tipo} | "
                    f"Mensaje: '{mensaje[:40]}...'"
                )
        except Exception as e:
            logger.error(
                f"❌ [MODO OYENTE] Error al persistir en historial_vendedores: {str(e)}",
                exc_info=True
            )

    async def get_history(
        self,
        session: AsyncSession,
        vendedor_id: Optional[str] = None,
        cliente_telefono: Optional[str] = None,
        limit: int = 100
    ) -> List[HistorialVendedor]:
        """
        Recupera los registros de historial_vendedores aplicando filtros opcionales.
        """
        stmt = select(HistorialVendedor)
        if vendedor_id:
            stmt = stmt.where(HistorialVendedor.vendedor_id == vendedor_id)
        if cliente_telefono:
            clean_phone = self.clean_phone_number(cliente_telefono)
            stmt = stmt.where(HistorialVendedor.cliente_telefono == clean_phone)

        # Ordenar cronológicamente para reconstruir el diálogo
        stmt = stmt.order_by(HistorialVendedor.timestamp.asc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def build_gemini_context(
        self,
        session: AsyncSession,
        vendedor_id: Optional[str] = None,
        cliente_telefono: Optional[str] = None,
        limit: int = 50
    ) -> GeminiContextResponse:
        """
        Recopila los mensajes del historial y los estructura para ser analizados
        por la API de Google Gemini (evaluación de desempeño, intenciones y calidad comercial).
        """
        registros = await self.get_history(
            session=session,
            vendedor_id=vendedor_id,
            cliente_telefono=cliente_telefono,
            limit=limit
        )

        resumen = {"cliente": 0, "vendedor": 0, "otro": 0}
        transcript_lines: List[str] = []
        mensajes_pydantic: List[VendorMessageResponse] = []

        for reg in registros:
            mensajes_pydantic.append(
                VendorMessageResponse(
                    id=reg.id,
                    vendedor_id=reg.vendedor_id,
                    cliente_telefono=reg.cliente_telefono,
                    mensaje=reg.mensaje,
                    tipo=reg.tipo,
                    timestamp=reg.timestamp
                )
            )

            # Conteo de resumen
            t_key = reg.tipo.lower()
            if "vendedor" in t_key:
                resumen["vendedor"] += 1
                rol_str = f"Vendedor ({reg.vendedor_id})"
            elif "cliente" in t_key:
                resumen["cliente"] += 1
                rol_str = f"Cliente ({reg.cliente_telefono})"
            else:
                resumen["otro"] += 1
                rol_str = f"Emisor ({reg.tipo})"

            ts_formatted = reg.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
            transcript_lines.append(f"[{ts_formatted}] {rol_str}: {reg.mensaje}")

        transcripcion = (
            "\n".join(transcript_lines)
            if transcript_lines
            else "[No hay mensajes registrados con los filtros especificados]"
        )

        # Prompt de auditoría y coaching para Gemini
        prompt_gemini = (
            "Eres un Auditor Comercial Senior y Coach de Ventas de clase mundial impulsado por Google Gemini.\n"
            "Analiza detalladamente la siguiente interacción en tiempo real entre un Vendedor y un Cliente "
            "capturada en modo escucha pasiva.\n\n"
            "=== TRANSCRIPCIÓN DE LA CONVERSACIÓN ===\n"
            f"{transcripcion}\n"
            "=========================================\n\n"
            "Tu tarea consiste en evaluar objetivamente:\n"
            "1. Intención real y necesidades prioritarias del cliente.\n"
            "2. Nivel de interés, temperatura comercial (Frío / Tibio / Caliente) y objeciones.\n"
            "3. Desempeño del vendedor: empatía, agilidad de respuesta, argumentación de valor y técnicas de cierre.\n"
            "4. Errores críticos u oportunidades comerciales desaprovechadas.\n"
            "5. Plan de acción inmediato sugerido para concretar la venta."
        )

        # Payload listo para el SDK oficial google-genai
        gemini_contents_payload = [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt_gemini
                    }
                ]
            }
        ]

        # Estructura JSON sugerida para salida estructurada
        plantilla_analisis = {
            "resumen_ejecutivo": "string",
            "temperatura_cliente": "FRIO | TIBIO | CALIENTE",
            "intencion_detectada": "COMPRA | COTIZACION | SOPORTE | DUDA_GENERAL",
            "desempeno_vendedor": {
                "calificacion_1_a_10": 8,
                "puntos_fuertes": ["string"],
                "puntos_a_mejorar": ["string"]
            },
            "objeciones_identificadas": ["string"],
            "riesgo_perdida_lead": "ALTO | MEDIO | BAJO",
            "siguiente_accion_recomendada": "string"
        }

        return GeminiContextResponse(
            vendedor_id=vendedor_id,
            cliente_telefono=cliente_telefono,
            total_mensajes=len(registros),
            resumen_intercambio=resumen,
            mensajes=mensajes_pydantic,
            transcripcion_formateada=transcripcion,
            prompt_recomendado_gemini=prompt_gemini,
            gemini_contents_payload=gemini_contents_payload,
            plantilla_analisis_sugerido=plantilla_analisis
        )


# Instancia singleton del servicio
listener_service = ListenerService()
