from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Category(StrEnum):
    ELECTRONICS = "electronics"
    FURNITURE = "furniture"
    KITCHENWARE = "kitchenware"
    BOOKS = "books"
    CLOTHING = "clothing"
    TOOLS = "tools"
    DECOR = "decor"
    APPLIANCES = "appliances"
    SPORTS = "sports"
    TOYS = "toys"
    OTHER = "other"


class Condition(StrEnum):
    NEW = "new"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class ItemStatus(StrEnum):
    KEEP = "keep"
    SELL = "sell"
    DONATE = "donate"
    TRASH = "trash"


class ItemCreate(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = None
    category: Category = Category.OTHER
    room_id: int
    estimated_value: float | None = None
    condition: Condition | None = None
    status: ItemStatus | None = None
    source_type: str | None = None
    source_session_id: int | None = None


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    category: Category | None = None
    room_id: int | None = None
    estimated_value: float | None = None
    condition: Condition | None = None
    status: ItemStatus | None = None


class ItemImageOut(BaseModel):
    id: int
    image_path: str
    image_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ItemOut(BaseModel):
    id: int
    name: str
    description: str | None
    category: str
    room_id: int
    image_path: str | None
    thumbnail_path: str | None
    confidence_score: float | None
    estimated_value: float | None
    condition: str | None
    status: str | None
    source_type: str | None
    type: str
    created_at: datetime
    updated_at: datetime
    images: list[ItemImageOut] = []
    tags: list[str] = []

    model_config = {"from_attributes": True}
