"""Duplicate grouping using Union-Find with file hash, pHash and burst-detection signals."""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from backend.indexer.hasher import hamming_distance


class _UnionFind:
    def __init__(self, ids: list[int]) -> None:
        self._parent: dict[int, int] = {i: i for i in ids}
        self._rank: dict[int, int] = {i: 0 for i in ids}

    def find(self, x: int) -> int:
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1

    def connected(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)


def _phash_to_int(phash_hex: str) -> int:
    """Convert hex-encoded phash string to integer."""
    return int(phash_hex, 16)


def _band_keys(phash_int: int, num_bands: int, band_bits: int) -> list[tuple[int, int]]:
    """Split a phash integer into bands for LSH bucketing.

    Each band is a (band_index, band_value) tuple. Images that share at least
    one band are candidate pairs for exact distance checking.
    """
    keys = []
    for b in range(num_bands):
        band_val = (phash_int >> (b * band_bits)) & ((1 << band_bits) - 1)
        keys.append((b, band_val))
    return keys


def find_duplicate_groups(
    images: list[dict],
    phash_threshold: int = 10,
    burst_window: float = 5.0,
) -> list[dict]:
    """Find groups of duplicate images using file hash, pHash similarity and burst detection.

    Args:
        images: List of dicts with keys: id, phash, file_hash, exif_date, exif_camera_model.
        phash_threshold: Maximum Hamming distance (exclusive) to consider two
            hashes as duplicates.
        burst_window: Maximum time difference in seconds (inclusive) for burst
            detection.

    Returns:
        List of {"image_ids": [int, ...], "match_type": str} for groups with 2+
        members. match_type is one of "exact", "phash", "burst", or combinations.
    """
    if not images:
        return []

    ids = [img["id"] for img in images]
    uf = _UnionFind(ids)

    exact_pairs: set[frozenset] = set()
    phash_pairs: set[frozenset] = set()
    burst_pairs: set[frozenset] = set()

    # 0. Exact file hash comparison — O(n) via hash buckets
    hash_buckets: dict[str, list[int]] = defaultdict(list)
    for img in images:
        if img.get("file_hash"):
            hash_buckets[img["file_hash"]].append(img["id"])

    for _hash, ids_with_hash in hash_buckets.items():
        if len(ids_with_hash) < 2:
            continue
        for k in range(1, len(ids_with_hash)):
            uf.union(ids_with_hash[0], ids_with_hash[k])
            exact_pairs.add(frozenset({ids_with_hash[0], ids_with_hash[k]}))

    # 1. pHash comparison — LSH band bucketing to avoid O(n²)
    # Split 64-bit phash into bands. Images sharing a band are candidates.
    # With 8 bands of 8 bits, pairs with hamming distance <~10 will very likely
    # share at least one identical band.
    NUM_BANDS = 8
    BAND_BITS = 8
    phash_buckets: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for img in images:
        if img["phash"] is None:
            continue
        phash_int = _phash_to_int(img["phash"])
        for key in _band_keys(phash_int, NUM_BANDS, BAND_BITS):
            phash_buckets[key].append(img)

    # Check candidate pairs within each bucket
    checked_phash: set[frozenset] = set()
    for bucket in phash_buckets.values():
        if len(bucket) < 2:
            continue
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                pair_key = frozenset({a["id"], b["id"]})
                if pair_key in checked_phash:
                    continue
                checked_phash.add(pair_key)
                if hamming_distance(a["phash"], b["phash"]) < phash_threshold:
                    uf.union(a["id"], b["id"])
                    phash_pairs.add(pair_key)

    # 2. Burst detection — sort by time, compare only neighbours within window
    # Group by camera first, then sort by date within each camera group.
    camera_groups: dict[str, list[dict]] = defaultdict(list)
    for img in images:
        if img["exif_date"] is not None and img["exif_camera_model"] is not None:
            camera_groups[img["exif_camera_model"]].append(img)

    for cam_images in camera_groups.values():
        cam_images.sort(key=lambda x: x["exif_date"])
        for i in range(len(cam_images)):
            j = i + 1
            while j < len(cam_images):
                a, b = cam_images[i], cam_images[j]
                delta = abs((a["exif_date"] - b["exif_date"]).total_seconds())
                if delta > burst_window:
                    break  # sorted, so all further j will be even larger
                uf.union(a["id"], b["id"])
                burst_pairs.add(frozenset({a["id"], b["id"]}))
                j += 1

    # 3. Collect groups with 2+ members
    groups: dict[int, list[int]] = defaultdict(list)
    for img in images:
        groups[uf.find(img["id"])].append(img["id"])

    result = []
    for root, members in groups.items():
        if len(members) < 2:
            continue

        member_set = set(members)

        has_exact = any(pair <= member_set for pair in exact_pairs)
        has_phash = any(pair <= member_set for pair in phash_pairs)
        has_burst = any(pair <= member_set for pair in burst_pairs)

        types = []
        if has_exact:
            types.append("exact")
        if has_phash:
            types.append("phash")
        if has_burst:
            types.append("burst")
        match_type = "+".join(types) if types else "unknown"

        result.append({"image_ids": sorted(members), "match_type": match_type})

    return result
