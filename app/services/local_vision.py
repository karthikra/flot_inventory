import base64
import json
import logging
from pathlib import Path

import cv2
import httpx
import numpy as np

from app.config import settings
from app.schemas.capture import DetectedObject

logger = logging.getLogger(__name__)

# Prompt for Qwen2.5-VL requesting structured JSON with bounding boxes
QWEN_PROMPT = """Identify every distinct object visible in this image.
For each object, return a JSON object with these fields:
- "name": specific descriptive name (include brand/model/color if visible)
- "description": 1-2 sentences about color, material, size, condition
- "category": one of [electronics, furniture, kitchenware, books, clothing, tools, decor, appliances, sports, toys, musical_instruments, other]
- "is_book": true only if it's a book or printed material
- "bbox_2d": [x1, y1, x2, y2] pixel coordinates of the bounding box

Return ONLY a JSON array, no other text. Example:
[{"name": "Black floor lamp", "description": "Tall adjustable metal floor lamp with matte black finish and fabric shade.", "category": "decor", "is_book": false, "bbox_2d": [120, 50, 340, 580]}]"""

# Category inference from YOLO-World vocabulary names
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "furniture": [
        "chair", "couch", "sofa", "table", "desk", "bed", "shelf", "bookshelf",
        "cabinet", "dresser", "nightstand", "bench", "stool", "ottoman", "recliner",
        "wardrobe", "tv stand", "coffee table", "dining table", "end table",
    ],
    "electronics": [
        "tv", "monitor", "laptop", "keyboard", "mouse", "speaker", "headphones",
        "remote", "phone", "tablet", "game console", "router", "camera",
    ],
    "kitchenware": [
        "pot", "pan", "plate", "bowl", "cup", "mug", "glass", "bottle",
        "cutting board", "knife block",
    ],
    "appliances": [
        "refrigerator", "microwave", "oven", "toaster", "blender", "kettle",
        "coffee maker", "dishwasher", "washing machine", "dryer", "vacuum",
        "iron", "fan", "heater", "air conditioner", "humidifier",
    ],
    "decor": [
        "lamp", "floor lamp", "desk lamp", "chandelier", "candle", "vase",
        "picture frame", "painting", "mirror", "clock", "plant", "potted plant",
        "rug", "curtain", "pillow", "blanket", "figurine", "sculpture",
    ],
    "musical_instruments": [
        "piano", "guitar", "violin", "drum", "keyboard instrument",
    ],
    "books": ["book", "magazine", "vinyl record"],
    "toys": ["toy", "teddy bear", "board game"],
    "clothing": ["shoe", "bag", "backpack", "suitcase"],
    "sports": ["bicycle"],
    "tools": ["toolbox"],
    "other": ["box", "basket", "umbrella"],
}

# Build reverse lookup: vocabulary name -> category
_VOCAB_CATEGORY: dict[str, str] = {}
for _cat, _names in _CATEGORY_KEYWORDS.items():
    for _name in _names:
        _VOCAB_CATEGORY[_name.lower()] = _cat

# Singleton ONNX session
_onnx_session = None
_onnx_input_name = None
_onnx_output_name = None


def _get_onnx_session():
    global _onnx_session, _onnx_input_name, _onnx_output_name
    if _onnx_session is None:
        import onnxruntime as ort

        model_path = str(Path(settings.yolo_model_path).resolve())
        providers = []
        available = ort.get_available_providers()
        if "CoreMLExecutionProvider" in available:
            providers.append("CoreMLExecutionProvider")
        providers.append("CPUExecutionProvider")

        logger.info("Loading YOLO-World model from %s with providers %s", model_path, providers)
        _onnx_session = ort.InferenceSession(model_path, providers=providers)
        _onnx_input_name = _onnx_session.get_inputs()[0].name
        _onnx_output_name = _onnx_session.get_outputs()[0].name
    return _onnx_session, _onnx_input_name, _onnx_output_name


