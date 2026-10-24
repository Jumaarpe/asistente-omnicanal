from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


class EvolutionMessageKey(BaseModel):
    remoteJid: str
    fromMe: bool = False
    id: str
    participant: Optional[str] = None


class EvolutionMessageContent(BaseModel):
    conversation: Optional[str] = None
    extendedTextMessage: Optional[Dict[str, Any]] = None
    audioMessage: Optional[Dict[str, Any]] = None
    imageMessage: Optional[Dict[str, Any]] = None


class EvolutionMessageData(BaseModel):
    key: EvolutionMessageKey
    pushName: Optional[str] = None
    message: Optional[Dict[str, Any]] = None
    messageType: Optional[str] = None
    messageTimestamp: Optional[int] = None
    source: Optional[str] = None


class EvolutionWebhookPayload(BaseModel):
    """
    Estructura de evento emitida por Evolution API (v1 / v2).
    Evento típico: 'messages.upsert'
    """
    event: Optional[str] = "messages.upsert"
    instance: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    destination: Optional[str] = None
    date_time: Optional[str] = None
    sender: Optional[str] = None
    model_config = ConfigDict(extra="allow")
