from pathlib import Path

from dotenv import dotenv_values
from pydantic_settings import BaseSettings

_ENV_FILE = Path.home() / "env" / ".env.dev"
_env_vars = dotenv_values(str(_ENV_FILE)) if _ENV_FILE.exists() else {}


class Settings(BaseSettings):
    app_name: str = "Flot Inventory"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///data/inventory.db"
    data_dir: Path = Path("data")
    images_dir: Path = Path("data/images/originals")
    thumbnails_dir: Path = Path("data/images/thumbnails")
    thumbnail_size: tuple[int, int] = (300, 300)
    anthropic_api_key: str = ""
    vision_model: str = "claude-sonnet-4-5-20250929"
    max_video_size_mb: int = 500
    video_fps_extract: float = 1.5
    blur_threshold: float = 100.0
    duplicate_text_threshold: float = 0.85
    open_library_base_url: str = "https://openlibrary.org"
    whisper_model: str = "small"
    whisper_compute_type: str = "int8"
    whisper_device: str = "auto"
    audio_dir: Path = Path("data/audio")
    models_cache_dir: Path = Path.home() / ".cache" / "flot_inventory" / "models"
    yolo_model_path: str = str(Path.home() / ".cache" / "flot_inventory" / "models" / "yoloworld_v2s.onnx")
    yolo_confidence_threshold: float = 0.3
    yolo_nms_threshold: float = 0.45
    detection_iou_threshold: float = 0.3
    vision_backend: str = "ollama"  # "ollama" or "openai"
    ollama_base_url: str = "http://euler.tail375484.ts.net:11434"
    ollama_vision_model: str = "qwen2.5vl:7b"
    openai_vision_url: str = ""  # e.g. "https://user--qwen25vl.modal.run/v1"
    openai_vision_api_key: str = ""
    openai_vision_model: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    qwen_timeout: float = 300.0
    yolo_world_vocabulary: list[str] = [
        # Furniture
        "chair", "couch", "sofa", "table", "desk", "bed", "shelf", "bookshelf",
        "cabinet", "dresser", "nightstand", "bench", "stool", "ottoman", "recliner",
        "wardrobe", "tv stand", "coffee table", "dining table", "end table",
        # Electronics
        "tv", "monitor", "laptop", "keyboard", "mouse", "speaker", "headphones",
        "remote", "phone", "tablet", "game console", "router", "camera",
        # Kitchen
        "refrigerator", "microwave", "oven", "toaster", "blender", "kettle",
        "coffee maker", "dishwasher", "pot", "pan", "plate", "bowl", "cup", "mug",
        "glass", "bottle", "cutting board", "knife block",
        # Decor & lighting
        "lamp", "floor lamp", "desk lamp", "chandelier", "candle", "vase",
        "picture frame", "painting", "mirror", "clock", "plant", "potted plant",
        "rug", "curtain", "pillow", "blanket", "figurine", "sculpture",
        # Musical instruments
        "piano", "guitar", "violin", "drum", "keyboard instrument",
        # Books & media
        "book", "bookshelf", "magazine", "vinyl record",
        # Appliances
        "washing machine", "dryer", "vacuum", "iron", "fan", "heater",
        "air conditioner", "humidifier",
        # Storage & misc
        "box", "basket", "bag", "suitcase", "backpack", "shoe", "toy",
        "teddy bear", "board game", "bicycle", "umbrella", "toolbox",
    ]

    model_config = {
        "env_prefix": "INVENTORY_",
        "env_file": ".env",
        "extra": "ignore",
    }

    def model_post_init(self, __context):
        if not self.anthropic_api_key:
            self.anthropic_api_key = _env_vars.get("ANTHROPIC_API_KEY", "")


settings = Settings()
