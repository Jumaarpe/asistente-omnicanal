import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.database.session import init_db, async_session_factory
from app.models.customer import Customer
from app.models.conversation import Conversation
from app.schemas.ai import IntentClassificationResult
from app.services.routing_service import routing_service
from app.services.memory_service import memory_service


@pytest_asyncio.fixture(autouse=True)
async def setup_test_database():
    """Inicializa la base de datos antes de cada test."""
    await init_db()


def test_advisor_selection_by_intent():
    """Verifica que la asignación de asesores corresponda exactamente a la intención comercial."""
    purchase_advisor = routing_service.get_advisor_for_intent("COMPRA")
    assert purchase_advisor is not None
    assert purchase_advisor.department == "Ventas Directas"
    assert purchase_advisor.name == settings.ADVISOR_PURCHASE_NAME
    assert purchase_advisor.phone == settings.ADVISOR_PURCHASE_PHONE

    quote_advisor = routing_service.get_advisor_for_intent("COTIZACION")
    assert quote_advisor is not None
    assert quote_advisor.department == "Cuentas Corporativas"
    assert quote_advisor.name == settings.ADVISOR_QUOTE_NAME
    assert quote_advisor.phone == settings.ADVISOR_QUOTE_PHONE

    other_advisor = routing_service.get_advisor_for_intent("OTRO")
    assert other_advisor is None


def test_format_advisor_alert_contains_direct_whatsapp_link():
    """Verifica que la plantilla de alerta contenga formato enriquecido y enlace directo wa.me."""
    advisor = routing_service.get_advisor_for_intent("COMPRA")
    customer = Customer(id=1, phone="+5491133334444", name="Esteban Quito")
    conv = Conversation(id=10, customer_id=1, channel="whatsapp", status="open")
    
    classification = IntentClassificationResult(
        intent="COMPRA",
        confidence=0.95,
        reasoning="El cliente solicita link de pago para 10 licencias.",
        product_interest="Licencias Pro",
        quantity=10,
        urgency_level="alta",
        suggested_reply="Hola Esteban, te enviamos el link de pago."
    )

    lead_card = routing_service.build_lead_card(
        customer=customer,
        conversation=conv,
        classification=classification,
        advisor=advisor,
        last_message="Quiero comprar ya las 10 licencias"
    )

    alert_text = routing_service.format_advisor_alert(lead_card)
    assert "NUEVO LEAD CALIFICADO - COMPRA" in alert_text
    assert "Esteban Quito" in alert_text
    assert "+5491133334444" in alert_text
    assert "https://wa.me/5491133334444" in alert_text
    assert "Licencias Pro" in alert_text


@pytest.mark.asyncio
async def test_route_conversation_compra_flow():
    """Verifica el flujo completo de enrutamiento comercial para una intención de COMPRA."""
    test_phone = "+5491177770001"
    async with async_session_factory() as session:
        customer = await memory_service.get_or_create_customer(session, phone=test_phone, name="Cliente Compra")
        conv = await memory_service.get_or_create_active_conversation(session, customer_id=customer.id)
        
        classification = IntentClassificationResult(
            intent="COMPRA",
            confidence=0.92,
            reasoning="Intención directa de pago.",
            product_interest="Plan Anual",
            quantity=1,
            urgency_level="alta",
            suggested_reply="¡Hola! Con gusto te asistimos."
        )

        result = await routing_service.route_conversation(
            session=session,
            customer=customer,
            conversation=conv,
            classification=classification,
            last_message="Por favor pásame el link de pago para abonar hoy"
        )

        assert result.status == "routed"
        assert result.intent == "COMPRA"
        assert result.assigned_advisor.department == "Ventas Directas"
        assert result.alert_message_sent is True
        assert result.customer_notified is True

        # Verificar actualización en Base de Datos
        await session.refresh(conv)
        assert conv.status == "routed"
        assert conv.intent == "COMPRA"
        assert settings.ADVISOR_PURCHASE_NAME in conv.assigned_advisor


@pytest.mark.asyncio
async def test_route_conversation_skips_otro():
    """Verifica que mensajes sin intención comercial no disparen alertas a asesores."""
    test_phone = "+5491177770002"
    async with async_session_factory() as session:
        customer = await memory_service.get_or_create_customer(session, phone=test_phone, name="Cliente Saludo")
        conv = await memory_service.get_or_create_active_conversation(session, customer_id=customer.id)

        classification = IntentClassificationResult(
            intent="OTRO",
            confidence=0.90,
            reasoning="Solo es un saludo cordial.",
            urgency_level="baja",
            suggested_reply="¡Hola! ¿Cómo estás?"
        )

        result = await routing_service.route_conversation(
            session=session,
            customer=customer,
            conversation=conv,
            classification=classification,
            last_message="Hola buen día"
        )

        assert result.status == "skipped"
        assert result.assigned_advisor is None


@pytest.mark.asyncio
async def test_api_routing_leads_endpoint():
    """Verifica el endpoint GET /api/v1/routing/leads."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Consultar asesores
        res_adv = await client.get(f"{settings.API_V1_STR}/routing/advisors")
        assert res_adv.status_code == 200
        data_adv = res_adv.json()
        assert "compra" in data_adv
        assert "cotizacion" in data_adv

        # Consultar leads enrutados
        res_leads = await client.get(f"{settings.API_V1_STR}/routing/leads")
        assert res_leads.status_code == 200
        data_leads = res_leads.json()
        assert "count" in data_leads
        assert "leads" in data_leads
