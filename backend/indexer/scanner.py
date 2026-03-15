from pathlib import Path
from typing import Iterator

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif",
    ".tiff", ".tif", ".raw", ".cr2", ".nef", ".arw", ".dng",
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".mts",
}

MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def scan_directory(directory: str | Path, exclude_patterns: list[str] | None = None) -> Iterator[Path]:
    """Recursively scan a directory and yield paths to image files.

    Args:
        directory: Path to the directory to scan (str or Path).
        exclude_patterns: List of folder name patterns to skip.

    Yields:
        Path objects for each image file found.
    """
    directory = Path(directory)
    excludes = set(exclude_patterns or [])

    if not directory.exists():
        return

    for path in directory.rglob("*"):
        if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS:
            # Check if any parent folder matches exclude patterns
            if excludes and any(part in excludes for part in path.parts):
                continue
            yield path
