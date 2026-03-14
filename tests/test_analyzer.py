from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from backend.indexer.analyzer import _parse_response, analyze_image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jpeg(tmp_path: Path) -> Path:
    img_path = tmp_path / "test.jpg"
    img = Image.new("RGB", (64, 64), color=(128, 128, 128))
    img.save(img_path, format="JPEG")
    return img_path


def _mock_ollama_response(content: str) -> MagicMock:
    """Build a mock httpx.Response that returns the given content string."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"message": {"content": content}}
    return mock_resp


# ---------------------------------------------------------------------------
# _parse_response unit tests
# ---------------------------------------------------------------------------


def test_parse_response_clean_json_with_quality():
    content = json.dumps(
        {"description": "A grey square.", "tags": ["grey", "square"], "quality_score": 0.75}
    )
    result = _parse_response(content, quality_enabled=True)
    assert result == {
        "description": "A grey square.",
        "tags": ["grey", "square"],
        "quality_score": 0.75,
    }


def test_parse_response_json_wrapped_in_text():
    content = (
        "Sure! Here is the JSON you asked for:\n"
        '{"description": "A cat on a mat.", "tags": ["cat", "mat", "indoor"], "quality_score": 0.9}\n'
        "Hope that helps!"
    )
    result = _parse_response(content, quality_enabled=True)
    assert result is not None
    assert result["description"] == "A cat on a mat."
    assert "cat" in result["tags"]
    assert result["quality_score"] == pytest.approx(0.9)


def test_parse_response_no_quality_when_disabled():
    content = json.dumps(
        {"description": "A sunset.", "tags": ["sunset", "sky"], "quality_score": 0.8}
    )
    result = _parse_response(content, quality_enabled=False)
    assert result is not None
    assert result["quality_score"] is None


def test_parse_response_missing_required_fields():
    content = json.dumps({"tags": ["only tags"]})
    result = _parse_response(content, quality_enabled=True)
    assert result is None


def test_parse_response_no_json():
    result = _parse_response("No JSON here at all.", quality_enabled=True)
    assert result is None


# ---------------------------------------------------------------------------
# analyze_image integration-style tests (httpx mocked)
# ---------------------------------------------------------------------------


def test_analyze_image_success(tmp_path):
    img_path = _make_jpeg(tmp_path)

    response_content = json.dumps(
        {
            "description": "A solid grey image used for testing purposes.",
            "tags": ["grey", "test", "solid", "image", "monochrome"],
            "quality_score": 0.65,
        }
    )
    mock_resp = _mock_ollama_response(response_content)

    with patch("backend.indexer.analyzer.httpx.post", return_value=mock_resp) as mock_post:
        result = analyze_image(
            path=img_path,
            ollama_url="http://localhost:11434",
            model="llava:7b",
            language="english",
            quality_enabled=True,
            timeout=30.0,
            retries=3,
            retry_delay=0.0,
        )

    assert result is not None
    assert result["description"] == "A solid grey image used for testing purposes."
    assert isinstance(result["tags"], list)
    assert len(result["tags"]) == 5
    assert result["quality_score"] == pytest.approx(0.65)

    # Verify the POST was called with the correct URL
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "http://localhost:11434/api/chat"

    # Verify payload structure
    payload = call_args[1]["json"]
    assert payload["model"] == "llava:7b"
    assert payload["stream"] is False
    assert len(payload["messages"]) == 1
    msg = payload["messages"][0]
    assert msg["role"] == "user"
    assert "images" in msg
    assert isinstance(msg["images"][0], str)  # base64 string


def test_analyze_image_quality_disabled(tmp_path):
    img_path = _make_jpeg(tmp_path)

    response_content = json.dumps(
        {
            "description": "A solid grey image.",
            "tags": ["grey", "test", "solid", "image", "monochrome"],
        }
    )
    mock_resp = _mock_ollama_response(response_content)

    with patch("backend.indexer.analyzer.httpx.post", return_value=mock_resp):
        result = analyze_image(
            path=img_path,
            ollama_url="http://localhost:11434",
            model="llava:7b",
            language="english",
            quality_enabled=False,
            timeout=30.0,
            retries=1,
            retry_delay=0.0,
        )

    assert result is not None
    assert result["quality_score"] is None


def test_analyze_image_ollama_down(tmp_path):
    img_path = _make_jpeg(tmp_path)

    with patch(
        "backend.indexer.analyzer.httpx.post",
        side_effect=httpx_connect_error(),
    ):
        result = analyze_image(
            path=img_path,
            ollama_url="http://localhost:11434",
            model="llava:7b",
            language="english",
            quality_enabled=True,
            timeout=5.0,
            retries=3,
            retry_delay=0.0,  # no sleep in tests
        )

    assert result is None


def httpx_connect_error():
    """Return a ConnectError to simulate Ollama being unreachable."""
    import httpx as _httpx

    return _httpx.ConnectError("Connection refused")


def test_analyze_image_retries_then_succeeds(tmp_path):
    """First two calls fail; third succeeds."""
    img_path = _make_jpeg(tmp_path)

    import httpx as _httpx

    success_content = json.dumps(
        {
            "description": "A grey square on the third try.",
            "tags": ["grey", "square", "retry", "test", "image"],
            "quality_score": 0.5,
        }
    )
    success_resp = _mock_ollama_response(success_content)

    side_effects = [
        _httpx.ConnectError("Connection refused"),
        _httpx.ConnectError("Connection refused"),
        success_resp,
    ]

    with patch("backend.indexer.analyzer.httpx.post", side_effect=side_effects):
        result = analyze_image(
            path=img_path,
            ollama_url="http://localhost:11434",
            model="llava:7b",
            language="english",
            quality_enabled=True,
            timeout=5.0,
            retries=3,
            retry_delay=0.0,
        )

    assert result is not None
    assert result["description"] == "A grey square on the third try."


def test_analyze_image_nonexistent_file(tmp_path):
    result = analyze_image(
        path=tmp_path / "does_not_exist.jpg",
        ollama_url="http://localhost:11434",
        model="llava:7b",
        language="english",
        quality_enabled=True,
        timeout=5.0,
        retries=1,
        retry_delay=0.0,
    )
    assert result is None


def test_analyze_image_language_in_prompt(tmp_path):
    """Verify the chosen language appears in the prompt sent to Ollama."""
    img_path = _make_jpeg(tmp_path)

    response_content = json.dumps(
        {
            "description": "Ein graues Bild.",
            "tags": ["grau", "bild", "test", "einfarbig", "quadrat"],
            "quality_score": 0.5,
        }
    )
    mock_resp = _mock_ollama_response(response_content)

    with patch("backend.indexer.analyzer.httpx.post", return_value=mock_resp) as mock_post:
        analyze_image(
            path=img_path,
            ollama_url="http://localhost:11434",
            model="llava:7b",
            language="german",
            quality_enabled=False,
            timeout=5.0,
            retries=1,
            retry_delay=0.0,
        )

    payload = mock_post.call_args[1]["json"]
    prompt_text = payload["messages"][0]["content"]
    assert "german" in prompt_text
