from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class Message(Base):
    """
    Representa un mensaje individual (entrante o saliente) dentro de una conversación.
    Preserva el historial exacto cronológico para alimentar la memoria del LLM.
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    message_id_origin: Mapped[Optional[str]] = mapped_column(
        String(100),
        index=True,
        nullable=True,
        comment="ID asignado por WhatsApp o Vapi"
    )
    sender_role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="customer, assistant, system, advisor"
    )
    message_type: Mapped[str] = mapped_column(
        String(20),
        default="text",
        nullable=False,
        comment="text, audio, image"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    raw_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relación
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, conv_id={self.conversation_id}, role='{self.sender_role}', snippet='{self.content[:30]}...')>"
