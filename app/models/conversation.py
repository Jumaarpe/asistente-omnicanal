from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.message import Message


class Conversation(Base):
    """
    Representa una sesión o hilo de conversación de un cliente.
    Mantiene el estado comercial, el canal de entrada y la intención clasificada.
    """
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )
    channel: Mapped[str] = mapped_column(String(30), default="whatsapp", nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        default="open",
        nullable=False,
        comment="open, pending_classification, routed, closed"
    )
    intent: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="COMPRA, COTIZACION, OTRO"
    )
    intent_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    assigned_advisor: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relaciones
    customer: Mapped["Customer"] = relationship("Customer", back_populates="conversations")
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.timestamp"
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, customer_id={self.customer_id}, channel='{self.channel}', status='{self.status}', intent='{self.intent}')>"
