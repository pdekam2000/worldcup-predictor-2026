"""Phase A22 — crash-safe JSONL append with file locking."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable

LockKey = tuple[Any, ...]
DedupeFn = Callable[[dict[str, Any]], LockKey]


@contextmanager
def jsonl_file_lock(path: Path):
    """Cross-process lock via adjacent .lock file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = lock_path.open("a+", encoding="utf-8")
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_jsonl_rows(
    path: Path,
    rows: Iterable[dict[str, Any]],
    *,
    dedupe_key: DedupeFn,
    force: bool = False,
) -> dict[str, Any]:
    """Locked append with duplicate skip. Never truncates unless force rebuild elsewhere."""
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming = list(rows)
    written = 0
    skipped = 0

    with jsonl_file_lock(path):
        existing: set[LockKey] = set()
        if path.is_file() and not force:
            for row in load_jsonl(path):
                existing.add(dedupe_key(row))

        partial = path.with_suffix(path.suffix + ".partial")
        with partial.open("a", encoding="utf-8") as fh:
            for row in incoming:
                key = dedupe_key(row)
                if key in existing:
                    skipped += 1
                    continue
                fh.write(json.dumps(row, default=str) + "\n")
                existing.add(key)
                written += 1

        if written:
            with partial.open("r", encoding="utf-8") as src, path.open("a", encoding="utf-8") as dst:
                dst.write(src.read())
            partial.unlink(missing_ok=True)

    return {"written": written, "skipped_duplicates": skipped, "path": str(path)}


def rebuild_jsonl_deduped(
    path: Path,
    *,
    dedupe_key: DedupeFn,
) -> dict[str, Any]:
    """Vacuum: rewrite file with last row per dedupe key."""
    rows = load_jsonl(path)
    if not rows:
        return {"before": 0, "after": 0, "path": str(path)}
    seen: dict[LockKey, dict[str, Any]] = {}
    for row in rows:
        seen[dedupe_key(row)] = row
    unique = list(seen.values())
    with jsonl_file_lock(path):
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            tmp.write_text("".join(json.dumps(r, default=str) + "\n" for r in unique), encoding="utf-8")
            tmp.replace(path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
    return {"before": len(rows), "after": len(unique), "path": str(path)}


def count_jsonl_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())
