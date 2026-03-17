from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _parse_response(content: str, quality_enabled: bool) -> Optional[dict]:
    """Parse JSON from LLM response content.

    Handles cases where the LLM wraps JSON in surrounding text by finding
    the first '{' and last '}' in the content.
    """
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        logger.warning("No JSON object found in response content")
        return None

    json_str = content[start : end + 1]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse JSON from response: %s", exc)
        return None

    description = data.get("description")
    tags = data.get("tags")

    if not isinstance(description, str) or not isinstance(tags, list):
        logger.warning("Response JSON missing required fields 'description' or 'tags'")
        return None

    quality_score: Optional[float] = None
    if quality_enabled:
        qs = data.get("quality_score")
        if qs is not None:
            try:
                quality_score = float(qs)
            except (TypeError, ValueError):
                quality_score = None

    colors = data.get("colors", [])
    scene_type = data.get("scene_type", "other")
    return {
        "description": description,
        "tags": [str(t) for t in tags],
        "colors": [str(c) for c in colors] if isinstance(colors, list) else [],
        "scene_type": str(scene_type) if isinstance(scene_type, str) else "other",
        "quality_score": quality_score,
    }


def analyze_image(
    path: str | Path,
    ollama_url: str,
    model: str,
    language: str,
    quality_enabled: bool,
    timeout: float = 120.0,
    retries: int = 3,
    retry_delay: float = 30.0,
    thumb_path: str | Path | None = None,
) -> Optional[dict]:
    """Analyze an image using an Ollama vision model.

    Uses thumbnail if available (much faster, no cloud download needed).
    Skips videos without thumbnails.
    Returns a dict with 'description', 'tags', and 'quality_score'.
    """
    path = Path(path)
    # Prefer thumbnail for AI analysis (300px is enough for description)
    source = Path(thumb_path) if thumb_path and Path(thumb_path).exists() else path
    try:
        image_data = base64.b64encode(source.read_bytes()).decode("utf-8")
    except OSError as exc:
        logger.error("Cannot read image file %s: %s", path, exc)
        return None

    quality_instruction = (
        '\n- "quality_score": a float between 0.0 and 1.0 rating photographic quality (sharpness, exposure, composition)'
        if quality_enabled
        else ""
    )
    prompt = (
        f"Analyze this image carefully and respond with ONLY a JSON object (no other text).\n"
        f"Fields:\n"
        f'- "description": 2-3 sentence description in {language}. Include what is shown, '
        f"the setting/environment, mood, and any notable details.\n"
        f'- "tags": array of 8-15 keyword tags in {language}. Include: subject, action, '
        f"setting, objects, colors, mood, style (e.g. portrait, landscape, macro), "
        f"time of day if visible, season if apparent.\n"
        f'- "colors": array of 2-4 dominant color names in english (e.g. "blue", "warm orange")\n'
        f'- "scene_type": one of: "portrait", "group", "landscape", "cityscape", "indoor", '
        f'"food", "animal", "document", "screenshot", "art", "macro", "other"'
        f"{quality_instruction}\n\n"
        f"Respond with ONLY the JSON object."
    )

    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_data],
            }
        ],
    }

    url = f"{ollama_url.rstrip('/')}/api/chat"
    last_exc: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            response = httpx.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            body = response.json()
            content = body["message"]["content"]
            result = _parse_response(content, quality_enabled)
            if result is not None:
                return result
            logger.warning(
                "Attempt %d/%d: could not parse valid response", attempt, retries
            )
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "Attempt %d/%d failed for %s: %s", attempt, retries, path, exc
            )

        if attempt < retries:
            time.sleep(min(retry_delay, 5.0))  # Max 5s between retries

    logger.error(
        "All %d retries exhausted for %s. Last error: %s", retries, path, last_exc
    )
    return None
