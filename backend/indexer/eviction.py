import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def is_cloud_path(path: Path) -> bool:
    """Check if a path is stored in a macOS File Provider cloud service.

    Args:
        path: The file path to check.

    Returns:
        True if the path contains 'Library/CloudStorage', False otherwise.
    """
    return "Library/CloudStorage" in str(path)


def is_icloud_path(path: Path) -> bool:
    """Check if a path is an iCloud Drive (Apple CloudDocs) file.

    Only iCloud Drive files can be evicted with ``brctl``. Third-party File
    Provider services (OneDrive, Google Drive, Dropbox) under
    ``~/Library/CloudStorage`` are *not* CloudDocs libraries and ``brctl evict``
    will always fail for them with "Path is outside of any CloudDocs app
    library, will never sync".

    Args:
        path: The file path to check.

    Returns:
        True if the path is an iCloud Drive file, False otherwise.
    """
    s = str(path)
    return "Mobile Documents/com~apple~CloudDocs" in s or "CloudStorage/iCloud" in s


async def evict_file(path: Path) -> bool:
    """Evict an iCloud Drive file to free local disk space using brctl.

    ``brctl`` only manages Apple CloudDocs (iCloud Drive). For any other path —
    a local file or a third-party cloud provider — this is a no-op that returns
    False, because there is nothing brctl can evict.

    Args:
        path: The file path to evict.

    Returns:
        True only if the file was actually evicted via brctl, False otherwise.
    """
    if not is_icloud_path(path):
        return False

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
