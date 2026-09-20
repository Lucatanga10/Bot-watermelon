"""Piccolo storage JSON thread-safe per pannelli/opzioni/config."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

_locks: dict[str, asyncio.Lock] = {}


def _lock_for(name: str) -> asyncio.Lock:
    if name not in _locks:
        _locks[name] = asyncio.Lock()
    return _locks[name]


def _path(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


async def load(name: str, default: Any) -> Any:
    async with _lock_for(name):
        p = _path(name)
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default


async def save(name: str, data: Any) -> None:
    async with _lock_for(name):
        p = _path(name)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
