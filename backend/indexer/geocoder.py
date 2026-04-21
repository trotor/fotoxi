"""Reverse geocoding: convert GPS coordinates to place names via Nominatim.

Clusters nearby coordinates to minimize API calls (1 req/s rate limit).
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Cache: rounded (lat, lon) -> location_name
_cache: dict[tuple[float, float], str] = {}

# Cluster precision: ~500m (round to 2 decimal places ≈ 1.1km per 0.01°)
_PRECISION = 2


def _round_coords(lat: float, lon: float) -> tuple[float, float]:
    """Round coordinates to cluster nearby points."""
    return (round(lat, _PRECISION), round(lon, _PRECISION))


def _format_location(address: dict) -> str:
    """Build a readable location name from Nominatim address components.

    Produces: "Neighbourhood/Suburb, City, Region, Country" — skipping missing parts.
    """
    parts = []

    # Most specific: neighbourhood or suburb
    local = address.get("neighbourhood") or address.get("suburb") or address.get("hamlet") or address.get("village")
    if local:
        parts.append(local)

    # City level
    city = address.get("city") or address.get("town") or address.get("municipality")
    if city and city not in parts:
        parts.append(city)

    # Region
    region = address.get("state") or address.get("county") or address.get("region")
    if region and region not in parts:
        parts.append(region)

    # Country
    country = address.get("country")
    if country and country not in parts:
        parts.append(country)

    return ", ".join(parts) if parts else "Unknown"


async def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Reverse geocode a single coordinate pair. Uses cache for nearby points."""
    key = _round_coords(lat, lon)
    if key in _cache:
        return _cache[key]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": lat,
                    "lon": lon,
                    "format": "json",
                    "addressdetails": 1,
                    "zoom": 14,  # city/town level
                },
                headers={"User-Agent": "Fotoxi/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

        address = data.get("address", {})
        name = _format_location(address)
        _cache[key] = name
        return name

    except Exception as exc:
        logger.warning("Reverse geocode failed for %.4f, %.4f: %s", lat, lon, exc)
        return None


async def batch_reverse_geocode(
    coords: list[tuple[int, float, float]],
    on_progress: Optional[callable] = None,
    on_cluster_done: Optional[callable] = None,
    stop_event: Optional[asyncio.Event] = None,
) -> dict[int, str]:
    """Reverse geocode a batch of (image_id, lat, lon) tuples.

    Clusters nearby points and geocodes only unique clusters.
    Returns {image_id: location_name}.

    Rate limited to 1 request per second (Nominatim policy).
    """
    # Group by cluster key
    cluster_map: dict[tuple[float, float], list[int]] = {}
    coord_for_cluster: dict[tuple[float, float], tuple[float, float]] = {}

    for image_id, lat, lon in coords:
        key = _round_coords(lat, lon)
        cluster_map.setdefault(key, []).append(image_id)
        # Use first actual coordinate as representative
        if key not in coord_for_cluster:
            coord_for_cluster[key] = (lat, lon)

    # Filter out already cached clusters
    to_fetch = [k for k in cluster_map if k not in _cache]
    total_clusters = len(to_fetch)

    logger.info(
        "batch_reverse_geocode: %d images → %d unique clusters (%d cached, %d to fetch)",
        len(coords), len(cluster_map), len(cluster_map) - total_clusters, total_clusters,
    )

    # Fetch uncached clusters with rate limiting
    for i, key in enumerate(to_fetch):
        if stop_event and stop_event.is_set():
            logger.info("batch_reverse_geocode: stop requested at %d/%d", i, total_clusters)
            break

        lat, lon = coord_for_cluster[key]
        name = await reverse_geocode(lat, lon)
        if name:
            _cache[key] = name

        img_count = len(cluster_map[key])
        if on_progress:
            on_progress(i + 1, total_clusters, name, img_count)

        # Save this cluster's results immediately
        if name and on_cluster_done:
            await on_cluster_done(cluster_map[key], name)

        # Rate limit: 1 req/s for Nominatim
        if i < total_clusters - 1:
            await asyncio.sleep(1.1)

    # Build result mapping
    result: dict[int, str] = {}
    for key, image_ids in cluster_map.items():
        name = _cache.get(key)
        if name:
            for image_id in image_ids:
                result[image_id] = name

    return result
