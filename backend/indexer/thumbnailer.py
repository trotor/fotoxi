import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def generate_thumbnail(source: Path, thumbs_dir: Path, image_id: int) -> Optional[Path]:
    """Generate a 300px (longest side) JPEG thumbnail for the given image.

    Args:
        source: Path to the source image file.
        thumbs_dir: Directory where thumbnails are stored.
        image_id: Numeric ID used to name the thumbnail file.

    Returns:
        Path to the saved thumbnail on success, None on error.
    """
    try:
        from PIL import Image
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass

        thumbs_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumbs_dir / f"{image_id}.jpg"

        with Image.open(source) as img:
            img.thumbnail((300, 300))
            img = img.convert("RGB")
            img.save(thumb_path, format="JPEG", quality=85)

        return thumb_path
    except Exception as exc:
        logger.warning("Failed to generate thumbnail for %s: %s", source, exc)
        return None
