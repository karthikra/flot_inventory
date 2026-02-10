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

    model_config = {
        "env_prefix": "INVENTORY_",
        "env_file": ".env",
        "extra": "ignore",
    }

    def model_post_init(self, __context):
        if not self.anthropic_api_key:
            self.anthropic_api_key = _env_vars.get("ANTHROPIC_API_KEY", "")


settings = Settings()
