"""Последовательный поиск или несколько потоков с общим потоком кандидатов."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import closing
import threading
import time
from .candidates import iter_candidates
from .hashes import HashTarget
from .models import CrackResult, WorkerProgress


def crack(target, config, wordlist=None, on_progress=None):
    total = config.validate(wordlist)
    parsed = HashTarget.parse(target.encoded)
    if parsed.algorithm != target.algorithm:
        raise ValueError('Алгоритм не соответствует хэшу')
    target = parsed
    started = time.perf_counter()
    stopped = threading.Event()
    lock = threading.Lock()
    rows = [WorkerProgress(index + 1, None, 0, 'waiting') for index in range(config.workers)]
    candidates = iter_candidates(config, wordlist)

    def publish():
        if on_progress:
            with lock:
                snapshot = tuple(rows)
            on_progress(snapshot)

    def scan(worker):
        checked, candidate, status = 0, None, 'done'
        try:
            while not stopped.is_set():
                with lock:
                    raw = next(candidates, None)
                    if raw is None:
                        break
                    candidate = raw.decode('utf-8', errors='backslashreplace')
                    rows[worker] = WorkerProgress(worker + 1, candidate, checked, 'running')
                if config.workers == 1:
                    publish()
                matched = target.matches(raw)
                checked += 1
                with lock:
                    rows[worker] = WorkerProgress(worker + 1, candidate, checked, 'running')
                if matched:
                    status = 'found'
                    stopped.set()
                    return raw
            else:
                status = 'stopped'
        except BaseException:
            status = 'error'
            stopped.set()
            raise
        finally:
            with lock:
                rows[worker] = WorkerProgress(worker + 1, candidate, checked, status)
        return None

    with closing(candidates):
        publish()
        if config.workers == 1:
            password = scan(0)
        else:
            executor = ThreadPoolExecutor(max_workers=config.workers, thread_name_prefix='lab3-worker')
            try:
                futures = [executor.submit(scan, worker) for worker in range(config.workers)]
                pending = set(futures)
                while pending:
                    finished, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                    for future in finished:
                        future.result()
                    publish()
                password = next((value for future in futures if (value := future.result()) is not None), None)
            finally:
                stopped.set()
                executor.shutdown(wait=True, cancel_futures=True)
        publish()
    return CrackResult(password is not None, password.decode('utf-8', errors='backslashreplace') if password is not None else None,
                       time.perf_counter() - started, sum(row.checked for row in rows), total,
                       config.workers, 'cpu', password.hex() if password is not None else None)
