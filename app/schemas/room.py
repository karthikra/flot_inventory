from datetime import datetime

from pydantic import BaseModel, Field


class RoomCreate(BaseModel):
    name: str = Field(max_length=100)
    description: str | None = None
    floor: int = 1


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    floor: int | None = None
    floor_plan_data: str | None = None


class RoomOut(BaseModel):
    id: int
    name: str
    description: str | None
    floor: int
    floor_plan_data: str | None
    created_at: datetime
    updated_at: datetime
    item_count: int = 0
    total_value: float = 0.0

    model_config = {"from_attributes": True}
