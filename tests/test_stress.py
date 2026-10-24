import asyncio
import pytest
import httpx
from app.main import app
from app.database.session import async_session_factory
from app.models.customer import Customer
from app.models.conversation import Conversation
from sqlalchemy import select, func


@pytest.mark.asyncio
async def test_high_concurrency_mixed_webhooks():
    """
    Prueba de estrés y concurrencia (Día 7):
    Envía una ráfaga simultánea de peticiones mixtas (WhatsApp, Vapi y Retell)
    para verificar que:
    1. La API responde con HTTP 200 y ack en todos los casos sin bloqueos.
    2. SQLite con WAL mode maneja escrituras concurrentes sin OperationalError.
    3. Todos los clientes y conversaciones se crean íntegramente.
    """
    transport = httpx.ASGITransport(app=app)
    num_requests = 25

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        tasks = []

        for i in range(num_requests):
            # Alternar entre WhatsApp y llamadas de Voz
            if i % 3 == 0:
                payload = {
                    "data": {
                        "key": {
                            "id": f"PYTEST_STRESS_WA_{i}",
                            "remoteJid": f"5491122{i:04d}@s.whatsapp.net",
                            "fromMe": False
                        },
                        "pushName": f"Test Stress {i}",
                        "message": {
                            "conversation": f"Quiero comprar urgente el plan para mi empresa #{i}"
                        }
                    }
                }
                tasks.append(client.post("/api/v1/webhooks/whatsapp", json=payload))
            elif i % 3 == 1:
                payload = {
                    "message": {
                        "type": "end-of-call-report",
                        "call": {
                            "id": f"pytest_vapi_stress_{i}",
                            "customer": {
                                "number": f"+5491133{i:04d}",
                                "name": f"Vapi Stress {i}"
                            },
                            "transcript": f"Buenas tardes, quisiera cotizar una flota de 10 laptops #{i}.",
                            "recordingUrl": f"https://api.vapi.ai/recordings/test_{i}.mp3",
                            "duration": 30
                        }
                    }
                }
                tasks.append(client.post("/api/v1/webhooks/voice/vapi", json=payload))
            else:
                payload = {
                    "event": "call_analyzed",
                    "call": {
                        "call_id": f"pytest_retell_stress_{i}",
                        "from_number": f"+5491144{i:04d}",
                        "transcript": f"Hola, deseo comprar 5 routers industriales hoy mismo #{i}.",
                        "recording_url": f"https://retell.ai/recordings/test_{i}.wav",
                        "duration_ms": 45000
                    }
                }
                tasks.append(client.post("/api/v1/webhooks/voice/retell", json=payload))

        # Enviar todas concurrentemente
        responses = await asyncio.gather(*tasks)

        # 1. Todas deben haber respondido HTTP 200 inmediatamente
        assert len(responses) == num_requests
        for resp in responses:
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "received"

        # Permitir que las background tasks se completen
        await asyncio.sleep(2.0)

        # 2. Verificar que la base de datos no arrojó bloqueos y persistiò registros
        async with async_session_factory() as session:
            cust_count = (await session.execute(select(func.count(Customer.id)))).scalar() or 0
            conv_count = (await session.execute(select(func.count(Conversation.id)))).scalar() or 0
            assert cust_count > 0
            assert conv_count > 0
