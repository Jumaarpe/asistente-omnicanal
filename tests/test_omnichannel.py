import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.database.session import init_db, async_session_factory
from app.services.omnichannel_service import omnichannel_service


@pytest_asyncio.fixture(autouse=True)
async def setup_test_database():
    """Inicializa la base de datos antes de cada test."""
    await init_db()


@pytest.mark.asyncio
async def test_omnichannel_voice_to_whatsapp_handover():
    """
    Verifica el escenario omnicanal completo:
    1. El cliente primero llama por VOZ (Vapi) solicitando cotización.
    2. Luego escribe por WHATSAPP dando seguimiento.
    3. El sistema unifica la identidad, detecta la continuidad de canal y preserva al asesor.
    """
    phone = "+5491188880001"
    customer_name = "Emiliano Martínez"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # PASO 1: Llamada de Voz (Vapi) solicitando cotización
        vapi_call = {
            "message": {
                "type": "end-of-call-report",
                "call": {
                    "id": "vapi_omni_01",
                    "customer": {
                        "number": phone,
                        "name": customer_name
                    }
                },
                "transcript": "Cliente: Hola, llamo para pedir una cotización formal para equipar 50 oficinas.",
                "summary": "Petición de cotización formal de 50 oficinas."
            }
        }
        res_voice = await client.post(f"{settings.API_V1_STR}/webhooks/voice/vapi", json=vapi_call)
        assert res_voice.status_code == 200

        # PASO 2: Mismo cliente escribe por WhatsApp dando seguimiento
        wa_message = {
            "event": "messages.upsert",
            "data": {
                "key": {
                    "remoteJid": f"{phone.replace('+', '')}@s.whatsapp.net",
                    "fromMe": False,
                    "id": "wa_omni_02"
                },
                "pushName": customer_name,
                "message": {
                    "conversation": "Hola, acabo de llamar por teléfono por la cotización de las 50 oficinas, ¿recibieron mi solicitud?"
                }
            }
        }
        res_wa = await client.post(f"{settings.API_V1_STR}/webhooks/whatsapp", json=wa_message)
        assert res_wa.status_code == 200

        # PASO 3: Consultar la Línea de Tiempo 360° unificada
        timeline_res = await client.get(f"{settings.API_V1_STR}/customers/{phone}/timeline")
        assert timeline_res.status_code == 200
        data = timeline_res.json()

        assert data["phone"] == phone
        assert data["name"] == customer_name
        # Ambos canales registrados para el mismo cliente
        assert "voice" in data["channels_used"]
        assert "whatsapp" in data["channels_used"]
        assert data["active_intent"] == "COTIZACION"
        assert settings.ADVISOR_QUOTE_NAME in data["assigned_advisor"]
        assert data["total_messages"] >= 2

        # Verificar que el timeline contiene eventos de ambos canales
        channels_in_timeline = {event["channel"] for event in data["timeline"]}
        assert "voice" in channels_in_timeline
        assert "whatsapp" in channels_in_timeline


@pytest.mark.asyncio
async def test_omnichannel_cross_channel_detection_service():
    """Verifica el cálculo de continuidad de canal en el servicio omnichannel."""
    phone = "+5491188880002"
    async with async_session_factory() as session:
        # Consultar cliente sin interacciones previas
        timeline_empty = await omnichannel_service.get_customer_timeline(session, phone=phone)
        assert timeline_empty is None


@pytest.mark.asyncio
async def test_customers_timeline_api_404_on_unknown():
    """Verifica que el endpoint de timeline retorne 404 para un teléfono inexistente."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"{settings.API_V1_STR}/customers/+5491100009999/timeline")
        assert res.status_code == 404
