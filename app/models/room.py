from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Room(Base, TimestampMixin):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    floor: Mapped[int] = mapped_column(default=1)
    floor_plan_data: Mapped[str | None] = mapped_column(Text)  # JSON for drag-and-drop layout

    items: Mapped[list["Item"]] = relationship(back_populates="room", cascade="all, delete-orphan")  # noqa: F821
    capture_sessions: Mapped[list["CaptureSession"]] = relationship(back_populates="room")  # noqa: F821
