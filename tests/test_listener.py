import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.config import settings
from app.database.session import init_db, async_session_factory
from app.models.vendor_history import HistorialVendedor


@pytest.fixture(autouse=True)
def setup_database():
    """
    Inicializa las tablas de la base de datos (incluyendo historial_vendedores)
    antes de ejecutar las pruebas de escucha pasiva.
    """
    import asyncio
    asyncio.run(init_db())


def test_listener_webhook_incoming_client_message():
    """
    Simula la llegada de un webhook de Evolution API con un mensaje entrante
    del cliente (fromMe=False) hacia el vendedor.
    
    Verifica:
    1. Respuesta HTTP 200 OK inmediata con status 'received'.
    2. Persistencia en la tabla SQLite 'historial_vendedores'.
    3. Valores exactos en: vendedor_id, cliente_telefono, mensaje, tipo='cliente', timestamp.
    """
    payload = {
        "event": "messages.upsert",
        "instance": "vendedor_juan",
        "data": {
            "key": {
                "remoteJid": "5491177778888@s.whatsapp.net",
                "fromMe": False,
                "id": "EVO_CLIENTE_001"
            },
            "pushName": "Roberto Gómez",
            "message": {
                "conversation": "Hola Juan, te consulto por el precio de las 5 licencias que hablamos."
            },
            "messageType": "conversation",
            "messageTimestamp": 1729500000
        }
    }

    with TestClient(app) as client:
        response = client.post(f"{settings.API_V1_STR}/listener/webhook", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["vendedor_id"] == "vendedor_juan"
        assert data["cliente_telefono"] == "+5491177778888"

    # Verificar directamente en la base de datos SQLite
    import asyncio
    async def verify_db():
        async with async_session_factory() as session:
            stmt = select(HistorialVendedor).where(
                HistorialVendedor.vendedor_id == "vendedor_juan",
                HistorialVendedor.cliente_telefono == "+5491177778888"
            )
            result = await session.execute(stmt)
            registro = result.scalars().first()
            assert registro is not None
            assert registro.mensaje == "Hola Juan, te consulto por el precio de las 5 licencias que hablamos."
            assert registro.tipo == "cliente"
            assert registro.timestamp is not None

    asyncio.run(verify_db())


def test_listener_webhook_outgoing_vendor_message():
    """
    Simula la respuesta del propio vendedor hacia el cliente (fromMe=True).
    El modo oyente debe guardar pasivamente la réplica del vendedor con tipo='vendedor'.
    """
    payload = {
        "event": "messages.upsert",
        "instance": "vendedor_juan",
        "data": {
            "key": {
                "remoteJid": "5491177778888@s.whatsapp.net",
                "fromMe": True,
                "id": "EVO_VENDEDOR_002"
            },
            "pushName": "Juan Vendedor",
            "message": {
                "conversation": "Hola Roberto, claro que sí, te salen $120.000 con soporte incluido."
            },
            "messageType": "conversation",
            "messageTimestamp": 1729500060
        }
    }

    with TestClient(app) as client:
        response = client.post(f"{settings.API_V1_STR}/listener/webhook", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"

    # Verificar registro en base de datos
    import asyncio
    async def verify_db():
        async with async_session_factory() as session:
            stmt = select(HistorialVendedor).where(
                HistorialVendedor.vendedor_id == "vendedor_juan",
                HistorialVendedor.tipo == "vendedor"
            )
            result = await session.execute(stmt)
            registro = result.scalars().first()
            assert registro is not None
            assert "120.000" in registro.mensaje
            assert registro.tipo == "vendedor"

    asyncio.run(verify_db())


def test_listener_webhook_with_path_param_vendor_id():
    """
    Verifica que se pueda invocar el webhook especificando el ID del vendedor
    en la ruta URL (/listener/webhook/{vendedor_id}).
    """
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {
                "remoteJid": "5491199990000@s.whatsapp.net",
                "fromMe": False,
                "id": "EVO_URL_003"
            },
            "message": {
                "conversation": "Buenas tardes, ¿tienen entrega inmediata?"
            }
        }
    }

    with TestClient(app) as client:
        response = client.post(
            f"{settings.API_V1_STR}/listener/webhook/vendedor_carlos",
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["vendedor_id"] == "vendedor_carlos"
        assert data["cliente_telefono"] == "+5491199990000"


def test_listener_webhook_silent_mode_does_not_reply_to_customer():
    """
    Verifica que el Módulo de Escucha Pasiva sea 100% SILENCIOSO:
    No debe invocar el cliente de WhatsApp para enviar mensajes ni interactuar con el cliente.
    """
    payload = {
        "event": "messages.upsert",
        "instance": "vendedor_silencioso",
        "data": {
            "key": {
                "remoteJid": "5491144445555@s.whatsapp.net",
                "fromMe": False,
                "id": "EVO_SILENT_004"
            },
            "message": {
                "conversation": "Quiero comprar ahora mismo."
            }
        }
    }

    # Interceptamos el método send_message del cliente de WhatsApp para comprobar que NO se invoque
    with patch("app.services.whatsapp_client.whatsapp_client.send_message", new_callable=AsyncMock) as mock_send:
        with TestClient(app) as client:
            response = client.post(f"{settings.API_V1_STR}/listener/webhook", json=payload)
            assert response.status_code == 200
            assert response.json()["status"] == "received"

        # Debe ser cero llamadas: silencio absoluto
        mock_send.assert_not_called()


def test_listener_gemini_context_endpoint():
    """
    Verifica el endpoint '/listener/gemini-context':
    Comprueba que devuelva la estructura de conversación organizada con roles,
    prompt especializado de auditoría y payload compatible con la API de Google Gemini.
    """
    with TestClient(app) as client:
        # 1. Enviar interacción previa entre vendedor y cliente
        client.post(
            f"{settings.API_V1_STR}/listener/webhook",
            json={
                "vendedor_id": "vendedor_auditoria",
                "cliente_telefono": "+5491133332222",
                "mensaje": "¿Cuánto me descuentan si compro 20 equipos?",
                "tipo": "cliente"
            }
        )
        client.post(
            f"{settings.API_V1_STR}/listener/webhook",
            json={
                "vendedor_id": "vendedor_auditoria",
                "cliente_telefono": "+5491133332222",
                "mensaje": "Podemos hacer un 15% de descuento por esa cantidad.",
                "tipo": "vendedor"
            }
        )

        # 2. Consultar el endpoint de estructuración para Gemini
        response = client.get(
            f"{settings.API_V1_STR}/listener/gemini-context",
            params={
                "vendedor_id": "vendedor_auditoria",
                "cliente_telefono": "+5491133332222"
            }
        )
        assert response.status_code == 200
        data = response.json()

        assert data["total_mensajes"] >= 2
        assert data["vendedor_id"] == "vendedor_auditoria"
        assert data["cliente_telefono"] == "+5491133332222"
        assert data["resumen_intercambio"]["cliente"] >= 1
        assert data["resumen_intercambio"]["vendedor"] >= 1
        
        # Validar componentes para Google Gemini
        assert "TRANSCRIPCIÓN DE LA CONVERSACIÓN" in data["prompt_recomendado_gemini"]
        assert len(data["gemini_contents_payload"]) > 0
        assert data["gemini_contents_payload"][0]["role"] == "user"
        assert "plantilla_analisis_sugerido" in data
        assert "desempeno_vendedor" in data["plantilla_analisis_sugerido"]


def test_main_routes_remain_unaltered_compra_and_cotizacion():
    """
    CRÍTICO: Verifica que la incorporación del Módulo de Escucha Pasiva
    NO altere ni rompa las rutas principales del sistema de compras y cotizaciones.
    """
    with TestClient(app) as client:
        # 1. Clasificador de intenciones comerciales (COMPRA)
        res_ai = client.post(
            f"{settings.API_V1_STR}/ai/classify",
            json={"text": "Quiero comprar ya mismo 3 licencias por favor, pasame el link de pago"}
        )
        assert res_ai.status_code == 200
        ai_data = res_ai.json()
        assert ai_data["intent"] == "COMPRA"

        # 2. Clasificador de intenciones comerciales (COTIZACION)
        res_cotiz = client.post(
            f"{settings.API_V1_STR}/ai/classify",
            json={"text": "Necesito presupuesto formal para presentar al directorio de la empresa"}
        )
        assert res_cotiz.status_code == 200
        cotiz_data = res_cotiz.json()
        assert cotiz_data["intent"] == "COTIZACION"

        # 3. Consulta de asesores comerciales configurados para COMPRA y COTIZACION
        res_routing = client.get(f"{settings.API_V1_STR}/routing/advisors")
        assert res_routing.status_code == 200
        routing_data = res_routing.json()
        assert routing_data["compra"]["name"] == settings.ADVISOR_PURCHASE_NAME
        assert routing_data["cotizacion"]["name"] == settings.ADVISOR_QUOTE_NAME

        # 4. Webhook principal de WhatsApp para atención de clientes sigue operativo
        res_wh = client.get(f"{settings.API_V1_STR}/webhooks/whatsapp")
        assert res_wh.status_code == 200
        assert res_wh.json()["status"] == "active"
