"""Проверка словаря и потоковый CPU-поиск по исходным байтам."""
from __future__ import annotations

import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .hashes import HashTarget, TargetError
from .models import CrackResult, WorkerProgress


def inspect_wordlist(path: Path) -> dict[str, object]:
    path = path.resolve(strict=True)
    if not path.is_file() or path.stat().st_size > 256 * 1024 * 1024:
        raise ValueError('Словарь должен быть файлом размером не более 256 МиБ')
    digest = hashlib.sha256()
    lines = 0
    last = b''
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
            lines += block.count(b'\n')
            last = block[-1:]
    if last and last != b'\n':
        lines += 1
    return {'sha256': digest.hexdigest(), 'bytes': path.stat().st_size, 'lines': lines}


def crack_wordlist(target: HashTarget, path: Path, on_progress=None, metadata=None) -> CrackResult:
    """Stream raw password bytes in file order using one stoppable worker thread."""
    parsed = HashTarget.parse(target.encoded)
    if parsed.algorithm != target.algorithm:
        raise TargetError('Алгоритм не соответствует хэшу')
    target = parsed
    path = path.resolve(strict=True)
    info = inspect_wordlist(path) if metadata is None else metadata
    stopped = threading.Event()
    started = time.perf_counter()

    def search():
        checked = 0
        candidate = None
        next_update = 0.0
        status = 'done'
        try:
            with path.open('rb') as stream:
                for line in stream:
                    if stopped.is_set():
                        status = 'stopped'
                        break
                    raw = line.removesuffix(b'\n').removesuffix(b'\r')
                    candidate = raw.decode('utf-8', errors='backslashreplace')
                    if on_progress and time.monotonic() >= next_update:
                        on_progress((WorkerProgress(1, candidate, checked, 'running'),))
                        next_update = time.monotonic() + 0.1
                    matched = target.matches(raw)
                    checked += 1
                    if matched:
                        status = 'found'
                        return CrackResult(True, candidate, time.perf_counter() - started,
                                           checked, info['lines'], 1, 'threads', raw.hex())
            return CrackResult(False, None, time.perf_counter() - started, checked, info['lines'], 1, 'threads')
        except BaseException:
            status = 'error'
            raise
        finally:
            if on_progress:
                on_progress((WorkerProgress(1, candidate, checked, status),))

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='dictionary-check')
    try:
        return executor.submit(search).result()
    finally:
        stopped.set()
        executor.shutdown(wait=True, cancel_futures=True)

