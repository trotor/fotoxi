"""Duplicate grouping using Union-Find with pHash and burst-detection signals."""

from __future__ import annotations

from datetime import datetime
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


def find_duplicate_groups(
    images: list[dict],
    phash_threshold: int = 10,
    burst_window: float = 5.0,
) -> list[dict]:
    """Find groups of duplicate images using pHash similarity and burst detection.

    Args:
        images: List of dicts with keys: id, phash, exif_date, exif_camera_model.
        phash_threshold: Maximum Hamming distance (exclusive) to consider two
            hashes as duplicates.
        burst_window: Maximum time difference in seconds (inclusive) for burst
            detection.

    Returns:
        List of {"image_ids": [int, ...], "match_type": str} for groups with 2+
        members. match_type is one of "phash", "burst", or "phash+burst".
    """
    if not images:
        return []

    ids = [img["id"] for img in images]
    uf = _UnionFind(ids)

    # Track which root pairs were joined via which signal.
    # We record edges as (id_i, id_j) sets to determine match_type later.
    phash_pairs: set[frozenset] = set()
    burst_pairs: set[frozenset] = set()

    n = len(images)

    # 1. pHash comparison
    for i in range(n):
        for j in range(i + 1, n):
            a, b = images[i], images[j]
            if a["phash"] is None or b["phash"] is None:
                continue
            if hamming_distance(a["phash"], b["phash"]) < phash_threshold:
                uf.union(a["id"], b["id"])
                phash_pairs.add(frozenset({a["id"], b["id"]}))

    # 2. Burst detection
    for i in range(n):
        for j in range(i + 1, n):
            a, b = images[i], images[j]
            if (
                a["exif_date"] is None
                or b["exif_date"] is None
                or a["exif_camera_model"] is None
                or b["exif_camera_model"] is None
            ):
                continue
            if a["exif_camera_model"] != b["exif_camera_model"]:
                continue
            delta = abs((a["exif_date"] - b["exif_date"]).total_seconds())
            if delta <= burst_window:
                uf.union(a["id"], b["id"])
                burst_pairs.add(frozenset({a["id"], b["id"]}))

    # 3. Collect groups with 2+ members
    from collections import defaultdict

    groups: dict[int, list[int]] = defaultdict(list)
    for img in images:
        groups[uf.find(img["id"])].append(img["id"])

    result = []
    for root, members in groups.items():
        if len(members) < 2:
            continue

        member_set = set(members)

        # Determine which signals contributed to this group.
        has_phash = any(
            pair <= member_set for pair in phash_pairs
        )
        has_burst = any(
            pair <= member_set for pair in burst_pairs
        )

        if has_phash and has_burst:
            match_type = "phash+burst"
        elif has_phash:
            match_type = "phash"
        else:
            match_type = "burst"

        result.append({"image_ids": sorted(members), "match_type": match_type})

    return result
