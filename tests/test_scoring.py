"""Tests for backend.grouping.scoring — 'keep best' duplicate scoring.

Ported from the frontend findBest/pathScore logic so bulk resolution on the
server picks the same winner the UI would recommend.
"""

from backend.grouping.scoring import path_score, pick_best


# ---------------------------------------------------------------------------
# path_score
# ---------------------------------------------------------------------------

def test_path_score_downloads_ranks_below_cloud_original():
    """A cloud original should outrank a Downloads copy."""
    assert path_score("/Users/x/Downloads/a.jpg") < path_score(
        "/Users/x/Library/CloudStorage/OneDrive-Personal/a.jpg"
    )


def test_path_score_none_is_zero():
    assert path_score(None) == 0


# ---------------------------------------------------------------------------
# pick_best
# ---------------------------------------------------------------------------

def test_pick_best_prefers_higher_resolution():
    images = [
        {"id": 1, "width": 1000, "height": 1000, "file_size": 100, "file_path": "/a.jpg"},
        {"id": 2, "width": 2000, "height": 2000, "file_size": 100, "file_path": "/b.jpg"},
    ]
    assert pick_best(images) == 2


def test_pick_best_prefers_larger_size_at_equal_resolution():
    images = [
        {"id": 1, "width": 1000, "height": 1000, "file_size": 100, "file_path": "/a.jpg"},
        {"id": 2, "width": 1000, "height": 1000, "file_size": 500, "file_path": "/b.jpg"},
    ]
    assert pick_best(images) == 2


def test_pick_best_prefers_original_location_at_equal_res_and_size():
    """Path quality is the tie-breaker: cloud original beats a Downloads copy."""
    images = [
        {"id": 1, "width": 1000, "height": 1000, "file_size": 100,
         "file_path": "/Users/x/Downloads/a.jpg"},
        {"id": 2, "width": 1000, "height": 1000, "file_size": 100,
         "file_path": "/Users/x/Library/CloudStorage/OneDrive-Personal/b.jpg"},
    ]
    assert pick_best(images) == 2


def test_pick_best_empty_returns_none():
    assert pick_best([]) is None


def test_pick_best_single_returns_that_id():
    images = [{"id": 7, "width": 10, "height": 10, "file_size": 1, "file_path": "/a.jpg"}]
    assert pick_best(images) == 7
