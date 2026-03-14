"""Tests for backend.grouping.duplicates."""

from datetime import datetime, timezone

import pytest

from backend.grouping.duplicates import find_duplicate_groups


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex_with_distance(base_hex: str, flip_bits: int) -> str:
    """Return a new hex hash string that differs from base_hex by flip_bits bits."""
    value = int(base_hex, 16)
    # Flip the lowest `flip_bits` bits
    for bit in range(flip_bits):
        value ^= 1 << bit
    # Preserve the same hex length
    hex_len = len(base_hex)
    return format(value, f"0{hex_len}x")


BASE_PHASH = "0" * 16  # 64-bit zero hash as 16-char hex


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_phash_duplicates():
    """Images with similar phash (distance < threshold) are grouped together."""
    # distance 0 from BASE_PHASH
    phash_a = BASE_PHASH
    # distance 5 from BASE_PHASH (within default threshold of 10)
    phash_b = _hex_with_distance(BASE_PHASH, 5)
    # distance 3 from BASE_PHASH
    phash_c = _hex_with_distance(BASE_PHASH, 3)

    images = [
        {"id": 1, "phash": phash_a, "exif_date": None, "exif_camera_model": None},
        {"id": 2, "phash": phash_b, "exif_date": None, "exif_camera_model": None},
        {"id": 3, "phash": phash_c, "exif_date": None, "exif_camera_model": None},
    ]

    groups = find_duplicate_groups(images)

    assert len(groups) == 1
    group = groups[0]
    assert sorted(group["image_ids"]) == [1, 2, 3]
    assert group["match_type"] == "phash"


def test_burst_duplicates():
    """Images taken within burst_window seconds on the same camera are grouped."""
    t0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 6, 1, 12, 0, 3, tzinfo=timezone.utc)  # 3 s apart
    t2 = datetime(2024, 6, 1, 12, 0, 6, tzinfo=timezone.utc)  # 6 s from t0, 3 s from t1

    # Use deliberately different hashes so pHash alone wouldn't group them.
    # Flip non-overlapping bit ranges so all pairwise distances > threshold 10.
    phash_b = format(0xFFFF_FFFF_0000_0000, "016x")  # upper 32 bits set
    phash_c = format(0x0000_0000_FFFF_FFFF, "016x")  # lower 32 bits set
    # BASE_PHASH is all zeros; distance to phash_b = 32, to phash_c = 32
    # phash_b vs phash_c distance = 64 — all pairs well above threshold 10.

    images = [
        {
            "id": 10,
            "phash": BASE_PHASH,
            "exif_date": t0,
            "exif_camera_model": "Canon EOS R5",
        },
        {
            "id": 11,
            "phash": phash_b,
            "exif_date": t1,
            "exif_camera_model": "Canon EOS R5",
        },
        {
            "id": 12,
            "phash": phash_c,
            "exif_date": t2,
            "exif_camera_model": "Canon EOS R5",
        },
    ]

    # burst_window=5: t0-t1=3s (join), t1-t2=3s (join), t0-t2=6s (no direct join,
    # but transitively connected via t1)
    groups = find_duplicate_groups(images, phash_threshold=10, burst_window=5.0)

    assert len(groups) == 1
    group = groups[0]
    assert sorted(group["image_ids"]) == [10, 11, 12]
    assert group["match_type"] == "burst"


def test_combined_group():
    """A group where both phash and burst signals contribute gets match_type 'phash+burst'."""
    t0 = datetime(2024, 7, 15, 8, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 7, 15, 8, 0, 2, tzinfo=timezone.utc)

    phash_a = BASE_PHASH
    phash_b = _hex_with_distance(BASE_PHASH, 4)  # close hash AND same burst

    images = [
        {
            "id": 20,
            "phash": phash_a,
            "exif_date": t0,
            "exif_camera_model": "Sony A7IV",
        },
        {
            "id": 21,
            "phash": phash_b,
            "exif_date": t1,
            "exif_camera_model": "Sony A7IV",
        },
    ]

    groups = find_duplicate_groups(images, phash_threshold=10, burst_window=5.0)

    assert len(groups) == 1
    group = groups[0]
    assert sorted(group["image_ids"]) == [20, 21]
    assert group["match_type"] == "phash+burst"


def test_no_duplicates():
    """Images with very different hashes and no burst relationship produce no groups."""
    # Use non-overlapping 32-bit masks so all pairwise distances are 32 bits apart.
    phash_a = BASE_PHASH                                         # 0x0000000000000000
    phash_b = format(0xFFFF_FFFF_0000_0000, "016x")             # upper 32 bits set
    phash_c = format(0x0000_0000_FFFF_FFFF, "016x")             # lower 32 bits set

    images = [
        {"id": 30, "phash": phash_a, "exif_date": None, "exif_camera_model": None},
        {"id": 31, "phash": phash_b, "exif_date": None, "exif_camera_model": None},
        {"id": 32, "phash": phash_c, "exif_date": None, "exif_camera_model": None},
    ]

    groups = find_duplicate_groups(images, phash_threshold=10)

    assert groups == []


def test_phash_none_skipped():
    """Images with None phash are not compared via pHash."""
    images = [
        {"id": 40, "phash": None, "exif_date": None, "exif_camera_model": None},
        {"id": 41, "phash": None, "exif_date": None, "exif_camera_model": None},
    ]
    groups = find_duplicate_groups(images)
    assert groups == []


def test_burst_different_cameras_not_grouped():
    """Images on different cameras are not grouped by burst, even if timestamps are close."""
    t0 = datetime(2024, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 8, 1, 10, 0, 1, tzinfo=timezone.utc)

    phash_far = _hex_with_distance(BASE_PHASH, 30)

    images = [
        {
            "id": 50,
            "phash": BASE_PHASH,
            "exif_date": t0,
            "exif_camera_model": "Nikon Z6",
        },
        {
            "id": 51,
            "phash": phash_far,
            "exif_date": t1,
            "exif_camera_model": "Canon EOS R5",
        },
    ]

    groups = find_duplicate_groups(images, phash_threshold=10, burst_window=5.0)
    assert groups == []


def test_empty_input():
    """Empty image list returns empty groups."""
    assert find_duplicate_groups([]) == []
