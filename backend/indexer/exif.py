import logging
import re
import struct
from datetime import datetime, timedelta
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

    # Fallback: try filename, then file mtime
    if exif_date is None:
        exif_date = _parse_date_from_filename(path.stem)
    if exif_date is None:
        try:
            stat = path.stat()
            candidates = [stat.st_mtime]
            btime = getattr(stat, "st_birthtime", None)
            if btime:
                candidates.append(btime)
            exif_date = datetime.fromtimestamp(min(candidates))
        except Exception:
            pass

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


def _read_mp4_creation_time(path: Path) -> Optional[datetime]:
    """Read creation_time from MP4/MOV mvhd atom (container metadata)."""
    try:
        with open(path, "rb") as f:
            while True:
                header = f.read(8)
                if len(header) < 8:
                    return None
                size, box_type = struct.unpack(">I4s", header)
                box_type = box_type.decode("ascii", errors="ignore")
                if size == 0:
                    return None
                if size == 1:  # 64-bit extended size
                    size = struct.unpack(">Q", f.read(8))[0]
                if box_type in ("moov", "trak", "mdia"):
                    continue  # descend into container atoms
                elif box_type == "mvhd":
                    version = struct.unpack(">B", f.read(1))[0]
                    f.read(3)  # flags
                    if version == 0:
                        ct = struct.unpack(">I", f.read(4))[0]
                    else:
                        ct = struct.unpack(">Q", f.read(8))[0]
                    if ct == 0:
                        return None
                    # MP4 epoch is 1904-01-01
                    dt = datetime(1904, 1, 1) + timedelta(seconds=ct)
                    # Sanity check: must be after 2000 and not in the future
                    if dt.year < 2000 or dt > datetime.now() + timedelta(days=1):
                        return None
                    return dt
                else:
                    remaining = size - 8
                    if remaining > 0:
                        f.seek(remaining, 1)
    except Exception as exc:
        logger.debug("_read_mp4_creation_time failed for %s: %s", path, exc)
    return None


def _extract_video_metadata(path: Path) -> Optional[dict]:
    """Extract basic metadata from a video file using OpenCV + MP4 atoms."""
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

    # Try MP4/MOV container creation_time first (most reliable)
    creation_time = _read_mp4_creation_time(path)
    if creation_time:
        result["exif_date"] = creation_time
        return result

    # Try parsing date from filename (e.g. 20260112_190536000_iOS.MP4, VID_20210501_123456.mp4)
    fname_date = _parse_date_from_filename(path.stem)
    if fname_date:
        result["exif_date"] = fname_date
        return result

    # Fallback: earliest of mtime and birthtime
    try:
        stat = path.stat()
        candidates = [stat.st_mtime]
        btime = getattr(stat, "st_birthtime", None)
        if btime:
            candidates.append(btime)
        result["exif_date"] = datetime.fromtimestamp(min(candidates))
    except Exception:
        pass

    return result


def _parse_date_from_filename(stem: str) -> Optional[datetime]:
    """Try to extract a date/time from common filename patterns."""
    # Pattern: 20260112_190536 (with optional milliseconds and suffix)
    m = re.match(r"(\d{4})(\d{2})(\d{2})[_\-](\d{2})(\d{2})(\d{2})", stem)
    if not m:
        # Pattern: VID_20260112_190536 or IMG_20260112_190536
        m = re.match(r"(?:VID|IMG|MOV)[_\-](\d{4})(\d{2})(\d{2})[_\-](\d{2})(\d{2})(\d{2})", stem)
    if m:
        try:
            dt = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6]))
            if 2000 <= dt.year <= datetime.now().year + 1:
                return dt
        except ValueError:
            pass
    return None
