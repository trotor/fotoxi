import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.indexer.eviction import evict_file, is_cloud_path


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
# evict_file – non-cloud path (no-op)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evict_non_cloud_path():
    path = Path("/Users/test/Photos/photo.jpg")
    result = await evict_file(path)
    assert result is True


# ---------------------------------------------------------------------------
# evict_file – cloud path, subprocess succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evict_cloud_success():
    path = Path("/Users/test/Library/CloudStorage/OneDrive-User/photo.jpg")

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
# evict_file – cloud path, subprocess fails (non-zero returncode)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evict_cloud_failure_nonzero():
    path = Path("/Users/test/Library/CloudStorage/OneDrive-User/photo.jpg")

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.wait = AsyncMock(return_value=None)

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
        result = await evict_file(path)

    assert result is False


# ---------------------------------------------------------------------------
# evict_file – cloud path, subprocess raises an exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evict_cloud_exception():
    path = Path("/Users/test/Library/CloudStorage/OneDrive-User/photo.jpg")

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(side_effect=OSError("brctl not found"))):
        result = await evict_file(path)

    assert result is False
