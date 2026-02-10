from pydantic import BaseModel, Field

from app.schemas.item import ItemOut


class BookCreate(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = None
    room_id: int
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    genre: str | None = None
    page_count: int | None = None
    year_published: int | None = None
    synopsis: str | None = None
    estimated_value: float | None = None
    condition: str | None = None


class BookUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    genre: str | None = None
    page_count: int | None = None
    year_published: int | None = None
    synopsis: str | None = None


class BookOut(ItemOut):
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    genre: str | None = None
    page_count: int | None = None
    year_published: int | None = None
    cover_image_path: str | None = None
    synopsis: str | None = None
