import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.database.session import init_db, async_session_factory
from app.models.customer import Customer
from app.models.conversation import Conversation
from app.services.voice_adapter import voice_adapter


@pytest_asyncio.fixture(autouse=True)
async def setup_test_database():
    """Inicializa la base de datos antes de cada test."""
    await init_db()


def test_voice_adapter_parse_vapi():
    """Verifica el parseo correcto de un payload de fin de llamada de Vapi AI."""
    payload = {
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": "vapi_call_123456",
                "customer": {
                    "number": "+5491155554444",
                    "name": "Ignacio Copani"
                },
                "status": "ended"
            },
            "transcript": "Agente: Gracias por llamar. ¿En qué puedo ayudarte? Cliente: Quiero comprar 10 unidades del sistema de monitoreo de inmediato.",
            "summary": "El cliente desea comprar 10 unidades de monitoreo ya.",
            "recordingUrl": "https://vapi.ai/recordings/call_123456.mp3"
        }
    }

    result = voice_adapter.parse_vapi_payload(payload)
    assert result is not None
    assert result.provider == "vapi"
    assert result.call_id == "vapi_call_123456"
    assert result.customer_phone == "+5491155554444"
    assert result.customer_name == "Ignacio Copani"
    assert "comprar 10 unidades" in result.transcript
    assert result.recording_url == "https://vapi.ai/recordings/call_123456.mp3"


def test_voice_adapter_parse_retell():
    """Verifica el parseo correcto de un payload de fin de llamada de Retell AI."""
    payload = {
        "event": "call_analyzed",
        "call_id": "retell_call_789012",
        "from_number": "+5491166665555",
        "customer_name": "Fabiana Cantilo",
        "transcript": "Agente: Hola. Cliente: Buenas tardes, solicitamos una cotización formal con membrete para 30 sucursales.",
        "call_analysis": {
            "call_summary": "Cliente solicita presupuesto formal para 30 sucursales."
        },
        "recording_url": "https://retellai.com/recordings/789012.wav"
    }

    result = voice_adapter.parse_retell_payload(payload)
    assert result is not None
    assert result.provider == "retell"
    assert result.call_id == "retell_call_789012"
    assert result.customer_phone == "+5491166665555"
    assert result.customer_name == "Fabiana Cantilo"
    assert "cotización formal" in result.transcript


@pytest.mark.asyncio
async def test_voice_webhook_vapi_compra_end_to_end():
    """
    Test de integración completo para Vapi AI:
    Envía llamada de voz de compra -> se persiste en BD con canal 'voice' -> se enruta a Ventas Directas.
    """
    vapi_payload = {
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": "vapi_integ_001",
                "customer": {
                    "number": "+5491199991111",
                    "name": "Leandro Paredes"
                }
            },
            "transcript": "Cliente: Hola, llamo para comprar el paquete premium empresarial hoy mismo. Por favor cobrame con tarjeta.",
            "summary": "Compra de paquete premium."
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(f"{settings.API_V1_STR}/webhooks/voice/vapi", json=vapi_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "received"
        assert data["message_id"] == "vapi_integ_001"

        # Consultar historial en BD
        hist_res = await client.get(f"{settings.API_V1_STR}/conversations/+5491199991111/history")
        assert hist_res.status_code == 200
        hist_data = hist_res.json()

        assert hist_data["customer"]["phone"] == "+5491199991111"
        assert hist_data["customer"]["name"] == "Leandro Paredes"
        assert hist_data["conversation"]["channel"] == "voice"
        assert hist_data["conversation"]["intent"] == "COMPRA"
        assert hist_data["conversation"]["status"] in ["open", "pending_routing", "routed"]


@pytest.mark.asyncio
async def test_voice_webhook_retell_cotizacion_end_to_end():
    """
    Test de integración completo para Retell AI:
    Envía llamada de voz de cotización -> se persiste con canal 'voice' -> se enruta a Cuentas Corporativas.
    """
    retell_payload = {
        "event": "call_analyzed",
        "call_id": "retell_integ_002",
        "from_number": "+5491199992222",
        "customer_name": "Rodrigo De Paul",
        "transcript": "Cliente: Buenos días, somos de Tech Solutions y necesitamos un presupuesto formal detallado para presentar en directorio.",
        "call_analysis": {
            "call_summary": "Solicitud de propuesta formal corporativa."
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(f"{settings.API_V1_STR}/webhooks/voice/retell", json=retell_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "received"

        # Consultar historial en BD
        hist_res = await client.get(f"{settings.API_V1_STR}/conversations/+5491199992222/history")
        assert hist_res.status_code == 200
        hist_data = hist_res.json()

        assert hist_data["customer"]["phone"] == "+5491199992222"
        assert hist_data["conversation"]["channel"] == "voice"
        assert hist_data["conversation"]["intent"] == "COTIZACION"
