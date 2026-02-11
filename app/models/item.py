from datetime import datetime

from sqlalchemy import Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.tag import item_tags


class Item(Base, TimestampMixin):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(
        String(50), default="other"
    )  # electronics, furniture, kitchenware, books, clothing, tools, decor, appliances, sports, toys, other
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"))
    image_path: Mapped[str | None] = mapped_column(String(500))
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    estimated_value: Mapped[float | None] = mapped_column(Float)
    condition: Mapped[str | None] = mapped_column(
        Enum("new", "good", "fair", "poor", name="condition_enum")
    )
    status: Mapped[str | None] = mapped_column(
        Enum("keep", "sell", "donate", "trash", name="status_enum")
    )
    source_type: Mapped[str | None] = mapped_column(String(20))  # video_frame / image
    source_session_id: Mapped[int | None] = mapped_column(ForeignKey("capture_sessions.id"))
    voice_note: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(20), default="item")  # discriminator

    # Product enrichment fields
    brand: Mapped[str | None] = mapped_column(String(200))
    model_number: Mapped[str | None] = mapped_column(String(200))
    serial_number: Mapped[str | None] = mapped_column(String(200))
    material: Mapped[str | None] = mapped_column(String(200))
    width_cm: Mapped[float | None] = mapped_column(Float)
    height_cm: Mapped[float | None] = mapped_column(Float)
    depth_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    replacement_cost: Mapped[float | None] = mapped_column(Float)
    purchase_date: Mapped[str | None] = mapped_column(String(50))
    purchase_price: Mapped[float | None] = mapped_column(Float)

    __mapper_args__ = {
        "polymorphic_identity": "item",
        "polymorphic_on": "type",
    }

    room: Mapped["Room"] = relationship(back_populates="items")  # noqa: F821
    tags: Mapped[list["Tag"]] = relationship(secondary=item_tags, back_populates="items")  # noqa: F821
    images: Mapped[list["ItemImage"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class ItemImage(Base):
    __tablename__ = "item_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    image_path: Mapped[str] = mapped_column(String(500))
    image_type: Mapped[str] = mapped_column(
        String(20), default="front"
    )  # front, back, serial, damage, receipt
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    item: Mapped["Item"] = relationship(back_populates="images")
