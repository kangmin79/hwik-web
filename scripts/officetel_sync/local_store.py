"""로컬 JSONL 읽기/쓰기 (스트리밍, 멱등 추가)."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Iterator

_FILE_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _file_lock(path: Path) -> threading.Lock:
    """파일별 lock — 동시 append 충돌 방지."""
    key = str(path.resolve())
    with _LOCKS_GUARD:
        if key not in _FILE_LOCKS:
            _FILE_LOCKS[key] = threading.Lock()
        return _FILE_LOCKS[key]


def write_jsonl(path: Path, rows: list[dict], *, mode: str = "w") -> int:
    """rows 를 JSONL 로 저장. mode='w' 덮어쓰기, 'a' 추가."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(path):
        with path.open(mode, encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def append_jsonl(path: Path, rows: list[dict]) -> int:
    return write_jsonl(path, rows, mode="a")


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(path):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))
