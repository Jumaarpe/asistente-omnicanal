from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class HistorialVendedor(Base):
    """
    Tabla de escucha pasiva / modo oyente para vendedores humanos.
    Almacena los mensajes intercambiados entre vendedores y clientes en tiempo real
    sin intervenir ni responder automáticamente.
    
    Permite auditar conversaciones, detectar oportunidades y recopilar historial
    para análisis estructurado con Google Gemini.
    """
    __tablename__ = "historial_vendedores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendedor_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
        comment="Identificador del vendedor o instancia de Evolution API"
    )
    cliente_telefono: Mapped[str] = mapped_column(
        String(50),
        index=True,
        nullable=False,
        comment="Número de teléfono del cliente en formato internacional"
    )
    mensaje: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Texto del mensaje intercambiado"
    )
    tipo: Mapped[str] = mapped_column(
        String(50),
        default="cliente",
        nullable=False,
        comment="Indica el origen o rol del emisor: 'cliente' o 'vendedor' (o tipo de mensaje)"
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Marca de tiempo UTC del mensaje"
    )

    def __repr__(self) -> str:
        return (
            f"<HistorialVendedor(id={self.id}, vendedor='{self.vendedor_id}', "
            f"cliente='{self.cliente_telefono}', tipo='{self.tipo}', snippet='{self.mensaje[:25]}...')>"
        )
