import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import settings


@pytest.mark.asyncio
async def test_health_check():
    """Verifica que los endpoints de salud respondan 200 OK con el estado del servicio."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

        response_v1 = await client.get(f"{settings.API_V1_STR}/health")
        assert response_v1.status_code == 200
        data_v1 = response_v1.json()
        assert data_v1["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_get_verification_challenge():
    """Verifica el handshake de validación de Meta Cloud API con hub.challenge."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Token correcto
        params = {
            "hub.mode": "subscribe",
            "hub.verify_token": settings.WEBHOOK_VERIFY_TOKEN,
            "hub.challenge": "1158201444"
        }
        response = await client.get(f"{settings.API_V1_STR}/webhooks/whatsapp", params=params)
        assert response.status_code == 200
        assert response.text == "1158201444"

        # Token incorrecto
        bad_params = {
            "hub.mode": "subscribe",
            "hub.verify_token": "token_falso_erroneo",
            "hub.challenge": "1158201444"
        }
        bad_response = await client.get(f"{settings.API_V1_STR}/webhooks/whatsapp", params=bad_params)
        assert bad_response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_post_evolution_incoming_customer_message():
    """
    Verifica que un mensaje de cliente entrante desde Evolution API
    sea aceptado y puesto en cola correctamente.
    """
    payload = {
        "event": "messages.upsert",
        "instance": "asistente-comercial",
        "data": {
            "key": {
                "remoteJid": "5491133334444@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG_EVO_TEST_001"
            },
            "pushName": "Mariana Gómez",
            "message": {
                "conversation": "Hola, estoy interesada en comprar el paquete empresarial de inmediato."
            },
            "messageType": "conversation",
            "messageTimestamp": 1713123456
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"{settings.API_V1_STR}/webhooks/whatsapp", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["message_id"] == "MSG_EVO_TEST_001"


@pytest.mark.asyncio
async def test_webhook_post_evolution_ignores_outgoing_message():
    """
    Verifica que los mensajes salientes (enviados por el bot o asesor, fromMe=True)
    sean identificados e ignorados para evitar loops infinitos.
    """
    payload = {
        "event": "messages.upsert",
        "instance": "asistente-comercial",
        "data": {
            "key": {
                "remoteJid": "5491133334444@s.whatsapp.net",
                "fromMe": True,
                "id": "MSG_BOT_OUTGOING_002"
            },
            "pushName": "Asistente Bot",
            "message": {
                "conversation": "¡Hola Mariana! Gracias por escribirnos..."
            },
            "messageType": "conversation"
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"{settings.API_V1_STR}/webhooks/whatsapp", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"


@pytest.mark.asyncio
async def test_webhook_post_generic_simplified_payload():
    """Verifica la compatibilidad con payloads simplificados o directos."""
    payload = {
        "message_id": "SIMP_TEST_999",
        "sender_id": "+5491188887777",
        "sender_name": "Roberto Díaz",
        "content": "Por favor envíenme una cotización formal para 50 puestos de trabajo."
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"{settings.API_V1_STR}/webhooks/whatsapp", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["message_id"] == "SIMP_TEST_999"
