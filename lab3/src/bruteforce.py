from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import threading
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator


class TargetError(ValueError):
    pass


@dataclass(frozen=True)
class HashTarget:
    algorithm: str
    encoded: str

    @classmethod
    def parse(cls, encoded: str) -> HashTarget:
        value = encoded.strip()
        if re.fullmatch(r"[0-9a-fA-F]{32}", value):
            return cls("md5", value.lower())
        if re.fullmatch(r"[0-9a-fA-F]{40}", value):
            return cls("sha1", value.lower())
        if value.startswith(("$2a$", "$2b$", "$2y$")):
            match = re.fullmatch(r"\$2[aby]\$(\d\d)\$[./A-Za-z0-9]{53}", value)
            if not match or not 4 <= int(match.group(1)) <= 12:
                raise TargetError("Некорректный bcrypt-хэш или cost вне учебного предела 4-12")
            return cls("bcrypt", value)
        if value.startswith("$argon2id$"):
            match = re.fullmatch(r"\$argon2id\$v=19\$m=(\d+),t=(\d+),p=(\d+)\$([A-Za-z0-9+/]+)\$([A-Za-z0-9+/]+)", value)
            if not match or len(value) > 512:
                raise TargetError("Некорректный Argon2id-хэш")
            memory_kib, iterations, parallelism = map(int, match.groups()[:3])
            if not 8 <= memory_kib <= 262144 or not 1 <= iterations <= 10 or not 1 <= parallelism <= 8:
                raise TargetError("Параметры Argon2id выходят за установленный предел")
            if memory_kib < 8 * parallelism:
                raise TargetError("Argon2id memory must be at least 8 * parallelism")
            try:
                salt, digest = [base64.b64decode(part + '=' * (-len(part) % 4), validate=True) for part in match.groups()[3:]]
            except binascii.Error as error:
                raise TargetError("Некорректная base64 в Argon2id") from error
            if not 8 <= len(salt) <= 64 or not 4 <= len(digest) <= 64:
                raise TargetError("Некорректные длины salt/hash Argon2id")
            return cls("argon2id", value)
        raise TargetError("Поддерживаются только MD5, SHA-1, bcrypt и Argon2id")

    def matches(self, candidate: str) -> bool:
        if self.algorithm not in ('md5', 'sha1', 'bcrypt', 'argon2id'):
            raise TargetError("Неподдерживаемый алгоритм")
        raw = candidate.encode("utf-8")
        if self.algorithm == "md5":
            return hashlib.md5(raw, usedforsecurity=False).hexdigest() == self.encoded
        if self.algorithm == "sha1":
            return hashlib.sha1(raw, usedforsecurity=False).hexdigest() == self.encoded
        if self.algorithm == "bcrypt":
            if len(raw) > 72:
                return False
            try:
                import bcrypt
            except ImportError as error:
                raise RuntimeError("Для bcrypt активируйте .venv и установите requirements.txt") from error
            return bcrypt.checkpw(raw, self.encoded.encode("ascii"))
        try:
            from argon2 import PasswordHasher
            from argon2.exceptions import VerificationError, VerifyMismatchError
        except ImportError as error:
            raise RuntimeError("Для Argon2 активируйте .venv и установите requirements.txt") from error
        try:
            return PasswordHasher().verify(self.encoded, candidate)
        except VerifyMismatchError:
            return False
        except VerificationError as error:
            raise TargetError("Argon2id-хэш повреждён или не поддерживается") from error


@dataclass(frozen=True)
class CrackConfig:
    alphabet: str
    min_length: int
    max_length: int
    candidate_limit: int = 2_000_000
    workers: int = 1
    backend: str = "threads"

    def validate(self) -> int:
        if not self.alphabet or len(self.alphabet) > 128 or len(set(self.alphabet)) != len(self.alphabet):
            raise ValueError("Алфавит должен содержать 1-128 уникальных символов")
        if not 1 <= self.min_length <= self.max_length <= 8:
            raise ValueError("Длины кандидатов должны находиться в диапазоне 1-8")
        if self.candidate_limit < 1:
            raise ValueError("Лимит кандидатов должен быть положительным")
        if not 1 <= self.workers <= min(64, os.cpu_count() or 1):
            raise ValueError("Число воркеров должно быть от 1 до числа логических процессоров (максимум 64)")
        if self.backend not in ("threads", "processes"):
            raise ValueError("Режим воркеров: threads или processes")
        if self.backend == "processes" and os.name == "nt" and self.workers > 61:
            raise ValueError("На Windows допускается не более 61 процесса")
        if any(ord(character) < 32 or ord(character) == 127 for character in self.alphabet):
            raise ValueError("Управляющие символы в алфавите запрещены")
        count = sum(len(self.alphabet) ** length for length in range(self.min_length, self.max_length + 1))
        if count > self.candidate_limit:
            raise ValueError(f"Диапазон содержит {count:,} кандидатов, лимит: {self.candidate_limit:,}")
        return count


