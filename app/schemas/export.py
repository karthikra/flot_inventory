from enum import StrEnum

from pydantic import BaseModel


class ExportFormat(StrEnum):
    CSV = "csv"
    PDF = "pdf"
    JSON = "json"


class ExportRequest(BaseModel):
    format: ExportFormat = ExportFormat.CSV
    room_ids: list[int] | None = None  # None = all rooms
    include_images: bool = True
    insurance_mode: bool = False


class ExportResult(BaseModel):
    file_path: str
    format: str
    item_count: int
    total_value: float