def _compute_iou(box_a: list[float], box_b: list[float]) -> float:
    """Compute IoU between two [x1, y1, x2, y2] boxes (normalized 0-1)."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


class LocalVisionService:
    """Two-stage local detection: YOLO-World (boxes) + Qwen2.5-VL (descriptions)."""

    async def analyze_frame(
        self, image_path: str, voice_context: str | None = None
    ) -> list[DetectedObject]:
        img = cv2.imread(image_path)
        if img is None:
            logger.error("Could not read image: %s", image_path)
            return []

        orig_h, orig_w = img.shape[:2]

        # Stage 1: YOLO-World detection (~10-20ms)
        yolo_detections = self._run_yolo(img)

        # Stage 2: Qwen2.5-VL description (~8-12s)
        qwen_objects = await self._run_qwen(image_path, orig_w, orig_h, voice_context)

        # Merge results
        merged = self._merge_detections(yolo_detections, qwen_objects, voice_context)
        return merged

    def _run_yolo(self, img: np.ndarray) -> list[dict]:
        """Run YOLO-World inference and return detections with boxes."""
        session, input_name, output_name = _get_onnx_session()
        vocab = settings.yolo_world_vocabulary

        # Preprocess: resize to 640x640, normalize, NCHW
        input_img = cv2.resize(img, (640, 640))
        input_img = input_img.astype(np.float32) / 255.0
        input_img = np.transpose(input_img, (2, 0, 1))  # HWC -> CHW
        input_img = np.expand_dims(input_img, axis=0)  # Add batch dim

        # Run inference
        outputs = session.run([output_name], {input_name: input_img})
        output = outputs[0]  # Shape: (1, N+4, 8400) where N = len(vocab)

        # Post-process: transpose to (8400, N+4)
        predictions = output[0].T  # (8400, N+4)

        # Extract boxes (cx, cy, w, h) and class scores
        boxes_xywh = predictions[:, :4]
        num_classes = len(vocab)
        class_scores = predictions[:, 4:4 + num_classes]  # (8400, N)

        # Get best class per detection
        class_ids = np.argmax(class_scores, axis=1)
        confidences = class_scores[np.arange(len(class_ids)), class_ids]

        # Filter by confidence
        mask = confidences > settings.yolo_confidence_threshold
        boxes_xywh = boxes_xywh[mask]
        class_ids = class_ids[mask]
        confidences = confidences[mask]

        if len(boxes_xywh) == 0:
            return []

        # Convert cx,cy,w,h -> x1,y1,x2,y2 (in 640x640 space)
        x1 = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
        y1 = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
        x2 = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
        y2 = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2
        boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)

        # NMS
        indices = cv2.dnn.NMSBoxes(
            boxes_xywh.tolist(),
            confidences.tolist(),
            settings.yolo_confidence_threshold,
            settings.yolo_nms_threshold,
        )
        if len(indices) == 0:
            return []

        indices = indices.flatten()

        detections = []
        for idx in indices:
            class_id = int(class_ids[idx])
            class_name = vocab[class_id] if class_id < len(vocab) else "unknown"
            # Normalize box to 0-1
            bbox = [
                float(boxes_xyxy[idx, 0] / 640),
                float(boxes_xyxy[idx, 1] / 640),
                float(boxes_xyxy[idx, 2] / 640),
                float(boxes_xyxy[idx, 3] / 640),
            ]
            bbox = [max(0.0, min(1.0, v)) for v in bbox]
            category = _VOCAB_CATEGORY.get(class_name.lower(), "other")
            detections.append({
                "class_name": class_name,
                "class_id": class_id,
                "confidence": float(confidences[idx]),
                "bbox": bbox,
                "category": category,
            })

        logger.info("YOLO-World detected %d objects", len(detections))
        return detections

    async def _run_qwen(
        self, image_path: str, img_w: int, img_h: int, voice_context: str | None = None
    ) -> list[dict]:
        """Run Qwen2.5-VL via configured backend for rich object descriptions."""
        if settings.vision_backend == "openai":
            return await self._run_qwen_openai(image_path, img_w, img_h, voice_context)
        return await self._run_qwen_ollama(image_path, img_w, img_h, voice_context)

    def _build_prompt(self, voice_context: str | None = None) -> str:
        prompt = QWEN_PROMPT
        if voice_context:
            prompt = (
                f'The person narrated: "{voice_context}"\n'
                "Use this context to improve identification.\n\n" + prompt
            )
        return prompt

    def _normalize_bboxes(self, objects: list[dict], img_w: int, img_h: int) -> list[dict]:
        """Normalize bbox_2d pixel coords to 0-1 range."""
        for obj in objects:
            bbox = obj.get("bbox_2d")
            if bbox and len(bbox) == 4 and img_w > 0 and img_h > 0:
                obj["bbox"] = [
                    max(0.0, min(1.0, bbox[0] / img_w)),
                    max(0.0, min(1.0, bbox[1] / img_h)),
                    max(0.0, min(1.0, bbox[2] / img_w)),
                    max(0.0, min(1.0, bbox[3] / img_h)),
                ]
            else:
                obj["bbox"] = None
        return objects

    async def _run_qwen_ollama(
        self, image_path: str, img_w: int, img_h: int, voice_context: str | None = None
    ) -> list[dict]:
        """Run Qwen2.5-VL via Ollama /api/generate endpoint."""
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")
        prompt = self._build_prompt(voice_context)

        payload = {
            "model": settings.ollama_vision_model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=settings.qwen_timeout) as client:
                resp = await client.post(
                    f"{settings.ollama_base_url}/api/generate",
                    json=payload,
                )
                resp.raise_for_status()
                result = resp.json()
                text = result.get("response", "")
                objects = self._parse_qwen_response(text)
                return self._normalize_bboxes(objects, img_w, img_h)
        except Exception:
            logger.exception("Qwen2.5-VL (Ollama) inference failed, using YOLO-only results")
            return []

    async def _run_qwen_openai(
        self, image_path: str, img_w: int, img_h: int, voice_context: str | None = None
    ) -> list[dict]:
        """Run Qwen2.5-VL via OpenAI-compatible /v1/chat/completions endpoint (Modal/vLLM)."""
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")
        ext = Path(image_path).suffix.lstrip(".") or "jpeg"
        mime = f"image/{ext}" if ext != "jpg" else "image/jpeg"
        prompt = self._build_prompt(voice_context)

        payload = {
            "model": settings.openai_vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{image_b64}",
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.1,
        }

        headers = {"Content-Type": "application/json"}
        if settings.openai_vision_api_key:
            headers["Authorization"] = f"Bearer {settings.openai_vision_api_key}"

        try:
            async with httpx.AsyncClient(timeout=settings.qwen_timeout) as client:
                resp = await client.post(
                    f"{settings.openai_vision_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                result = resp.json()
                text = result["choices"][0]["message"]["content"]
                objects = self._parse_qwen_response(text)
                return self._normalize_bboxes(objects, img_w, img_h)
        except Exception:
            logger.exception("Qwen2.5-VL (OpenAI) inference failed, using YOLO-only results")
            return []

    def _parse_qwen_response(self, text: str) -> list[dict]:
        """Parse Qwen response text into list of object dicts."""
        text = text.strip()
        # Strip markdown code fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        # Fix Python-style booleans/None that models sometimes emit
        fixed = text.replace(": True", ": true").replace(": False", ": false").replace(": None", ": null")

        for attempt in (fixed, text):
            try:
                data = json.loads(attempt)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return [data]
            except json.JSONDecodeError:
                pass

        # Try to find JSON array in the text
        for attempt in (fixed, text):
            start = attempt.find("[")
            end = attempt.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    data = json.loads(attempt[start:end + 1])
                    if isinstance(data, list):
                        return data
                except json.JSONDecodeError:
                    pass

        logger.warning("Could not parse Qwen response: %s", text[:200])
        return []

    def _merge_detections(
        self,
        yolo_dets: list[dict],
        qwen_objs: list[dict],
        voice_context: str | None = None,
    ) -> list[DetectedObject]:
        """Merge YOLO-World spatial data with Qwen2.5-VL semantic data.

        Both sources now provide bounding boxes. Match by IoU (70% weight)
        + fuzzy name similarity (30% weight). YOLO provides precise boxes,
        Qwen provides rich names/descriptions.
        """
        from rapidfuzz import fuzz

        merged: list[DetectedObject] = []
        used_qwen: set[int] = set()

        for det in yolo_dets:
            class_name = det["class_name"]
            category = det["category"]
            confidence = det["confidence"]
            yolo_bbox = det["bbox"]

            # Try to match with a Qwen object using IoU + name similarity
            best_match = None
            best_score = 0.0
            best_idx = -1

            for i, qobj in enumerate(qwen_objs):
                if i in used_qwen:
                    continue

                # Compute combined score: 70% IoU + 30% name similarity
                qwen_bbox = qobj.get("bbox")
                iou = 0.0
                if qwen_bbox and len(qwen_bbox) == 4:
                    iou = _compute_iou(yolo_bbox, qwen_bbox)

                qwen_name = qobj.get("name", "").lower()
                name_sim = fuzz.partial_ratio(class_name.lower(), qwen_name) / 100.0

                combined = 0.7 * iou + 0.3 * name_sim
                if combined > best_score and combined > 0.3:
                    best_score = combined
                    best_match = qobj
                    best_idx = i

            if best_match and best_idx >= 0:
                used_qwen.add(best_idx)
                name = best_match.get("name", class_name.title())
                description = best_match.get("description", f"Detected {class_name}")
                qwen_category = best_match.get("category", category)
                is_book = best_match.get("is_book", class_name == "book")
                final_confidence = min(1.0, (confidence + best_score) / 2)
            else:
                name = class_name.replace("_", " ").title()
                description = f"Detected {class_name}"
                qwen_category = category
                is_book = class_name == "book"
                final_confidence = confidence

            merged.append(DetectedObject(
                name=name,
                description=description,
                category=qwen_category,
                is_book=is_book,
                confidence=round(final_confidence, 2),
                bounding_box=yolo_bbox,
                voice_context=voice_context,
            ))

        # Add Qwen-only objects (items YOLO-World missed) with their own bounding boxes
        for i, qobj in enumerate(qwen_objs):
            if i in used_qwen:
                continue
            name = qobj.get("name", "Unknown")
            bbox = qobj.get("bbox")
            merged.append(DetectedObject(
                name=name,
                description=qobj.get("description", ""),
                category=qobj.get("category", "other"),
                is_book=qobj.get("is_book", False),
                confidence=0.6,
                bounding_box=bbox,
                voice_context=voice_context,
            ))

        logger.info(
            "Merged: %d YOLO + %d Qwen-only = %d total",
            len(yolo_dets), len(merged) - len(yolo_dets), len(merged),
        )
        return merged
