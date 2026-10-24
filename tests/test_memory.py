import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.config import settings
from app.database.session import init_db, async_session_factory
from app.models.customer import Customer
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.memory_service import memory_service


@pytest_asyncio.fixture(autouse=True)
async def setup_test_database():
    """Inicializa la base de datos antes de cada test."""
    await init_db()


@pytest.mark.asyncio
async def test_get_or_create_customer():
    """Verifica la creación y actualización de clientes en la base de datos."""
    phone = "+5491100001111"
    async with async_session_factory() as session:
        # 1. Crear nuevo cliente
        customer = await memory_service.get_or_create_customer(session, phone=phone, name="Lucas Rossi")
        assert customer.id is not None
        assert customer.phone == phone
        assert customer.name == "Lucas Rossi"
        first_id = customer.id

        # 2. Recuperar el mismo cliente
        existing = await memory_service.get_or_create_customer(session, phone=phone, name="Lucas Rossi Actualizado")
        assert existing.id == first_id
        assert existing.phone == phone


@pytest.mark.asyncio
async def test_get_or_create_conversation_and_messages():
    """Verifica la creación de conversaciones, mensajes y recuperación cronológica."""
    phone = "+5491100002222"
    async with async_session_factory() as session:
        customer = await memory_service.get_or_create_customer(session, phone=phone, name="Elena Morales")
        
        # 1. Crear conversación
        conv = await memory_service.get_or_create_active_conversation(session, customer_id=customer.id, channel="whatsapp")
        assert conv.id is not None
        assert conv.status == "open"
        assert conv.channel == "whatsapp"

        # 2. Guardar primer mensaje del cliente
        msg1 = await memory_service.save_message(
            session=session,
            conversation_id=conv.id,
            sender_role="customer",
            content="Hola, ¿tienen stock disponible de servidores?",
            message_id_origin="MSG_TEST_001"
        )
        assert msg1.id is not None

        # 3. Guardar respuesta del asistente
        msg2 = await memory_service.save_message(
            session=session,
            conversation_id=conv.id,
            sender_role="assistant",
            content="¡Hola Elena! Sí, disponemos de stock para entrega inmediata.",
            message_id_origin="MSG_TEST_002"
        )
        assert msg2.id is not None

        # 4. Recuperar historial para contexto del LLM
        history = await memory_service.get_conversation_history(session, conversation_id=conv.id, limit=10)
        assert len(history) == 2
        # Orden cronológico: primero msg1 (user), luego msg2 (assistant)
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hola, ¿tienen stock disponible de servidores?"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "¡Hola Elena! Sí, disponemos de stock para entrega inmediata."


@pytest.mark.asyncio
async def test_update_conversation_intent():
    """Verifica la actualización de la intención comercial y asignación de asesor."""
    phone = "+5491100003333"
    async with async_session_factory() as session:
        customer = await memory_service.get_or_create_customer(session, phone=phone, name="Santiago Venta")
        conv = await memory_service.get_or_create_active_conversation(session, customer_id=customer.id)

        # Actualizar a COMPRA
        updated = await memory_service.update_conversation_intent(
            session=session,
            conversation_id=conv.id,
            intent="COMPRA",
            confidence=0.96,
            advisor="Asesor Ventas Directas - Juan (+5491199990000)",
            status="routed"
        )
        assert updated is not None
        assert updated.intent == "COMPRA"
        assert updated.intent_confidence == 0.96
        assert updated.status == "routed"
        assert "Juan" in updated.assigned_advisor


@pytest.mark.asyncio
async def test_webhook_persists_to_database_and_history_endpoint():
    """
    Test de integración completo:
    Envía un webhook de WhatsApp y verifica que el cliente, la conversación y el mensaje
    se persistan en la BD y sean consultables vía /api/v1/conversations/{phone}/history.
    """
    test_phone = "+5491199998888"
    test_message_id = f"INTEG_MSG_{int(datetime.now().timestamp() * 1000)}"
    
    payload = {
        "event": "messages.upsert",
        "instance": "asistente-comercial",
        "data": {
            "key": {
                "remoteJid": f"{test_phone.replace('+', '')}@s.whatsapp.net",
                "fromMe": False,
                "id": test_message_id
            },
            "pushName": "Valeria Castro",
            "message": {
                "conversation": "Deseo comprar una suscripción anual corporativa ya mismo."
            },
            "messageType": "conversation",
            "messageTimestamp": int(datetime.now().timestamp())
        }
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Enviar mensaje vía Webhook
        post_res = await client.post(f"{settings.API_V1_STR}/webhooks/whatsapp", json=payload)
        assert post_res.status_code == 200
        assert post_res.json()["status"] == "received"

        # Consultar historial del cliente en el endpoint de persistencia
        get_res = await client.get(f"{settings.API_V1_STR}/conversations/{test_phone}/history")
        assert get_res.status_code == 200
        history_data = get_res.json()

        assert history_data["customer"]["phone"] == test_phone
        assert history_data["customer"]["name"] == "Valeria Castro"
        assert history_data["conversation"]["status"] in ["open", "pending_routing", "routed"]
        assert history_data["conversation"]["intent"] == "COMPRA"
        assert history_data["messages_count"] >= 1

        user_msgs = [m for m in history_data["history"] if m["role"] == "user"]
        assert len(user_msgs) >= 1
        assert "comprar una suscripción anual" in user_msgs[-1]["content"]

        # También se generó la respuesta automática del asistente
        assistant_msgs = [m for m in history_data["history"] if m["role"] == "assistant"]
        assert len(assistant_msgs) >= 1
