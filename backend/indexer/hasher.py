import hashlib
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


def compute_file_hash(path: Path) -> Optional[str]:
    """Compute SHA-256 hash of a file's contents.

    Reads the file in 64 KB chunks to handle large files efficiently.
    Returns the hex digest, or None on error.
    """
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception as exc:
        logger.warning("Failed to compute file hash for %s: %s", path, exc)
        return None


def compute_hashes(path: Path) -> Optional[dict]:
    """Open an image and compute perceptual hashes + file content hash.

    Returns a dict with "phash", "dhash", and "file_hash" as hex strings,
    or None on error. Videos get only file_hash (no perceptual hash).
    """
    from backend.indexer.scanner import VIDEO_EXTENSIONS

    file_hash = compute_file_hash(path)

    if path.suffix.lower() in VIDEO_EXTENSIONS:
        return {"phash": None, "dhash": None, "file_hash": file_hash} if file_hash else None

    try:
        with Image.open(path) as img:
            ph = imagehash.phash(img)
            dh = imagehash.dhash(img)
            return {"phash": str(ph), "dhash": str(dh), "file_hash": file_hash}
    except Exception as exc:
        logger.warning("Failed to compute hashes for %s: %s", path, exc)
        return None


def hamming_distance(hash1: str, hash2: str) -> int:
    """Return the Hamming distance between two hex-encoded hash strings."""
    a = int(hash1, 16)
    b = int(hash2, 16)
    xor = a ^ b
    return bin(xor).count("1")
