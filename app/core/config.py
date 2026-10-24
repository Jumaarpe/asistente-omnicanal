import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuración global de la aplicación basada en Pydantic Settings.
    Carga variables desde el entorno y/o archivo .env.
    """
    PROJECT_NAME: str = "Asistente Inteligente Omnicanal"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Configuración de Red / Servidor
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: List[str] = ["*"]

    # Seguridad y Verificación del Webhook
    # Utilizado para validar el webhook entrante de WhatsApp / Evolution API / Meta
    WEBHOOK_VERIFY_TOKEN: str = "webhook_token_secreto_mvp"
    WEBHOOK_API_KEY_HEADER: str = "X-Api-Key"
    WEBHOOK_API_KEY: str = ""

    # Proveedor de WhatsApp (evolution_api / meta_cloud / generic)
    WHATSAPP_PROVIDER: str = "evolution_api"
    EVOLUTION_API_URL: str = "http://localhost:8080"
    EVOLUTION_API_KEY: str = ""
    EVOLUTION_INSTANCE_NAME: str = "asistente-comercial"

    # Base de Datos y Memoria
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/assistant.db"
    CONVERSATION_EXPIRATION_HOURS: int = 24

    # Motor de Inteligencia Artificial (Google Gemini)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    CONFIDENCE_THRESHOLD: float = 0.70

    # Enrutamiento Comercial y Asesores (Día 4)
    ADVISOR_PURCHASE_NAME: str = "Martín - Ventas Directas"
    ADVISOR_PURCHASE_PHONE: str = "+5491111111111"
    ADVISOR_QUOTE_NAME: str = "Sofía - Cuentas Corporativas"
    ADVISOR_QUOTE_PHONE: str = "+5491122222222"
    AUTO_REPLY_CUSTOMER: bool = True
    SIMULATE_OUTGOING_WHATSAPP: bool = True

    # Nivel de Logs
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
