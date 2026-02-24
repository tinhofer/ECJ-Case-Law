"""Configuration loading for article2tts."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = _PACKAGE_ROOT / "config"


@dataclass
class Config:
    output_dir: str = "."
    language: str = "auto"  # auto | en | de | fr
    remove_bibliography: bool = True
    remove_urls: bool = True
    remove_citations: bool = True
    expand_abbreviations: bool = True
    custom_abbreviations: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        """Load config from YAML file, falling back to bundled defaults."""
        defaults_path = _CONFIG_DIR / "default.yaml"
        data: dict = {}
        if defaults_path.exists():
            with open(defaults_path) as f:
                data = yaml.safe_load(f) or {}
        if path is not None:
            with open(path) as f:
                overrides = yaml.safe_load(f) or {}
            data.update(overrides)
        # Expand ~ in output_dir
        if "output_dir" in data:
            data["output_dir"] = os.path.expanduser(data["output_dir"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def load_abbreviations(language: str) -> dict[str, str]:
    """Load abbreviation dictionary for the given language code."""
    abbrev_path = _CONFIG_DIR / f"abbreviations_{language}.yaml"
    if not abbrev_path.exists():
        return {}
    with open(abbrev_path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}
