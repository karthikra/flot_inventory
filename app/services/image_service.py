import shutil
import uuid
from pathlib import Path

from PIL import Image

from app.config import settings


class ImageService:
    def __init__(self):
        settings.images_dir.mkdir(parents=True, exist_ok=True)
        settings.thumbnails_dir.mkdir(parents=True, exist_ok=True)

    def save_image(self, source_path: Path, room_name: str = "unsorted") -> tuple[str, str]:
        """Save an image and generate thumbnail. Returns (image_path, thumbnail_path)."""
        room_dir = settings.images_dir / self._sanitize(room_name)
        room_dir.mkdir(parents=True, exist_ok=True)

        thumb_dir = settings.thumbnails_dir / self._sanitize(room_name)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        ext = source_path.suffix or ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"

        dest = room_dir / filename
        shutil.copy2(source_path, dest)

        thumb_path = thumb_dir / filename
        self._create_thumbnail(dest, thumb_path)

        return str(dest), str(thumb_path)

    async def save_upload(self, data: bytes, room_name: str = "unsorted", ext: str = ".jpg") -> tuple[str, str]:
        """Save uploaded bytes as image + thumbnail. Returns (image_path, thumbnail_path)."""
        room_dir = settings.images_dir / self._sanitize(room_name)
        room_dir.mkdir(parents=True, exist_ok=True)

        thumb_dir = settings.thumbnails_dir / self._sanitize(room_name)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{uuid.uuid4().hex}{ext}"
        dest = room_dir / filename
        dest.write_bytes(data)

        thumb_path = thumb_dir / filename
        self._create_thumbnail(dest, thumb_path)

        return str(dest), str(thumb_path)

    def _create_thumbnail(self, source: Path, dest: Path) -> None:
        with Image.open(source) as img:
            img.thumbnail(settings.thumbnail_size)
            img.save(dest, quality=85)

    def crop_to_bbox(
        self, image_path: str, bbox: list[float], output_path: str | None = None
    ) -> str:
        """Crop an image to a normalized [x1,y1,x2,y2] bounding box. Returns path to cropped image."""
        import uuid as _uuid

        with Image.open(image_path) as img:
            w, h = img.size
            left = int(bbox[0] * w)
            top = int(bbox[1] * h)
            right = int(bbox[2] * w)
            bottom = int(bbox[3] * h)
            cropped = img.crop((left, top, right, bottom))

            if not output_path:
                crop_dir = settings.data_dir / "crops"
                crop_dir.mkdir(parents=True, exist_ok=True)
                output_path = str(crop_dir / f"{_uuid.uuid4().hex}.jpg")

            cropped.save(output_path, quality=90)
            return output_path

    def _sanitize(self, name: str) -> str:
        return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name.lower())