@dataclass(frozen=True)
class CrackResult:
    found: bool
    password: str | None
    elapsed_seconds: float
    candidates_checked: int
    total_candidates: int
    workers: int
    backend: str = "threads"


def candidate_at(index: int, alphabet: str, length: int) -> str:
    if not alphabet or length < 1 or not 0 <= index < len(alphabet) ** length:
        raise ValueError("Индекс кандидата вне пространства перебора")
    base = len(alphabet)
    characters = [alphabet[0]] * length
    for position in range(length - 1, -1, -1):
        index, digit = divmod(index, base)
        characters[position] = alphabet[digit]
    return "".join(characters)


def iter_candidates(config: CrackConfig) -> Iterator[str]:
    config.validate()
    for length in range(config.min_length, config.max_length + 1):
        for index in range(len(config.alphabet) ** length):
            yield candidate_at(index, config.alphabet, length)


@dataclass(frozen=True)
class WorkerProgress:
    worker: int
    candidate: str | None
    checked: int
    status: str


_STATUSES = ("waiting", "running", "done", "found", "stopped", "error")
_PROCESS_STATE = None


def _candidate_global(index: int, config: CrackConfig) -> str:
    for length in range(config.min_length, config.max_length + 1):
        count = len(config.alphabet) ** length
        if index < count:
            return candidate_at(index, config.alphabet, length)
        index -= count
    raise ValueError("Индекс вне пространства перебора")


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
    if target.algorithm not in HASHCAT_MODES:
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


class CliProgress:
    """Render sampled worker state on stderr, leaving stdout as machine-readable JSON."""
    def __init__(self, config: CrackConfig, stream=None):
        self.config = config
        self.stream = sys.stderr if stream is None else stream
        self.total = config.validate()
        self.started = time.perf_counter()
        self.last_render = 0.0
        self.previous = None
        self.lines = 0
        self.ansi = self.stream.isatty() and os.environ.get("TERM") != "dumb"
        if config.workers + 3 >= shutil.get_terminal_size((100, 24)).lines:
            self.ansi = False  # Full snapshots when the table cannot fit on one screen.
        if self.ansi and os.name == "nt":
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.GetStdHandle.restype = ctypes.c_void_p
            handle = kernel.GetStdHandle(-12)
            mode = ctypes.c_ulong()
            self.ansi = bool(kernel.GetConsoleMode(ctypes.c_void_p(handle), ctypes.byref(mode))
                             and kernel.SetConsoleMode(ctypes.c_void_p(handle), mode.value | 4))

    def __call__(self, rows):
        now = time.perf_counter()
        final = all(row.status not in ("waiting", "running") for row in rows)
        if self.previous == rows or (not final and now - self.last_render < 0.1):
            return
        self.previous = rows
        self.last_render = now
        checked = sum(row.checked for row in rows)
        elapsed = now - self.started
        width = min(100, max(20, shutil.get_terminal_size((100, 24)).columns - 1))
        bar_size = 20
        filled = int(bar_size * checked / self.total)
        lines = [f"{self.config.backend} | workers={self.config.workers} | {elapsed:.1f}s",
                 f"[{'#' * filled}{'-' * (bar_size - filled)}] {checked}/{self.total} "
                 f"({100 * checked / self.total:.1f}%) | {checked / max(elapsed, 1e-9):.0f} checks/s",
                 "WORKER  STATE     CHECKED   CANDIDATE (latest sample)"]
        for row in rows:
            candidate = json.dumps(row.candidate, ensure_ascii=True) if row.candidate is not None else "-"
            lines.append(f"{row.worker:>6}  {row.status:<8}  {row.checked:>7}   {candidate}")
        if self.ansi and self.lines:
            self.stream.write(f"\x1b[{self.lines}A")
        for line in lines:
            self.stream.write(("\x1b[2K" if self.ansi else "") + line[:width] + "\n")
        self.stream.flush()
        self.lines = len(lines)


