from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from archiflow.duplicate_detector import compute_sha256


def _collect_files(source: Path, limit: int) -> list[Path]:
    files = [item for item in source.rglob("*") if item.is_file()]
    files.sort(key=lambda item: str(item).lower())
    if limit > 0:
        return files[:limit]
    return files


def _run_sequential(files: list[Path]) -> float:
    start = time.perf_counter()
    for path in files:
        compute_sha256(path)
    return time.perf_counter() - start


async def _run_asyncio_to_thread(files: list[Path], workers: int) -> float:
    semaphore = asyncio.Semaphore(workers)

    async def _hash_one(path: Path) -> None:
        async with semaphore:
            await asyncio.to_thread(compute_sha256, path)

    start = time.perf_counter()
    await asyncio.gather(*(_hash_one(path) for path in files))
    return time.perf_counter() - start


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AsyncIO exploration probe for SHA hashing.")
    parser.add_argument("--source", required=True, help="Source folder for sample hashing.")
    parser.add_argument("--limit", type=int, default=1000, help="Max file count to hash (0 means all).")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent asyncio.to_thread workers.")
    args = parser.parse_args(argv)

    source = Path(args.source).expanduser().resolve()
    if not source.is_dir():
        print(f"[asyncio-probe] source not found: {source}")
        return 1

    files = _collect_files(source, args.limit)
    if not files:
        print(f"[asyncio-probe] no files found under: {source}")
        return 1

    sequential = _run_sequential(files)
    async_elapsed = asyncio.run(_run_asyncio_to_thread(files, max(1, args.workers)))

    print(f"[asyncio-probe] files={len(files)}")
    print(f"[asyncio-probe] sequential={sequential:.3f}s")
    print(f"[asyncio-probe] asyncio_to_thread={async_elapsed:.3f}s workers={max(1, args.workers)}")
    if async_elapsed > 0:
        print(f"[asyncio-probe] speedup={sequential / async_elapsed:.2f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
