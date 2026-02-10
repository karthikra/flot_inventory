from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.item import Item


class Book(Item):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(300))
    author: Mapped[str | None] = mapped_column(String(200))
    isbn: Mapped[str | None] = mapped_column(String(20), index=True)
    publisher: Mapped[str | None] = mapped_column(String(200))
    genre: Mapped[str | None] = mapped_column(String(100))
    page_count: Mapped[int | None] = mapped_column(Integer)
    year_published: Mapped[int | None] = mapped_column(Integer)
    cover_image_path: Mapped[str | None] = mapped_column(String(500))
    synopsis: Mapped[str | None] = mapped_column(Text)

    __mapper_args__ = {"polymorphic_identity": "book"}
