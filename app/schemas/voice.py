from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field


class VapiCustomer(BaseModel):
    number: Optional[str] = None
    name: Optional[str] = None


class VapiCall(BaseModel):
    id: str
    customer: Optional[VapiCustomer] = None
    phoneNumberId: Optional[str] = None
    status: Optional[str] = None
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None


class VapiWebhookPayload(BaseModel):
    """
    Estructura típica de webhook de Vapi AI (end-of-call-report o message wrapper).
    """
    type: Optional[str] = None
    call: Optional[VapiCall] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    recordingUrl: Optional[str] = None
    cost: Optional[float] = None
    message: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}


class RetellTranscriptUtterance(BaseModel):
    role: str
    content: str


class RetellCallAnalysis(BaseModel):
    call_summary: Optional[str] = None
    user_sentiment: Optional[str] = None
    custom_analysis_data: Optional[Dict[str, Any]] = None


class RetellWebhookPayload(BaseModel):
    """
    Estructura típica de webhook de Retell AI (call_analyzed, call_ended).
    """
    event: Optional[str] = None
    call_id: Optional[str] = None
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    transcript: Optional[str] = None
    transcript_object: Optional[List[Dict[str, Any]]] = None
    recording_url: Optional[str] = None
    call_analysis: Optional[RetellCallAnalysis] = None
    metadata: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}


class VoiceCallNormalizedResult(BaseModel):
    """
    Resultado del parseo y extracción de la llamada de voz.
    """
    provider: Literal["vapi", "retell", "generic"]
    call_id: str
    customer_phone: str
    customer_name: Optional[str] = None
    transcript: str
    summary: Optional[str] = None
    recording_url: Optional[str] = None
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
