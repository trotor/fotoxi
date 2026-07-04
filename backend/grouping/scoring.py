"""Scoring for picking the 'best' image in a duplicate group.

Mirrors the frontend ``findBest``/``pathScore`` logic (Duplicates.tsx) so that
server-side bulk resolution keeps the same image the UI would recommend.
Weighting: resolution > file size > path quality.
"""

from __future__ import annotations

from typing import Optional


def path_score(path: Optional[str]) -> int:
    """Rank a file location — prefer cloud originals over downloads/temp copies."""
    if not path:
        return 0
    p = path.lower()
    if "/originals/" in p:
        return 30
    if "onedrive" in p or "googledrive" in p or "icloud" in p:
        return 20
    if "/pictures/" in p or "/valokuvat/" in p:
        return 15
    if "/documents/" in p:
        return 10
    if "/downloads/" in p:
        return 5
    return 10


def _score(image: dict) -> int:
    pixels = (image.get("width") or 0) * (image.get("height") or 0)
    size = image.get("file_size") or 0
    return pixels * 1000 + size + path_score(image.get("file_path")) * 100000


def pick_best(images: list[dict]) -> Optional[int]:
    """Return the id of the best image in ``images`` (or None if empty).

    Each image dict is expected to have ``id``, ``width``, ``height``,
    ``file_size`` and ``file_path`` keys (missing values treated as 0/None).
    """
    if not images:
        return None
    best_id = images[0]["id"]
    best_score = -1
    for img in images:
        score = _score(img)
        if score > best_score:
            best_score = score
            best_id = img["id"]
    return best_id
