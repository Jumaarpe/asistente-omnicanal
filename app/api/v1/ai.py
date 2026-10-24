from fastapi import APIRouter, HTTPException, status
from app.schemas.ai import IntentClassificationResult, ClassificationRequest
from app.services.ai_classifier import ai_classifier

router = APIRouter(prefix="/ai", tags=["AI & Intent Classification"])


@router.post(
    "/classify",
    response_model=IntentClassificationResult,
    summary="Clasificar intención comercial con Google Gemini"
)
async def classify_intent(request: ClassificationRequest):
    """
    Endpoint interactivo para evaluar la clasificación de intenciones comerciales
    (COMPRA vs COTIZACIÓN vs OTRO) usando Google Gemini.
    """
    if not request.text and not request.history:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar al menos 'text' o 'history' para clasificar."
        )

    # Construir historial si se pasó texto simple
    history = request.history or []
    if request.text:
        history.append({"role": "user", "content": request.text})

    result = await ai_classifier.classify_conversation(
        history=history,
        customer_name=request.customer_name
    )

    return result
