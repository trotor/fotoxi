from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    db_path: str = str(Path.home() / ".fotoxi" / "fotoxi.db")
    thumbs_dir: str = str(Path.home() / ".fotoxi" / "thumbs")
    source_dirs: list[str] = field(default_factory=list)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llava:7b"
    ai_language: str = "english"
    ai_quality_enabled: bool = True
    phash_threshold: int = 10
    burst_time_window: float = 5.0
    thread_pool_size: int = 4
    ollama_concurrency: int = 1
    server_host: str = "127.0.0.1"
    server_port: int = 8000

    def ensure_dirs(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.thumbs_dir).mkdir(parents=True, exist_ok=True)
