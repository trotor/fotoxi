"""Generate AI-optimized thumbnails (512px) for vision model analysis."""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def generate_ai_thumb(source: Path, ai_thumbs_dir: Path, image_id: int, size: int = 512) -> Optional[Path]:
    """Generate a thumbnail optimized for AI vision analysis.

    Larger than display thumbnails (512px vs 300px) for better AI recognition.
    """
    try:
        from PIL import Image, ImageOps
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass

        ai_thumbs_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = ai_thumbs_dir / f"{image_id}.jpg"

        # Skip if already exists
        if thumb_path.exists():
            return thumb_path

        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((size, size))
            img = img.convert("RGB")
            img.save(thumb_path, format="JPEG", quality=90)

        return thumb_path
    except Exception as exc:
        logger.warning("Failed to generate AI thumbnail for %s: %s", source, exc)
        return None
