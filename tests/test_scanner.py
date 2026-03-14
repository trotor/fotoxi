import pytest
from pathlib import Path

from backend.indexer.scanner import scan_directory


def test_scan_finds_images(tmp_path):
    # Create image files and a non-image file in the root temp dir
    (tmp_path / "photo.jpg").touch()
    (tmp_path / "image.png").touch()
    (tmp_path / "document.txt").touch()

    # Create a subdirectory with an image file
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "photo.heic").touch()

    results = list(scan_directory(tmp_path))

    assert len(results) == 3
    result_names = {p.name for p in results}
    assert "photo.jpg" in result_names
    assert "image.png" in result_names
    assert "photo.heic" in result_names
    assert "document.txt" not in result_names


def test_scan_empty_dir(tmp_path):
    results = list(scan_directory(tmp_path))
    assert results == []


def test_scan_nonexistent_dir(tmp_path):
    missing = tmp_path / "does_not_exist"
    results = list(scan_directory(missing))
    assert results == []
