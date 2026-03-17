from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


_PROJECT_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class Config:
    db_path: str = str(_PROJECT_DIR / "fotoxi.db")
    thumbs_dir: str = str(_PROJECT_DIR / "thumbs")
    source_dirs: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=lambda: [
        "derivatives", "resources", "masters", ".thumbnails", ".cache",
        "Thumbnails", "Previews", "Caches",
    ])
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llava:7b"
    ai_language: str = "english"
    ai_quality_enabled: bool = True
    phash_threshold: int = 10
    burst_time_window: float = 5.0
    thread_pool_size: int = 4
    ollama_concurrency: int = 1
    ui_language: str = "fi"
    server_host: str = "127.0.0.1"
    server_port: int = 8000
    ai_thumb_size: int = 512
    auto_process_on_start: bool = False

    @property
    def ai_thumbs_dir(self) -> str:
        return str(Path(self.thumbs_dir).parent / "ai_thumbs")

    def ensure_dirs(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.thumbs_dir).mkdir(parents=True, exist_ok=True)
        Path(self.ai_thumbs_dir).mkdir(parents=True, exist_ok=True)
