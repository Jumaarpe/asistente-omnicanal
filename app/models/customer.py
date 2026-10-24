from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class Customer(Base):
    """
    Representa un cliente o prospecto (lead) que interactúa a través de WhatsApp o Voz.
    El teléfono internacional estandarizado actúa como identificador comercial principal.
    """
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)

    first_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relación con sus conversaciones históricas y activas
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation",
        back_populates="customer",
        cascade="all, delete-orphan",
        order_by="desc(Conversation.created_at)"
    )

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, phone='{self.phone}', name='{self.name}')>"
