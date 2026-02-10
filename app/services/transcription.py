import asyncio
import logging
import re
import subprocess
from pathlib import Path

from app.config import settings
from app.schemas.capture import (
    FrameVoiceContext,
    RoomMention,
    TranscribedSegment,
    TranscribedWord,
    TranscriptionResult,
)

logger = logging.getLogger(__name__)

# Room-name trigger phrases (high confidence) and standalone names (lower confidence)
_TRIGGER_PHRASES = re.compile(
    r"\b(?:this is(?: the)?|entering(?: the)?|now in(?: the)?|here'?s(?: the)?|"
    r"moving (?:to|into)(?: the)?|we'?re in(?: the)?)\s+(.+?)(?:\.|,|$)",
    re.IGNORECASE,
)

_KNOWN_ROOMS = [
    "kitchen",
    "living room",
    "bedroom",
    "bathroom",
    "garage",
    "basement",
    "attic",
    "dining room",
    "office",
    "study",
    "laundry room",
    "pantry",
    "closet",
    "hallway",
    "entryway",
    "nursery",
    "guest room",
    "master bedroom",
    "den",
    "porch",
    "patio",
    "sunroom",
]

_KNOWN_ROOMS_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(r) for r in _KNOWN_ROOMS) + r")\b",
    re.IGNORECASE,
)


class TranscriptionService:
    def __init__(self):
        self._model = None

    def _get_model(self):
        """Lazy-load the whisper model on first use."""
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
        return self._model

    async def extract_audio(self, video_path: str | Path) -> Path | None:
        """Extract 16kHz mono WAV from video using ffmpeg. Returns None if no audio track."""
        video_path = Path(video_path)
        settings.audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = settings.audio_dir / f"{video_path.stem}.wav"

        # Check if video has an audio track
        probe_cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(video_path),
        ]
        try:
            result = await asyncio.to_thread(
                subprocess.run, probe_cmd, capture_output=True, text=True, timeout=30
            )
            if not result.stdout.strip():
                logger.info("No audio track found in %s", video_path.name)
                return None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("ffprobe failed or not found, skipping audio extraction")
            return None

        # Extract audio as 16kHz mono WAV
        extract_cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(audio_path),
        ]
        try:
            result = await asyncio.to_thread(
                subprocess.run, extract_cmd, capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                logger.error("ffmpeg audio extraction failed: %s", result.stderr[:500])
                return None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("ffmpeg failed or not found for audio extraction")
            return None

        if audio_path.exists() and audio_path.stat().st_size > 0:
            return audio_path
        return None

    async def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        """Transcribe audio with word-level timestamps via faster-whisper."""
        audio_path = Path(audio_path)
        model = self._get_model()

        segments_iter, info = await asyncio.to_thread(
            model.transcribe,
            str(audio_path),
            word_timestamps=True,
            vad_filter=True,
        )

        # Consume the generator in a thread since it does blocking work
        raw_segments = await asyncio.to_thread(list, segments_iter)

        segments = []
        full_words = []
        for seg in raw_segments:
            words = []
            for w in (seg.words or []):
                tw = TranscribedWord(
                    word=w.word.strip(),
                    start=w.start,
                    end=w.end,
                    probability=w.probability,
                )
                words.append(tw)
                full_words.append(tw)
            segments.append(TranscribedSegment(
                text=seg.text.strip(),
                start=seg.start,
                end=seg.end,
                words=words,
            ))

        full_text = " ".join(s.text for s in segments)

        return TranscriptionResult(
            segments=segments,
            full_text=full_text,
            language=info.language,
            duration=info.duration,
        )

    async def extract_and_transcribe(self, video_path: str | Path) -> TranscriptionResult | None:
        """Full pipeline: extract audio then transcribe. Returns None if no audio."""
        audio_path = await self.extract_audio(video_path)
        if audio_path is None:
            return None
        return await self.transcribe(audio_path)

    def correlate_to_frame(
        self,
        transcript: TranscriptionResult,
        frame_timestamp: float,
        frame_index: int = 0,
        window: float = 3.0,
    ) -> FrameVoiceContext:
        """Find words within a time window centered on the frame's timestamp."""
        half = window / 2.0
        t_start = frame_timestamp - half
        t_end = frame_timestamp + half

        matched_words = []
        for seg in transcript.segments:
            for w in seg.words:
                if w.end >= t_start and w.start <= t_end:
                    matched_words.append(w)

        snippet = " ".join(w.word for w in matched_words)

        return FrameVoiceContext(
            frame_index=frame_index,
            frame_timestamp=frame_timestamp,
            transcript_snippet=snippet,
            words=matched_words,
        )

    def correlate_all_frames(
        self,
        transcript: TranscriptionResult,
        frame_timestamps: list[tuple[int, float]],
        window: float = 3.0,
    ) -> list[FrameVoiceContext]:
        """Batch correlation for all frames. frame_timestamps = [(index, timestamp), ...]"""
        return [
            self.correlate_to_frame(transcript, ts, idx, window)
            for idx, ts in frame_timestamps
        ]

    def detect_room_mentions(self, transcript: TranscriptionResult) -> list[RoomMention]:
        """Detect room name mentions in the transcript."""
        mentions: list[RoomMention] = []
        seen: set[tuple[str, float]] = set()

        for seg in transcript.segments:
            text = seg.text

            # High-confidence: trigger phrase + room name
            for match in _TRIGGER_PHRASES.finditer(text):
                room_name = match.group(1).strip().lower()
                # Validate it looks like a room name (not too long, known or plausible)
                if len(room_name) > 40:
                    continue
                key = (room_name, round(seg.start, 1))
                if key not in seen:
                    seen.add(key)
                    mentions.append(RoomMention(
                        room_name=room_name,
                        timestamp=seg.start,
                        raw_text=text.strip(),
                        confidence=0.9,
                    ))

            # Lower-confidence: standalone known room names
            for match in _KNOWN_ROOMS_PATTERN.finditer(text):
                room_name = match.group(1).lower()
                key = (room_name, round(seg.start, 1))
                if key not in seen:
                    seen.add(key)
                    mentions.append(RoomMention(
                        room_name=room_name,
                        timestamp=seg.start,
                        raw_text=text.strip(),
                        confidence=0.7,
                    ))

        return mentions
