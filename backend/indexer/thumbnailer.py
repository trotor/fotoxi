import logging
from pathlib import Path
from typing import Optional

from backend.indexer.scanner import VIDEO_EXTENSIONS

logger = logging.getLogger(__name__)


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def generate_thumbnail(source: Path, thumbs_dir: Path, image_id: int) -> Optional[Path]:
    """Generate a 300px (longest side) JPEG thumbnail for an image or video.

    For videos, extracts a frame ~1 second in using OpenCV.
    For images, uses Pillow with EXIF orientation fix.
    """
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumbs_dir / f"{image_id}.jpg"

    if is_video(source):
        return _generate_video_thumbnail(source, thumb_path)
    else:
        return _generate_image_thumbnail(source, thumb_path)


def _generate_image_thumbnail(source: Path, thumb_path: Path) -> Optional[Path]:
    try:
        from PIL import Image, ImageOps
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass

        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((300, 300))
            img = img.convert("RGB")
            img.save(thumb_path, format="JPEG", quality=85)

        return thumb_path
    except Exception as exc:
        logger.warning("Failed to generate image thumbnail for %s: %s", source, exc)
        return None


def _generate_video_thumbnail(source: Path, thumb_path: Path) -> Optional[Path]:
    try:
        import cv2
        cap = cv2.VideoCapture(str(source))
        if not cap.isOpened():
            logger.warning("Cannot open video %s", source)
            return None

        # Seek to ~1 second or 10% of video
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        target_frame = min(int(fps), int(total_frames * 0.1)) if total_frames > 0 else int(fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

        ret, frame = cap.read()
        if not ret:
            # Fallback to first frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            logger.warning("Cannot read frame from %s", source)
            return None

        # Resize to 300px longest side
        h, w = frame.shape[:2]
        if w > h:
            new_w, new_h = 300, int(300 * h / w)
        else:
            new_w, new_h = int(300 * w / h), 300
        frame = cv2.resize(frame, (new_w, new_h))

        cv2.imwrite(str(thumb_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return thumb_path
    except ImportError:
        logger.warning("opencv-python-headless not installed, cannot generate video thumbnail for %s", source)
        return None
    except Exception as exc:
        logger.warning("Failed to generate video thumbnail for %s: %s", source, exc)
        return None
