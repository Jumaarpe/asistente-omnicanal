import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.services.ai_classifier import ai_classifier


@pytest.mark.asyncio
async def test_classify_compra_intent():
    """Verifica que un requerimiento de pago y compra directa se clasifique como COMPRA."""
    history = [
        {"role": "user", "content": "Buenas tardes, quiero comprar de inmediato 5 paquetes corporativos. ¿Cuál es el link de pago o CBU?"}
    ]
    result = await ai_classifier.classify_conversation(history, customer_name="Carlos Méndez")
    assert result.intent == "COMPRA"
    assert result.confidence >= 0.70
    assert result.urgency_level in ["alta", "media"]
    assert len(result.reasoning) > 0
    assert len(result.suggested_reply) > 0


@pytest.mark.asyncio
async def test_classify_cotizacion_intent():
    """Verifica que una solicitud de presupuesto formal se clasifique como COTIZACION."""
    history = [
        {"role": "user", "content": "Hola, solicito una cotización formal y desglosada con membrete para presentar a directorio antes de decidir la compra."}
    ]
    result = await ai_classifier.classify_conversation(history, customer_name="Empresa Andina")
    assert result.intent == "COTIZACION"
    assert result.confidence >= 0.70
    assert len(result.reasoning) > 0
    assert len(result.suggested_reply) > 0


@pytest.mark.asyncio
async def test_classify_otro_intent():
    """Verifica que saludos aislados o consultas fuera de foco se clasifiquen como OTRO."""
    history = [
        {"role": "user", "content": "Hola, buenos días, ¿cómo están?"}
    ]
    result = await ai_classifier.classify_conversation(history, customer_name="Juan")
    assert result.intent == "OTRO"
    assert len(result.suggested_reply) > 0


@pytest.mark.asyncio
async def test_classify_multiturn_context():
    """Verifica que el clasificador mantenga el contexto acumulado de múltiples turnos."""
    history = [
        {"role": "user", "content": "Hola, buen día"},
        {"role": "assistant", "content": "¡Hola! ¿En qué podemos ayudarte hoy?"},
        {"role": "user", "content": "Deseo pagar ahora mismo el plan premium para 2 personas."}
    ]
    result = await ai_classifier.classify_conversation(history, customer_name="Ana Clara")
    assert result.intent == "COMPRA"
    assert result.confidence >= 0.75


@pytest.mark.asyncio
async def test_ai_classify_http_endpoint():
    """Verifica el endpoint interactivo POST /api/v1/ai/classify."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "text": "Requiero un presupuesto detallado para evaluar con mis socios comerciales.",
            "customer_name": "Ing. Martín Peralta"
        }
        response = await client.post(f"{settings.API_V1_STR}/ai/classify", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "COTIZACION"
        assert data["confidence"] >= 0.70
        assert "suggested_reply" in data
