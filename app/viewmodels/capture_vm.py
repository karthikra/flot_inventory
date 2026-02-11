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
    FrameAnalysisResult,
    ModeSwitchPrompt,
    RoomMention,
)
from app.services.book_service import BookService
from app.services.image_service import ImageService
from app.services.transcription import TranscriptionService
from app.services.video_processor import VideoProcessor
from app.services.local_vision import LocalVisionService


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

        vision = LocalVisionService()
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
        audio_data: bytes | None = None,
    ):
        """Process a single image capture, optionally with voice narration."""
        import asyncio
        import logging
        import subprocess

        img_service = ImageService()
        image_path, thumb_path = await img_service.save_upload(image_data, room_name)

        # Transcribe audio if provided
        voice_context = None
        if audio_data and len(audio_data) > 1000:
            try:
                tmp_dir = settings.data_dir / "tmp"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                audio_raw = tmp_dir / f"img_audio_{uuid.uuid4().hex}.webm"
                audio_wav = tmp_dir / f"img_audio_{uuid.uuid4().hex}.wav"
                audio_raw.write_bytes(audio_data)

                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "ffmpeg", "-y", "-i", str(audio_raw),
                        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                        str(audio_wav),
                    ],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0 and audio_wav.exists():
                    transcription_svc = TranscriptionService()
                    transcript = await transcription_svc.transcribe(audio_wav)
                    if transcript and transcript.full_text.strip():
                        voice_context = transcript.full_text.strip()

                # Clean up temp files
                audio_raw.unlink(missing_ok=True)
                audio_wav.unlink(missing_ok=True)
            except Exception:
                logging.getLogger(__name__).exception("Image audio transcription failed")

        vision = LocalVisionService()
        detected = await vision.analyze_frame(image_path, voice_context=voice_context)

        # Attach voice context to all detected objects
        if voice_context:
            for obj in detected:
                obj.voice_context = voice_context

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
    async def process_rapid_capture(
        cls,
        session: AsyncSession,
        session_id: int,
        snap_images: list[bytes],
        timestamps: list[float],
        audio_data: bytes | None = None,
        room_name: str = "unsorted",
        progress_callback=None,
    ) -> tuple[list[DetectedObject], list["RoomMention"]]:
        """Process rapid capture: analyze snaps, optionally transcribe audio, deduplicate."""
        import asyncio
        import logging
        import subprocess

        rapid_dir = settings.data_dir / "rapid" / str(session_id)
        rapid_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            await progress_callback("saving", 0.05, f"Saving {len(snap_images)} snapshots...", {})

        # Save snap JPEGs to disk
        snap_paths: list[str] = []
        for i, img_data in enumerate(snap_images):
            snap_path = rapid_dir / f"snap_{i:04d}.jpg"
            snap_path.write_bytes(img_data)
            snap_paths.append(str(snap_path))

        # Transcribe audio if provided
        transcript = None
        room_mentions: list[RoomMention] = []
        if audio_data and len(audio_data) > 1000:
            if progress_callback:
                await progress_callback("transcribing", 0.1, "Transcribing audio narration...", {})

            # Save audio and convert to WAV via ffmpeg
            audio_ext = "webm"
            audio_raw = rapid_dir / f"audio.{audio_ext}"
            audio_raw.write_bytes(audio_data)
            audio_wav = rapid_dir / "audio.wav"

            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "ffmpeg", "-y", "-i", str(audio_raw),
                        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                        str(audio_wav),
                    ],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0 and audio_wav.exists():
                    transcription_svc = TranscriptionService()
                    transcript = await transcription_svc.transcribe(audio_wav)
                    room_mentions = transcription_svc.detect_room_mentions(transcript)
            except Exception:
                logging.getLogger(__name__).exception("Rapid capture audio transcription failed")

        # Build voice contexts for each snap
        voice_contexts: dict[int, str] = {}
        if transcript and timestamps:
            transcription_svc = TranscriptionService()
            frame_timestamps = [(i, ts) for i, ts in enumerate(timestamps)]
            correlations = transcription_svc.correlate_all_frames(transcript, frame_timestamps)
            for ctx in correlations:
                if ctx.transcript_snippet.strip():
                    voice_contexts[ctx.frame_index] = ctx.transcript_snippet

        if progress_callback:
            await progress_callback(
                "analyzing", 0.2,
                f"Analyzing {len(snap_paths)} snapshots...",
                {"total_snaps": len(snap_paths)},
            )

        # Analyze each snap
        vision = LocalVisionService()
        all_results = []
        for i, snap_path in enumerate(snap_paths):
            vc = voice_contexts.get(i)
            objects = await vision.analyze_frame(snap_path, voice_context=vc)
            all_results.append(FrameAnalysisResult(
                frame_index=i,
                frame_path=snap_path,
                objects=objects,
                frame_timestamp=timestamps[i] if i < len(timestamps) else 0.0,
                voice_context=vc,
            ))
            if progress_callback:
                pct = 0.2 + (0.6 * (i + 1) / len(snap_paths))
                found = sum(len(r.objects) for r in all_results)
                await progress_callback(
                    "analyzing", pct,
                    f"Analyzed {i + 1}/{len(snap_paths)} snapshots. Found {found} items.",
                    {"items_found": found},
                )

        if progress_callback:
            await progress_callback("deduplicating", 0.85, "Removing duplicate detections...", {})

        # Deduplicate across snaps using VideoProcessor's logic
        processor = VideoProcessor(vision)
        deduplicated = processor._deduplicate_objects(all_results)

        # Update capture session
        capture = await session.get(CaptureSession, session_id)
        if capture:
            capture.items_found = len(deduplicated)
            capture.frame_count = len(snap_paths)
            capture.completed_at = datetime.now()
            if transcript:
                capture.has_audio = True
                capture.transcript_text = transcript.full_text
                capture.transcript_json = transcript.model_dump_json()
            await session.commit()

        if progress_callback:
            await progress_callback("done", 1.0, f"Done! Identified {len(deduplicated)} unique items.", {
                "items_found": len(deduplicated),
            })

        return deduplicated, room_mentions

    @classmethod
    async def process_scan_frame(
        cls,
        session: AsyncSession,
        session_id: int,
        image_data: bytes,
    ) -> tuple[list[DetectedObject], str]:
        """Analyze a single scan frame. Returns (objects, frame_path)."""
        scan_dir = settings.data_dir / "scan" / str(session_id)
        scan_dir.mkdir(parents=True, exist_ok=True)

        # Find next frame number
        existing = list(scan_dir.glob("frame_*.jpg"))
        frame_num = len(existing)
        frame_path = scan_dir / f"frame_{frame_num:04d}.jpg"
        frame_path.write_bytes(image_data)

        vision = LocalVisionService()
        detected = await vision.analyze_frame(str(frame_path))

        # Attach frame_path to each object for review
        for obj in detected:
            if not obj.bounding_box:
                obj.bounding_box = []

        return detected, str(frame_path)

    @classmethod
    async def process_scan_complete(
        cls,
        session: AsyncSession,
        session_id: int,
        video_data: bytes | None,
        items_json: list[dict],
        timestamps: list[float],
        audio_data: bytes | None = None,
        room_name: str = "unsorted",
    ) -> tuple[list[DetectedObject], list[RoomMention]]:
        """Finalize a scan session: save video, transcribe audio, deduplicate items."""
        import asyncio
        import logging
        import subprocess

        # Save full video if provided
        video_path = None
        if video_data and len(video_data) > 1000:
            video_dir = settings.data_dir / "videos"
            video_dir.mkdir(parents=True, exist_ok=True)
            video_path = video_dir / f"{uuid.uuid4().hex}.webm"
            video_path.write_bytes(video_data)

        # Transcribe audio if provided
        transcript = None
        room_mentions: list[RoomMention] = []
        if audio_data and len(audio_data) > 1000:
            try:
                scan_dir = settings.data_dir / "scan" / str(session_id)
                scan_dir.mkdir(parents=True, exist_ok=True)
                audio_raw = scan_dir / "audio.webm"
                audio_wav = scan_dir / "audio.wav"
                audio_raw.write_bytes(audio_data)

                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "ffmpeg", "-y", "-i", str(audio_raw),
                        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                        str(audio_wav),
                    ],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0 and audio_wav.exists():
                    transcription_svc = TranscriptionService()
                    transcript = await transcription_svc.transcribe(audio_wav)
                    room_mentions = transcription_svc.detect_room_mentions(transcript)
            except Exception:
                logging.getLogger(__name__).exception("Scan audio transcription failed")

        # Build voice contexts per frame from timestamps
        voice_contexts: dict[int, str] = {}
        if transcript and timestamps:
            transcription_svc = TranscriptionService()
            frame_timestamps = [(i, ts) for i, ts in enumerate(timestamps)]
            correlations = transcription_svc.correlate_all_frames(transcript, frame_timestamps)
            for ctx in correlations:
                if ctx.transcript_snippet.strip():
                    voice_contexts[ctx.frame_index] = ctx.transcript_snippet

        # Reconstruct DetectedObjects from accumulated JSON
        all_objects: list[DetectedObject] = []
        for item_dict in items_json:
            obj = DetectedObject(**item_dict)
            all_objects.append(obj)

        # Build FrameAnalysisResults for dedup (group objects by frame_path)
        frame_groups: dict[str, list[DetectedObject]] = {}
        for obj_dict, obj in zip(items_json, all_objects):
            fp = obj_dict.get("frame_path", "")
            frame_groups.setdefault(fp, []).append(obj)

        frame_results: list[FrameAnalysisResult] = []
        for i, (fp, objs) in enumerate(frame_groups.items()):
            vc = voice_contexts.get(i)
            if vc:
                for obj in objs:
                    if not obj.voice_context:
                        obj.voice_context = vc
            frame_results.append(FrameAnalysisResult(
                frame_index=i,
                frame_path=fp,
                objects=objs,
                frame_timestamp=timestamps[i] if i < len(timestamps) else 0.0,
                voice_context=vc,
            ))

        # Deduplicate
        vision = LocalVisionService()
        processor = VideoProcessor(vision)
        deduplicated = processor._deduplicate_objects(frame_results)

        # Update capture session
        capture = await session.get(CaptureSession, session_id)
        if capture:
            capture.items_found = len(deduplicated)
            capture.frame_count = len(frame_results)
            capture.completed_at = datetime.now()
            if video_path:
                capture.video_path = str(video_path)
            if transcript:
                capture.has_audio = True
                capture.transcript_text = transcript.full_text
                capture.transcript_json = transcript.model_dump_json()
            await session.commit()

        return deduplicated, room_mentions

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

            # Common enrichment kwargs
            enrichment = {
                "brand": ci.brand,
                "model_number": ci.model_number,
                "material": ci.material,
                "width_cm": ci.width_cm,
                "height_cm": ci.height_cm,
                "depth_cm": ci.depth_cm,
                "weight_kg": ci.weight_kg,
                "replacement_cost": ci.replacement_cost,
                "purchase_date": ci.purchase_date,
                "purchase_price": ci.purchase_price,
            }

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
                    **enrichment,
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
                    **enrichment,
                )
                saved.append(item)

        await session.commit()
        return saved
