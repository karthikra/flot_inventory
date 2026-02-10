import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.book import Book
from app.models.capture_session import CaptureSession
from app.models.item import Item
from app.repositories.item_repo import ItemRepository
from app.repositories.room_repo import RoomRepository
from app.schemas.capture import (
    CaptureConfirmItem,
    DetectedObject,
    ModeSwitchPrompt,
    RoomMention,
)
from app.services.book_service import BookService
from app.services.image_service import ImageService
from app.services.transcription import TranscriptionService
from app.services.video_processor import VideoProcessor
from app.services.vision import VisionService


@dataclass
class CaptureViewModel:
    rooms: list = field(default_factory=list)
    session_id: int | None = None
    detected_items: list[DetectedObject] = field(default_factory=list)
    mode_switch_prompt: ModeSwitchPrompt | None = None
    status: str = "idle"  # idle, recording, uploading, processing, reviewing
    progress: float = 0.0
    message: str = ""

    @classmethod
    async def load(cls, session: AsyncSession) -> "CaptureViewModel":
        room_repo = RoomRepository(session)
        rooms = await room_repo.get_all()
        return cls(rooms=rooms)

    @classmethod
    async def start_session(cls, session: AsyncSession, room_id: int, mode: str = "video") -> CaptureSession:
        capture = CaptureSession(room_id=room_id, mode=mode)
        session.add(capture)
        await session.flush()
        await session.refresh(capture)
        await session.commit()
        return capture

    @classmethod
    async def process_video(
        cls,
        session: AsyncSession,
        session_id: int,
        video_data: bytes,
        progress_callback=None,
    ) -> tuple[list[DetectedObject], ModeSwitchPrompt | None, list[RoomMention]]:
        """Save video and run the full processing pipeline."""
        # save video to disk
        video_dir = settings.data_dir / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        video_path = video_dir / f"{uuid.uuid4().hex}.webm"
        video_path.write_bytes(video_data)

        # update session
        capture = await session.get(CaptureSession, session_id)
        if capture:
            capture.video_path = str(video_path)

        vision = VisionService()
        transcription = TranscriptionService()
        processor = VideoProcessor(vision, transcription)
        detected, mode_switch, _, transcript, room_mentions = await processor.process_video(
            str(video_path), session_id, progress_callback
        )

        if capture:
            capture.items_found = len(detected)
            capture.completed_at = datetime.now()
            if transcript:
                capture.has_audio = True
                capture.transcript_text = transcript.full_text
                capture.transcript_json = transcript.model_dump_json()
            await session.commit()

        return detected, mode_switch, room_mentions

    @classmethod
    async def process_image(
        cls,
        session: AsyncSession,
        session_id: int,
        image_data: bytes,
        room_name: str = "unsorted",
    ):
        """Process a single image capture."""
        img_service = ImageService()
        image_path, thumb_path = await img_service.save_upload(image_data, room_name)

        vision = VisionService()
        detected = await vision.analyze_frame(image_path)

        # check for books and try barcode scanning
        book_service = BookService()
        barcode = book_service.scan_barcode(image_path)
        if barcode:
            book_meta = await book_service.lookup_isbn(barcode)
            if book_meta:
                # enrich any book detections
                for obj in detected:
                    if obj.is_book:
                        obj.name = book_meta.get("title", obj.name)
                        obj.description = f"By {book_meta.get('author', 'Unknown')}. {obj.description}"

        return detected, image_path, thumb_path

    @classmethod
    async def confirm_items(
        cls,
        session: AsyncSession,
        room_id: int,
        session_id: int,
        items: list[CaptureConfirmItem],
    ) -> list[Item]:
        """Save confirmed detections to the database."""
        item_repo = ItemRepository(session)
        img_service = ImageService()

        room_repo = RoomRepository(session)
        room = await room_repo.get(room_id)
        room_name = room.name if room else "unsorted"

        saved = []
        for ci in items:
            # save frame as item image
            image_path = None
            thumb_path = None
            if ci.frame_path and Path(ci.frame_path).exists():
                image_path, thumb_path = img_service.save_image(
                    Path(ci.frame_path), room_name
                )

            if ci.is_book:
                book = Book(
                    name=ci.name,
                    description=ci.description,
                    category="books",
                    room_id=room_id,
                    image_path=image_path,
                    thumbnail_path=thumb_path,
                    confidence_score=ci.confidence_score,
                    estimated_value=ci.estimated_value,
                    condition=ci.condition,
                    source_type="video_frame" if session_id else "image",
                    source_session_id=session_id,
                    type="book",
                    title=ci.title,
                    author=ci.author,
                    isbn=ci.isbn,
                    publisher=ci.publisher,
                    genre=ci.genre,
                    voice_note=ci.voice_context,
                )
                session.add(book)
                await session.flush()
                saved.append(book)
            else:
                item = await item_repo.create(
                    name=ci.name,
                    description=ci.description,
                    category=ci.category,
                    room_id=room_id,
                    image_path=image_path,
                    thumbnail_path=thumb_path,
                    confidence_score=ci.confidence_score,
                    estimated_value=ci.estimated_value,
                    condition=ci.condition,
                    source_type="video_frame" if session_id else "image",
                    source_session_id=session_id,
                    voice_note=ci.voice_context,
                )
                saved.append(item)

        await session.commit()
        return saved
