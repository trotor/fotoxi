import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def is_cloud_path(path: Path) -> bool:
    """Check if a path is stored in iCloud/CloudStorage.

    Args:
        path: The file path to check.

    Returns:
        True if the path contains 'Library/CloudStorage', False otherwise.
    """
    return "Library/CloudStorage" in str(path)


async def evict_file(path: Path) -> bool:
    """Evict a cloud-stored file to free local disk space using brctl.

    If the path is not a cloud path, this is a no-op and returns True.

    Args:
        path: The file path to evict.

    Returns:
        True on success or if the file is not a cloud path, False on failure.
    """
    if not is_cloud_path(path):
        return True

    try:
        args = ["brctl", "evict", str(path)]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode == 0:
            return True
        else:
            logger.warning("brctl evict failed for %s (returncode=%d)", path, proc.returncode)
            return False
    except Exception as exc:
        logger.warning("Failed to evict %s: %s", path, exc)
        return False
