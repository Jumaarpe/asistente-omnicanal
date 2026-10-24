from datetime import datetime, timezone
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime


class Base(DeclarativeBase):
    """
    Clase base declarativa para los modelos de SQLAlchemy 2.0.
    """
    pass
