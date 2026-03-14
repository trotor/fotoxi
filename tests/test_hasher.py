import io
from pathlib import Path

import pytest
from PIL import Image

from backend.indexer.hasher import compute_hashes, hamming_distance


def _make_red_jpeg(tmp_path: Path, size: tuple = (200, 200)) -> Path:
    """Create a solid-red JPEG at the given size and return its path."""
    img_path = tmp_path / f"red_{size[0]}x{size[1]}.jpg"
    img = Image.new("RGB", size, color=(255, 0, 0))
    img.save(img_path, format="JPEG")
    return img_path


def test_compute_hashes(tmp_path):
    img_path = _make_red_jpeg(tmp_path)
    result = compute_hashes(img_path)

    assert result is not None
    assert "phash" in result
    assert "dhash" in result
    assert isinstance(result["phash"], str)
    assert isinstance(result["dhash"], str)
    # Hex strings should be non-empty
    assert len(result["phash"]) > 0
    assert len(result["dhash"]) > 0


def test_similar_images_low_distance(tmp_path):
    path_large = _make_red_jpeg(tmp_path, size=(200, 200))
    path_small = _make_red_jpeg(tmp_path, size=(100, 100))

    hashes_large = compute_hashes(path_large)
    hashes_small = compute_hashes(path_small)

    assert hashes_large is not None
    assert hashes_small is not None

    dist = hamming_distance(hashes_large["phash"], hashes_small["phash"])
    assert dist < 10, f"Expected distance < 10, got {dist}"


def test_hamming_distance():
    assert hamming_distance("ff00", "ff00") == 0
    assert hamming_distance("ff00", "ff01") == 1


def test_invalid_file(tmp_path):
    nonexistent = tmp_path / "does_not_exist.jpg"
    result = compute_hashes(nonexistent)
    assert result is None