HASHCAT_MODES = {"md5": "0", "sha1": "100", "bcrypt": "3200", "argon2id": "34000"}


def compare_hashcat(target: HashTarget, config: CrackConfig, executable: str = "hashcat") -> dict[str, object]:
    binary = shutil.which(executable)
    if binary is None:
        return {"available": False, "reason": "hashcat is not installed", "elapsed_seconds": None}
    binary = str(Path(binary).resolve())
    mode = HASHCAT_MODES.get(target.algorithm)
    if mode is None:
        return {"available": False, "reason": f"No verified hashcat mode configured for {target.algorithm}", "elapsed_seconds": None}
    config.validate()
    scratch = Path(__file__).resolve().parents[2] / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lab3-hashcat-", dir=scratch) as directory:
        target_file = Path(directory) / "target.hash"
        wordlist = Path(directory) / "candidates.txt"
        cracked_file = Path(directory) / "cracked.txt"
        target_file.write_text(target.encoded + "\n", encoding="ascii")
        with wordlist.open("w", encoding="utf-8", newline="\n") as output:
            for candidate in iter_candidates(config):
                output.write(candidate + "\n")
        command = [
            binary,
            "--quiet",
            "--potfile-disable",
            "--restore-disable",
            "--logfile-disable",
            "--outfile", str(cracked_file),
            "--outfile-format", "2",
            "-m", mode,
            "-a", "0",
            str(target_file),
            str(wordlist),
        ]
        started = time.perf_counter()
        process = subprocess.run(command, cwd=Path(binary).parent, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=300, check=False)
        elapsed = time.perf_counter() - started
        output_text = process.stdout + process.stderr
        if process.returncode not in (0, 1):
            return {"available": True, "supported": False, "reason": output_text.strip()[-1000:], "elapsed_seconds": elapsed}
        return {
            "available": True,
            "supported": True,
            "cracked": cracked_file.exists() and any(target.matches(line) for line in cracked_file.read_text(encoding='utf-8').splitlines()),
            "elapsed_seconds": elapsed,
            "command": f"hashcat --potfile-disable --restore-disable --logfile-disable -m {mode} -a 0 target.hash candidates.txt",
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Учебный локальный перебор тестовых хэшей")
    parser.add_argument("target", help="Локальный тестовый hash string")
    parser.add_argument("--alphabet", default="0123456789")
    parser.add_argument("--min-length", type=int, default=1)
    parser.add_argument("--max-length", type=int, default=6)
    parser.add_argument("--candidate-limit", type=int, default=2_000_000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--backend", choices=("threads", "processes"), default="threads")
    parser.add_argument("--interactive", action="store_true", help="Запросить режим и число воркеров")
    progress = parser.add_mutually_exclusive_group()
    progress.add_argument("--progress", dest="progress", action="store_true", help="Показать кандидатов воркеров в stderr")
    progress.add_argument("--no-progress", dest="progress", action="store_false", help="Отключить таблицу воркеров")
    parser.set_defaults(progress=None)
    parser.add_argument("--compare-hashcat", action="store_true")
    return parser


def run(arguments: list[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    try:
        target = HashTarget.parse(options.target)
        if options.interactive:
            print("Режим: threads / processes", file=sys.stderr)
            print("Режим [threads]: ", end="", file=sys.stderr, flush=True)
            options.backend = input().strip() or "threads"
            print("Число воркеров [1]: ", end="", file=sys.stderr, flush=True)
            options.workers = int(input().strip() or "1")
        config = CrackConfig(options.alphabet, options.min_length, options.max_length,
                             options.candidate_limit, options.workers, options.backend)
        enabled = sys.stderr.isatty() if options.progress is None else options.progress
        result = crack(target, config, on_progress=CliProgress(config) if enabled else None)
        report: dict[str, object] = {"algorithm": target.algorithm, **asdict(result)}
        if options.compare_hashcat:
            report["hashcat"] = compare_hashcat(target, config)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if result.found else 1
    except (KeyboardInterrupt, EOFError):
        print("Перебор прерван", file=sys.stderr)
        return 130
    except (TargetError, ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
