import logging
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Optional

import exifread
from PIL import Image, UnidentifiedImageError

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

logger = logging.getLogger(__name__)


def _dms_to_decimal(values) -> Optional[float]:
    """Convert a list of exifread Ratio values [degrees, minutes, seconds] to decimal degrees."""
    try:
        degrees = float(Fraction(str(values[0])))
        minutes = float(Fraction(str(values[1])))
        seconds = float(Fraction(str(values[2])))
        return degrees + minutes / 60.0 + seconds / 3600.0
    except Exception:
        return None


def _parse_gps(tags: dict) -> tuple[Optional[float], Optional[float]]:
    lat = lon = None

    lat_tag = tags.get("GPS GPSLatitude")
    lat_ref_tag = tags.get("GPS GPSLatitudeRef")
    lon_tag = tags.get("GPS GPSLongitude")
    lon_ref_tag = tags.get("GPS GPSLongitudeRef")

    if lat_tag and lat_ref_tag:
        lat = _dms_to_decimal(lat_tag.values)
        if lat is not None and str(lat_ref_tag.values).strip().upper() == "S":
            lat = -lat

    if lon_tag and lon_ref_tag:
        lon = _dms_to_decimal(lon_tag.values)
        if lon is not None and str(lon_ref_tag.values).strip().upper() == "W":
            lon = -lon

    return lat, lon


def _parse_ratio(tag) -> Optional[float]:
    """Convert an exifread ratio tag to float."""
    if tag is None:
        return None
    try:
        values = tag.values
        if values:
            return float(Fraction(str(values[0])))
    except Exception:
        pass
    return None


def _parse_date(tag) -> Optional[datetime]:
    if tag is None:
        return None
    try:
        return datetime.strptime(str(tag.values), "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def extract_exif(path: Path) -> Optional[dict]:
    """Extract dimensions, format, and EXIF metadata from an image or video file.

    Returns None if the file does not exist or cannot be opened.
    """
    from backend.indexer.scanner import VIDEO_EXTENSIONS

    if not path.exists():
        logger.warning("extract_exif: file does not exist: %s", path)
        return None

    # Handle video files separately
    if path.suffix.lower() in VIDEO_EXTENSIONS:
        return _extract_video_metadata(path)

    # Get dimensions and format via Pillow
    try:
        with Image.open(path) as img:
            width, height = img.size
            fmt = img.format  # e.g. "JPEG", "PNG"
    except (UnidentifiedImageError, OSError, Exception) as exc:
        logger.warning("extract_exif: cannot open image %s: %s", path, exc)
        return None

    # Extract EXIF via exifread
    exif_date: Optional[datetime] = None
    make: Optional[str] = None
    model: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    focal_length: Optional[float] = None
    aperture: Optional[float] = None
    iso: Optional[int] = None
    exposure: Optional[float] = None

    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)

        exif_date = _parse_date(tags.get("EXIF DateTimeOriginal"))

        make_tag = tags.get("Image Make")
        if make_tag:
            make = str(make_tag.values).strip()

        model_tag = tags.get("Image Model")
        if model_tag:
            model = str(model_tag.values).strip()

        gps_lat, gps_lon = _parse_gps(tags)

        focal_length = _parse_ratio(tags.get("EXIF FocalLength"))
        aperture = _parse_ratio(tags.get("EXIF FNumber"))

        iso_tag = tags.get("EXIF ISOSpeedRatings")
        if iso_tag:
            try:
                iso = int(iso_tag.values[0])
            except Exception:
                pass

        exposure = _parse_ratio(tags.get("EXIF ExposureTime"))

    except Exception as exc:
        logger.warning("extract_exif: error reading EXIF from %s: %s", path, exc)

    return {
        "width": width,
        "height": height,
        "format": fmt,
        "exif_date": exif_date,
        "exif_camera_make": make,
        "exif_camera_model": model,
        "exif_gps_lat": gps_lat,
        "exif_gps_lon": gps_lon,
        "exif_focal_length": focal_length,
        "exif_aperture": aperture,
        "exif_iso": iso,
        "exif_exposure": exposure,
    }


def _extract_video_metadata(path: Path) -> Optional[dict]:
    """Extract basic metadata from a video file using OpenCV."""
    result = {
        "width": None, "height": None, "format": path.suffix.upper().lstrip("."),
        "exif_date": None, "exif_camera_make": None, "exif_camera_model": None,
        "exif_gps_lat": None, "exif_gps_lon": None, "exif_focal_length": None,
        "exif_aperture": None, "exif_iso": None, "exif_exposure": None,
    }
    try:
        import cv2
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return result
        result["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        result["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Video metadata extraction failed for %s: %s", path, exc)

    # Try to get date from file modification time
    try:
        mtime = path.stat().st_mtime
        result["exif_date"] = datetime.fromtimestamp(mtime)
    except Exception:
        pass

    return result
