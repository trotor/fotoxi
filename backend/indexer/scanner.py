from pathlib import Path
from typing import Iterator

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif",
    ".tiff", ".tif", ".raw", ".cr2", ".nef", ".arw", ".dng",
}


def scan_directory(directory: str | Path) -> Iterator[Path]:
    """Recursively scan a directory and yield paths to image files.

    Args:
        directory: Path to the directory to scan (str or Path).

    Yields:
        Path objects for each image file found.
    """
    directory = Path(directory)

    if not directory.exists():
        return

    for path in directory.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path
