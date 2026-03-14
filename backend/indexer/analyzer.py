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

    return {
        "description": description,
        "tags": tags,
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
) -> Optional[dict]:
    """Analyze an image using an Ollama vision model.

    Base64-encodes the image and sends it to the Ollama /api/chat endpoint.
    Returns a dict with 'description', 'tags', and 'quality_score' (None when
    quality_enabled is False), or None if all retries are exhausted.
    """
    path = Path(path)
    try:
        image_data = base64.b64encode(path.read_bytes()).decode("utf-8")
    except OSError as exc:
        logger.error("Cannot read image file %s: %s", path, exc)
        return None

    quality_instruction = (
        '\n- "quality_score": a float between 0.0 and 1.0 rating the overall '
        "photographic quality of the image (sharpness, exposure, composition)"
        if quality_enabled
        else ""
    )
    prompt = (
        f"Analyze this image and respond with ONLY a JSON object (no other text) "
        f"containing exactly these fields:\n"
        f'- "description": a 2-3 sentence description of the image in {language}\n'
        f'- "tags": an array of 5 to 10 relevant keyword tags (strings) in {language}'
        f"{quality_instruction}\n\n"
        f"Respond with only the JSON object, no markdown, no explanation."
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
            time.sleep(retry_delay)

    logger.error(
        "All %d retries exhausted for %s. Last error: %s", retries, path, last_exc
    )
    return None
