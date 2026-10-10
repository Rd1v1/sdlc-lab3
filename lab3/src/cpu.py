"""Разделение диапазона между потоками или процессами и остановка поиска."""
from __future__ import annotations

import multiprocessing
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
from typing import Callable
from .candidates import _candidate_global
from .hashes import HashTarget, TargetError
from .models import CrackConfig, CrackResult, WorkerProgress


_STATUSES = ("waiting", "running", "done", "found", "stopped", "error")
_PROCESS_STATE = None


def _publish(state, locks, worker, checked, index, status):
    with locks[worker]:
        offset = worker * 3
        state[offset] = checked
        state[offset + 1] = index
        state[offset + 2] = status


def _snapshot(state, locks, config):
    rows = []
    for worker in range(config.workers):
        with locks[worker]:
            checked, index, status = state[worker * 3:worker * 3 + 3]
        rows.append(WorkerProgress(worker + 1, _candidate_global(index, config) if index >= 0 else None,
                                   checked, _STATUSES[status]))
    return tuple(rows)


def _scan_worker(target, config, worker, start, end, stopped, state, locks, monitored):
    checked = 0
    index = -1
    status = 2
    next_update = 0.0
    try:
        for index in range(start, end):
            if stopped.is_set():
                status = 4
                # Keep the last attempted index, rather than an untested candidate.
                index = index - 1 if checked else -1
                break
            candidate = _candidate_global(index, config)
            if monitored and time.monotonic() >= next_update:
                _publish(state, locks, worker, checked, index, 1)
                next_update = time.monotonic() + 0.05
            matched = target.matches(candidate)
            checked += 1
            if matched:
                status = 3
                stopped.set()
                return candidate, checked
        return None, checked
    except BaseException:
        status = 5
        stopped.set()
        raise
    finally:
        _publish(state, locks, worker, checked, index, status)


def _initialize_process(stopped, state, locks):
    # The parent handles Ctrl+C and asks workers to stop between verifications.
    import signal
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    global _PROCESS_STATE
    _PROCESS_STATE = (stopped, state, locks)


def _scan_process(target, config, worker, start, end, monitored):
    stopped, state, locks = _PROCESS_STATE
    return _scan_worker(target, config, worker, start, end, stopped, state, locks, monitored)


def crack(target: HashTarget, config: CrackConfig,
          on_progress: Callable[[tuple[WorkerProgress, ...]], None] | None = None) -> CrackResult:
    total = config.validate()
    # Validate manually constructed targets as well as CLI input, before spawning workers.
    if target.algorithm not in ('md5', 'sha1', 'bcrypt', 'argon2id'):
        raise TargetError("Неподдерживаемый алгоритм")
    parsed = HashTarget.parse(target.encoded)
    if parsed.algorithm != target.algorithm:
        raise TargetError("Алгоритм не соответствует хэшу")
    target = parsed
    started = time.perf_counter()
    if config.backend == "processes":
        context = multiprocessing.get_context("spawn")
        stopped = context.Event()
        state = context.RawArray("q", config.workers * 3)
        locks = [context.Lock() for _ in range(config.workers)]
        executor = ProcessPoolExecutor(max_workers=config.workers, mp_context=context,
                                       initializer=_initialize_process, initargs=(stopped, state, locks))
    else:
        stopped = threading.Event()
        state = [0] * (config.workers * 3)
        locks = [threading.Lock() for _ in range(config.workers)]
        executor = ThreadPoolExecutor(max_workers=config.workers, thread_name_prefix="candidate-check")
    for worker in range(config.workers):
        _publish(state, locks, worker, 0, -1, 0)
    futures = []
    password = None
    checked = 0
    try:
        if on_progress:
            on_progress(_snapshot(state, locks, config))
        for worker in range(config.workers):
            start, end = total * worker // config.workers, total * (worker + 1) // config.workers
            if config.backend == "processes":
                future = executor.submit(_scan_process, target, config, worker, start, end, on_progress is not None)
            else:
                future = executor.submit(_scan_worker, target, config, worker, start, end,
                                         stopped, state, locks, on_progress is not None)
            futures.append(future)
        pending = set(futures)
        while pending:
            finished, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in finished:
                found, attempts = future.result()
                checked += attempts
                if found is not None:
                    password = found
            if on_progress:
                on_progress(_snapshot(state, locks, config))
    finally:
        stopped.set()
        executor.shutdown(wait=True, cancel_futures=True)
    return CrackResult(password is not None, password, time.perf_counter() - started,
                       checked, total, config.workers, config.backend)

