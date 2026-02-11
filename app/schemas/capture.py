from pydantic import BaseModel, Field


class DetectedObject(BaseModel):
    name: str
    description: str
    category: str = "other"
    is_book: bool = False
    needs_closer_look: bool = False
    closer_look_reason: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    estimated_value_usd: float | None = None
    condition: str | None = None
    bounding_box: list[float] | None = None  # [x1, y1, x2, y2] normalized
    voice_context: str | None = None
    # Product enrichment from vision
    brand: str | None = None
    model_number: str | None = None
    material: str | None = None
    estimated_dimensions_cm: dict | None = None  # {width, height, depth}


class BookDetail(BaseModel):
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    genre: str | None = None
    estimated_page_count: int | None = None


class DetailedDetection(DetectedObject):
    book_details: BookDetail | None = None
    visible_text: str | None = None
    barcode_present: bool = False


class FrameAnalysisResult(BaseModel):
    frame_index: int
    frame_path: str
    objects: list[DetectedObject] = []
    frame_timestamp: float = 0.0
    voice_context: str | None = None


class VideoProcessingStatus(BaseModel):
    session_id: int
    status: str  # extracting_frames, filtering, analyzing, deduplicating, done
    progress: float = Field(ge=0.0, le=1.0)
    total_frames: int = 0
    quality_frames: int = 0
    items_found: int = 0
    needs_closer_look: list[dict] = []
    message: str = ""


class ModeSwitchPrompt(BaseModel):
    reason: str
    items: list[str]  # descriptions of what needs closer capture
    suggested_action: str = "Switch to image mode for better detail"


class CaptureConfirmItem(BaseModel):
    name: str
    description: str | None = None
    category: str = "other"
    is_book: bool = False
    confidence_score: float | None = None
    estimated_value: float | None = None
    condition: str | None = None
    frame_path: str | None = None
    voice_context: str | None = None
    # Book-specific
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    genre: str | None = None
    # Product enrichment
    brand: str | None = None
    model_number: str | None = None
    material: str | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    depth_cm: float | None = None
    weight_kg: float | None = None
    replacement_cost: float | None = None
    purchase_date: str | None = None
    purchase_price: float | None = None


class CaptureConfirmRequest(BaseModel):
    session_id: int
    room_id: int
    items: list[CaptureConfirmItem]


# --- Voice / Transcription schemas ---


class TranscribedWord(BaseModel):
    word: str
    start: float
    end: float
    probability: float = 0.0


class TranscribedSegment(BaseModel):
    text: str
    start: float
    end: float
    words: list[TranscribedWord] = []


class TranscriptionResult(BaseModel):
    segments: list[TranscribedSegment] = []
    full_text: str = ""
    language: str = ""
    duration: float = 0.0


class FrameVoiceContext(BaseModel):
    frame_index: int
    frame_timestamp: float
    transcript_snippet: str = ""
    words: list[TranscribedWord] = []


class RoomMention(BaseModel):
    room_name: str
    timestamp: float
    raw_text: str
    confidence: float = 0.7
