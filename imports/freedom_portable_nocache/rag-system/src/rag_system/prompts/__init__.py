"""Prompt versioning — load and render prompts from prompts/prompts.yml.

Usage
-----
    from rag_system.prompts import get_prompt, render_prompt

    tmpl = get_prompt("answer_with_citations")   # returns PromptConfig
    text = render_prompt(tmpl, query="...", evidence_blocks="...")
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

_PROMPTS_FILE = Path(__file__).parent.parent.parent.parent / "prompts" / "prompts.yml"


@dataclass
class PromptConfig:
    """Structured prompt definition loaded from prompts.yml."""

    name: str
    version: str
    description: str
    template: str


@lru_cache(maxsize=1)
def _load_all() -> Dict[str, PromptConfig]:
    """Load prompts.yml once and cache. Returns dict keyed by prompt name."""
    path = Path(os.getenv("PROMPTS_FILE", str(_PROMPTS_FILE)))
    if yaml is None:
        raise ImportError("PyYAML is required for prompt loading. pip install pyyaml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {
        p["name"]: PromptConfig(
            name=p["name"],
            version=p["version"],
            description=p.get("description", ""),
            template=p["template"],
        )
        for p in data.get("prompts", [])
    }


def get_prompt(name: str) -> PromptConfig:
    """Return the PromptConfig for *name*, raising KeyError if not found."""
    catalog = _load_all()
    if name not in catalog:
        raise KeyError(f"Prompt '{name}' not found. Available: {sorted(catalog)}")
    return catalog[name]


def list_prompts() -> Dict[str, str]:
    """Return {name: version} for all loaded prompts."""
    return {k: v.version for k, v in _load_all().items()}


def render_prompt(config: PromptConfig, **kwargs: str) -> str:
    """Render *config.template* by replacing ``{{ var }}`` with *kwargs* values."""
    text = config.template
    for key, value in kwargs.items():
        text = text.replace("{{ " + key + " }}", value)
        text = text.replace("{{" + key + "}}", value)
    return text
