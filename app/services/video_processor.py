import asyncio
import logging
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image

from app.config import settings
from app.schemas.capture import (
    DetectedObject,
    FrameAnalysisResult,
    ModeSwitchPrompt,
    RoomMention,
    TranscriptionResult,
)
from app.services.transcription import TranscriptionService
from app.services.vision import VisionService

logger = logging.getLogger(__name__)


class VideoProcessor:
    def __init__(
        self,
        vision_service: VisionService,
        transcription_service: TranscriptionService | None = None,
    ):
        self.vision = vision_service
        self.transcription = transcription_service
        self.frames_dir = settings.data_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)

    async def process_video(self, video_path: str, session_id: int, progress_callback=None):
        """Full pipeline: extract frames + transcribe (parallel) -> filter -> correlate -> analyze -> deduplicate.

        progress_callback(status, progress, message, data) is called at each stage.
        Returns (deduplicated_objects, mode_switch, all_results, transcript, room_mentions).
        """
        if progress_callback:
            await progress_callback("extracting_frames", 0.0, "Extracting frames from video...", {})

        # Run frame extraction and transcription in parallel
        frame_task = asyncio.create_task(self._extract_frames(video_path, session_id))
        transcript_task = asyncio.create_task(self._safe_transcribe(video_path, progress_callback))

        frames_with_ts = await frame_task
        total_frames = len(frames_with_ts)

        if progress_callback:
            await progress_callback(
                "filtering", 0.15,
                f"Extracted {total_frames} frames. Filtering quality...",
                {"total_frames": total_frames},
            )

        quality_frames = self._filter_quality_frames(frames_with_ts)
        quality_count = len(quality_frames)

        # Await transcription result
        transcript = await transcript_task

        # Build voice contexts for each frame
        voice_contexts: dict[int, str] = {}
        room_mentions: list[RoomMention] = []
        if transcript and self.transcription:
            frame_timestamps = [(i, ts) for i, (_, ts) in enumerate(quality_frames)]
            correlations = self.transcription.correlate_all_frames(transcript, frame_timestamps)
            for ctx in correlations:
                if ctx.transcript_snippet.strip():
                    voice_contexts[ctx.frame_index] = ctx.transcript_snippet
            room_mentions = self.transcription.detect_room_mentions(transcript)

        if progress_callback:
            voice_msg = ""
            if transcript:
                seg_count = len(transcript.segments)
                voice_msg = f" Transcribed {seg_count} segments ({transcript.duration:.1f}s audio)."
            await progress_callback(
                "analyzing", 0.3,
                f"Analyzing {quality_count} quality frames...{voice_msg}",
                {"quality_frames": quality_count},
            )

        all_results: list[FrameAnalysisResult] = []
        for i, (frame_path, frame_ts) in enumerate(quality_frames):
            vc = voice_contexts.get(i)
            objects = await self.vision.analyze_frame(str(frame_path), voice_context=vc)
            all_results.append(FrameAnalysisResult(
                frame_index=i,
                frame_path=str(frame_path),
                objects=objects,
                frame_timestamp=frame_ts,
                voice_context=vc,
            ))
            if progress_callback:
                pct = 0.3 + (0.5 * (i + 1) / quality_count)
                found = sum(len(r.objects) for r in all_results)
                await progress_callback(
                    "analyzing", pct,
                    f"Analyzed {i + 1}/{quality_count} frames. Found {found} items.",
                    {"items_found": found},
                )

        if progress_callback:
            await progress_callback("deduplicating", 0.85, "Removing duplicate detections...", {})

        deduplicated = self._deduplicate_objects(all_results)
        needs_closer = [obj for obj in deduplicated if obj.needs_closer_look]

        mode_switch = None
        if needs_closer:
            mode_switch = ModeSwitchPrompt(
                reason=f"Found {len(needs_closer)} items that need closer inspection",
                items=[f"{obj.name}: {obj.closer_look_reason}" for obj in needs_closer],
            )

        if progress_callback:
            await progress_callback("done", 1.0, f"Done! Identified {len(deduplicated)} unique items.", {
                "items_found": len(deduplicated),
                "needs_closer_look": len(needs_closer),
            })

        return deduplicated, mode_switch, all_results, transcript, room_mentions

    async def _safe_transcribe(
        self, video_path: str, progress_callback=None
    ) -> TranscriptionResult | None:
        """Wrap transcription with error handling so failures don't break the pipeline."""
        if not self.transcription:
            return None
        try:
            if progress_callback:
                await progress_callback(
                    "transcribing", 0.05, "Transcribing audio narration...", {}
                )
            result = await self.transcription.extract_and_transcribe(video_path)
            if result and progress_callback:
                await progress_callback(
                    "transcribing", 0.12,
                    f"Transcribed {len(result.segments)} segments ({result.duration:.1f}s audio)",
                    {},
                )
            return result
        except Exception:
            logger.exception("Transcription failed, continuing without voice context")
            return None

    async def _extract_frames(
        self, video_path: str, session_id: int
    ) -> list[tuple[Path, float]]:
        """Extract frames from video at configured FPS rate. Returns (path, timestamp) pairs."""
        session_dir = self.frames_dir / str(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_interval = int(fps / settings.video_fps_extract)
        frame_interval = max(1, frame_interval)

        frames: list[tuple[Path, float]] = []
        frame_idx = 0
        saved_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % frame_interval == 0:
                timestamp = frame_idx / fps
                frame_path = session_dir / f"frame_{saved_idx:04d}.jpg"
                cv2.imwrite(str(frame_path), frame)
                frames.append((frame_path, timestamp))
                saved_idx += 1
            frame_idx += 1
            if frame_idx % 100 == 0:
                await asyncio.sleep(0)

        cap.release()
        return frames

    def _filter_quality_frames(
        self, frames: list[tuple[Path, float]]
    ) -> list[tuple[Path, float]]:
        """Remove blurry and near-duplicate frames. Preserves (path, timestamp) pairs."""
        quality_frames: list[tuple[Path, float]] = []
        seen_hashes: list[imagehash.ImageHash] = []

        for frame_path, timestamp in frames:
            img = cv2.imread(str(frame_path))
            if img is None:
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            if laplacian_var < settings.blur_threshold:
                continue

            pil_img = Image.open(frame_path)
            phash = imagehash.phash(pil_img)
            is_duplicate = any(abs(phash - h) < 10 for h in seen_hashes)
            if is_duplicate:
                continue

            seen_hashes.append(phash)
            quality_frames.append((frame_path, timestamp))

        return quality_frames

    def _deduplicate_objects(self, results: list[FrameAnalysisResult]) -> list[DetectedObject]:
        """Merge objects detected across multiple frames."""
        from rapidfuzz import fuzz

        all_objects: list[tuple[DetectedObject, str]] = []
        for result in results:
            for obj in result.objects:
                all_objects.append((obj, result.frame_path))

        if not all_objects:
            return []

        merged: list[DetectedObject] = []
        used = [False] * len(all_objects)

        for i, (obj_a, _) in enumerate(all_objects):
            if used[i]:
                continue
            best = obj_a
            used[i] = True
            for j in range(i + 1, len(all_objects)):
                if used[j]:
                    continue
                obj_b = all_objects[j][0]
                name_sim = fuzz.ratio(obj_a.name.lower(), obj_b.name.lower())
                desc_sim = fuzz.ratio(
                    (obj_a.description or "").lower(),
                    (obj_b.description or "").lower(),
                )
                if name_sim > 80 or (name_sim > 60 and desc_sim > 70):
                    used[j] = True
                    if obj_b.confidence > best.confidence:
                        best = obj_b
            merged.append(best)

        return merged
