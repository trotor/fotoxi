import io
import struct
from pathlib import Path

import piexif
import pytest
from PIL import Image

from backend.indexer.exif import extract_exif


def _make_jpeg(path: Path, width: int = 100, height: int = 100, color=(255, 0, 0)):
    """Save a plain JPEG image (no EXIF) to *path*."""
    img = Image.new("RGB", (width, height), color=color)
    img.save(path, format="JPEG")


def _make_jpeg_with_exif(
    path: Path,
    width: int = 100,
    height: int = 100,
    make: str = "TestMake",
    model: str = "TestModel",
):
    """Save a JPEG with basic camera EXIF tags embedded via piexif."""
    img = Image.new("RGB", (width, height), color=(0, 128, 255))

    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: make.encode(),
            piexif.ImageIFD.Model: model.encode(),
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: b"2024:06:15 10:30:00",
            piexif.ExifIFD.FocalLength: (50, 1),
            piexif.ExifIFD.FNumber: (18, 10),
            piexif.ExifIFD.ISOSpeedRatings: 200,
            piexif.ExifIFD.ExposureTime: (1, 500),
        },
        "GPS": {},
        "1st": {},
    }

    exif_bytes = piexif.dump(exif_dict)
    img.save(path, format="JPEG", exif=exif_bytes)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_extract_exif_basic(tmp_path):
    """Plain JPEG: verify width, height, and format are extracted correctly."""
    img_path = tmp_path / "red.jpg"
    _make_jpeg(img_path, width=100, height=100)

    result = extract_exif(img_path)

    assert result is not None
    assert result["width"] == 100
    assert result["height"] == 100
    assert result["format"] == "JPEG"


def test_extract_exif_missing_file(tmp_path):
    """Non-existent path returns None without raising."""
    missing = tmp_path / "does_not_exist.jpg"
    result = extract_exif(missing)
    assert result is None


def test_extract_exif_with_camera_tags(tmp_path):
    """JPEG with piexif-embedded EXIF: verify camera make/model and other tags."""
    img_path = tmp_path / "camera.jpg"
    _make_jpeg_with_exif(img_path, make="Canon", model="EOS 5D")

    result = extract_exif(img_path)

    assert result is not None
    assert result["width"] == 100
    assert result["height"] == 100
    assert result["format"] == "JPEG"
    assert result["exif_camera_make"] == "Canon"
    assert result["exif_camera_model"] == "EOS 5D"
    assert result["exif_focal_length"] == pytest.approx(50.0)
    assert result["exif_aperture"] == pytest.approx(1.8)
    assert result["exif_iso"] == 200
    assert result["exif_exposure"] == pytest.approx(1 / 500)

    from datetime import datetime

    assert result["exif_date"] == datetime(2024, 6, 15, 10, 30, 0)


def test_extract_exif_non_image_file(tmp_path):
    """A file that is not an image returns None."""
    bad_file = tmp_path / "not_an_image.jpg"
    bad_file.write_bytes(b"this is not an image")

    result = extract_exif(bad_file)
    assert result is None


def test_extract_exif_no_gps_returns_none_coords(tmp_path):
    """Image without GPS data returns None for lat/lon."""
    img_path = tmp_path / "no_gps.jpg"
    _make_jpeg(img_path)

    result = extract_exif(img_path)

    assert result is not None
    assert result["exif_gps_lat"] is None
    assert result["exif_gps_lon"] is None
