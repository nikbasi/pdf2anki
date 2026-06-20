from __future__ import annotations

from pathlib import Path

import yaml

from pdf2anki.models import BookConfig


def load_config(path: Path | None) -> BookConfig:
    if path is None or not path.exists():
        return BookConfig()
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return BookConfig.model_validate(data)


def save_config(config: BookConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(config.model_dump(mode="json"), f, default_flow_style=False, allow_unicode=True)
