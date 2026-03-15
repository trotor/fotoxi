import logging
from pathlib import Path
from typing import Optional

import imagehash
from PIL import Image

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

logger = logging.getLogger(__name__)


def compute_hashes(path: Path) -> Optional[dict]:
    """Open an image and compute perceptual hashes.

    Returns a dict with "phash" and "dhash" as hex strings, or None on error.
    Videos are skipped (return None).
    """
    from backend.indexer.scanner import VIDEO_EXTENSIONS
    if path.suffix.lower() in VIDEO_EXTENSIONS:
        return None  # No perceptual hash for videos

    try:
        with Image.open(path) as img:
            ph = imagehash.phash(img)
            dh = imagehash.dhash(img)
            return {"phash": str(ph), "dhash": str(dh)}
    except Exception as exc:
        logger.warning("Failed to compute hashes for %s: %s", path, exc)
        return None


def hamming_distance(hash1: str, hash2: str) -> int:
    """Return the Hamming distance between two hex-encoded hash strings."""
    a = int(hash1, 16)
    b = int(hash2, 16)
    xor = a ^ b
    return bin(xor).count("1")
