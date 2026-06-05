import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.indexer.eviction import evict_file, is_cloud_path, is_icloud_path


# ---------------------------------------------------------------------------
# is_cloud_path
# ---------------------------------------------------------------------------

def test_is_cloud_path_true():
    path = Path("/Users/test/Library/CloudStorage/OneDrive-User/photo.jpg")
    assert is_cloud_path(path) is True


def test_is_cloud_path_false():
    path = Path("/Users/test/Photos/photo.jpg")
    assert is_cloud_path(path) is False


# ---------------------------------------------------------------------------
# is_icloud_path – only Apple CloudDocs / iCloud Drive paths qualify
# ---------------------------------------------------------------------------

def test_is_icloud_path_mobile_documents():
    path = Path("/Users/test/Library/Mobile Documents/com~apple~CloudDocs/photo.jpg")
    assert is_icloud_path(path) is True


def test_is_icloud_path_cloudstorage_icloud_drive():
    path = Path("/Users/test/Library/CloudStorage/iCloud Drive/photo.jpg")
    assert is_icloud_path(path) is True


def test_is_icloud_path_onedrive_false():
    path = Path("/Users/test/Library/CloudStorage/OneDrive-User/photo.jpg")
    assert is_icloud_path(path) is False


def test_is_icloud_path_google_drive_false():
    path = Path("/Users/test/Library/CloudStorage/GoogleDrive-a@b.com/photo.jpg")
    assert is_icloud_path(path) is False


def test_is_icloud_path_non_cloud_false():
    path = Path("/Users/test/Photos/photo.jpg")
    assert is_icloud_path(path) is False


# ---------------------------------------------------------------------------
# evict_file – non-cloud path: never touches brctl, not evicted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evict_non_cloud_path_skips_brctl():
    path = Path("/Users/test/Photos/photo.jpg")
    with patch("asyncio.create_subprocess_exec", new=AsyncMock()) as mock_exec:
        result = await evict_file(path)
    assert result is False
    mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# evict_file – third-party cloud provider (OneDrive): brctl cannot evict,
# so we must NOT call it and must NOT log a per-file warning (the spam bug).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evict_onedrive_skips_brctl():
    path = Path("/Users/test/Library/CloudStorage/OneDrive-User/photo.jpg")
    with patch("asyncio.create_subprocess_exec", new=AsyncMock()) as mock_exec:
        result = await evict_file(path)
    assert result is False
    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_evict_onedrive_does_not_warn(caplog):
    path = Path("/Users/test/Library/CloudStorage/OneDrive-User/photo.jpg")
    with patch("asyncio.create_subprocess_exec", new=AsyncMock()):
        with caplog.at_level("WARNING"):
            await evict_file(path)
    assert caplog.records == []


# ---------------------------------------------------------------------------
# evict_file – iCloud path, subprocess succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evict_icloud_success():
    path = Path("/Users/test/Library/Mobile Documents/com~apple~CloudDocs/photo.jpg")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.wait = AsyncMock(return_value=None)

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)) as mock_exec:
        result = await evict_file(path)

    assert result is True
    mock_exec.assert_called_once_with(
        "brctl", "evict", str(path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# evict_file – iCloud path, subprocess fails (non-zero returncode)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evict_icloud_failure_nonzero():
    path = Path("/Users/test/Library/Mobile Documents/com~apple~CloudDocs/photo.jpg")

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.wait = AsyncMock(return_value=None)

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        result = await evict_file(path)

    assert result is False


# ---------------------------------------------------------------------------
# evict_file – iCloud path, subprocess raises an exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evict_icloud_exception():
    path = Path("/Users/test/Library/Mobile Documents/com~apple~CloudDocs/photo.jpg")

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=OSError("brctl not found"))):
        result = await evict_file(path)

    assert result is False
