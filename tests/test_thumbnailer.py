import pytest
from pathlib import Path
from PIL import Image

from backend.indexer.thumbnailer import generate_thumbnail


def make_image(path: Path, width: int, height: int) -> Path:
    """Create a simple RGB PNG image at the given path."""
    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    img.save(path, format="PNG")
    return path


def test_generate_thumbnail(tmp_path: Path) -> None:
    """Landscape 4000x3000 image: longest side of thumbnail should be 300px."""
    source = make_image(tmp_path / "landscape.png", width=4000, height=3000)
    thumbs_dir = tmp_path / "thumbs"

    result = generate_thumbnail(source, thumbs_dir, image_id=1)

    assert result is not None
    assert result.exists()
    assert result == thumbs_dir / "1.jpg"

    with Image.open(result) as thumb:
        assert max(thumb.size) == 300


def test_thumbnail_portrait(tmp_path: Path) -> None:
    """Portrait 2000x4000 image: height (longest side) should be 300px."""
    source = make_image(tmp_path / "portrait.png", width=2000, height=4000)
    thumbs_dir = tmp_path / "thumbs"

    result = generate_thumbnail(source, thumbs_dir, image_id=2)

    assert result is not None
    assert result.exists()

    with Image.open(result) as thumb:
        width, height = thumb.size
        assert height == 300
        assert max(thumb.size) == 300


def test_generate_thumbnail_invalid_source(tmp_path: Path) -> None:
    """Non-existent source should return None without raising."""
    result = generate_thumbnail(
        tmp_path / "nonexistent.jpg", tmp_path / "thumbs", image_id=99
    )
    assert result is None
