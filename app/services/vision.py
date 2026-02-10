import base64
import json
from pathlib import Path

import anthropic

from app.config import settings
from app.schemas.capture import DetectedObject, DetailedDetection

BATCH_PROMPT = """Analyze this image of a room in a home. Identify every distinct object you can see.

For EACH object, return a JSON object with these fields:
- name: Short descriptive name (e.g., "Samsung 55-inch TV")
- description: 2-3 sentence description including color, material, brand if visible, size
- category: One of [electronics, furniture, kitchenware, books, clothing, tools, decor, appliances, sports, toys, other]
- is_book: true if this is a book, magazine, or printed material
- needs_closer_look: true if you cannot fully identify this item and a closer photo would help (partially hidden, text too small, barcode visible but unreadable)
- closer_look_reason: If needs_closer_look is true, explain why (e.g., "Book spine text is too small to read reliably")
- confidence: Float 0.0-1.0 of identification confidence
- estimated_value_usd: Rough replacement value estimate (null if uncertain)
- condition: One of [new, good, fair, poor] based on visible appearance
- bounding_box: [x1, y1, x2, y2] normalized coordinates (0-1) of object in image

Return ONLY a JSON array. Be thorough — include everything from large furniture to small items on shelves. Prefer being specific ("IKEA KALLAX shelf unit, white, 4x4") over generic ("bookshelf")."""

BATCH_PROMPT_WITH_VOICE = """Analyze this image of a room in a home. Identify every distinct object you can see.

The person recording this walkthrough narrated the following at this moment:
"{voice_context}"

Use their narration as additional context:
- If they mention a brand, model, or origin (e.g., "IKEA", "from Costco"), incorporate that into the object name and description
- If they describe an object's purpose or history, include it in the description
- When narration confirms what you see visually, increase your confidence score
- If narration mentions something you can't see clearly, still note it with moderate confidence

For EACH object, return a JSON object with these fields:
- name: Short descriptive name (e.g., "Samsung 55-inch TV")
- description: 2-3 sentence description including color, material, brand if visible, size
- category: One of [electronics, furniture, kitchenware, books, clothing, tools, decor, appliances, sports, toys, other]
- is_book: true if this is a book, magazine, or printed material
- needs_closer_look: true if you cannot fully identify this item and a closer photo would help
- closer_look_reason: If needs_closer_look is true, explain why
- confidence: Float 0.0-1.0 of identification confidence
- estimated_value_usd: Rough replacement value estimate (null if uncertain)
- condition: One of [new, good, fair, poor] based on visible appearance
- bounding_box: [x1, y1, x2, y2] normalized coordinates (0-1) of object in image
- voice_context: The relevant part of the narration that relates to this specific object (null if none)

Return ONLY a JSON array. Be thorough — include everything from large furniture to small items on shelves."""

DETAIL_PROMPT = """Look at this close-up image of a household item. Provide a detailed identification.

Return ONLY a JSON object with:
- name: Specific name including brand and model if visible
- description: Detailed 3-5 sentence description
- category: One of [electronics, furniture, kitchenware, books, clothing, tools, decor, appliances, sports, toys, other]
- is_book: true/false
- book_details: If is_book, include {title, author, isbn (if visible), publisher, genre, estimated_page_count}
- visible_text: Any text, serial numbers, model numbers you can read
- barcode_present: true if a barcode or QR code is visible
- needs_closer_look: false (this IS the close-up)
- confidence: Float 0.0-1.0
- estimated_value_usd: Replacement value estimate
- condition: One of [new, good, fair, poor] with brief justification"""


class VisionService:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.vision_model

    async def analyze_frame(
        self, image_path: str, voice_context: str | None = None
    ) -> list[DetectedObject]:
        """Analyze a single frame/image for multiple objects (video walkthrough mode)."""
        image_data = self._load_image_b64(image_path)
        media_type = self._get_media_type(image_path)

        if voice_context:
            prompt = BATCH_PROMPT_WITH_VOICE.format(voice_context=voice_context)
        else:
            prompt = BATCH_PROMPT

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": image_data},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )

        return self._parse_batch_response(response.content[0].text)

    async def analyze_detail(self, image_path: str) -> DetailedDetection:
        """Analyze a single close-up image for detailed identification."""
        image_data = self._load_image_b64(image_path)
        media_type = self._get_media_type(image_path)

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": image_data},
                        },
                        {"type": "text", "text": DETAIL_PROMPT},
                    ],
                }
            ],
        )

        return self._parse_detail_response(response.content[0].text)

    def _load_image_b64(self, image_path: str) -> str:
        return base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")

    def _get_media_type(self, image_path: str) -> str:
        ext = Path(image_path).suffix.lower()
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext, "image/jpeg")

    def _parse_batch_response(self, text: str) -> list[DetectedObject]:
        try:
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(text)
            if isinstance(data, list):
                return [DetectedObject(**obj) for obj in data]
            return [DetectedObject(**data)]
        except (json.JSONDecodeError, ValueError):
            return []

    def _parse_detail_response(self, text: str) -> DetailedDetection:
        try:
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(text)
            return DetailedDetection(**data)
        except (json.JSONDecodeError, ValueError):
            return DetailedDetection(
                name="Unknown item",
                description="Could not identify this item",
                confidence=0.0,
            )
