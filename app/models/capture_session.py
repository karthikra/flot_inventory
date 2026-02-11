from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CaptureSession(Base):
    __tablename__ = "capture_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    mode: Mapped[str] = mapped_column(
        Enum("video", "image", "rapid", "scan", name="capture_mode_enum"), default="video"
    )
    video_path: Mapped[str | None] = mapped_column(String(500))
    audio_path: Mapped[str | None] = mapped_column(String(500))
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    transcript_json: Mapped[str | None] = mapped_column(Text)
    transcript_text: Mapped[str | None] = mapped_column(Text)
    frame_count: Mapped[int] = mapped_column(Integer, default=0)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column()

    room: Mapped["Room"] = relationship(back_populates="capture_sessions")  # noqa: F821
